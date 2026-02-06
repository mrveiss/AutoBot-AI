# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Librarian Assistant Agent for Web Research.

This agent performs web research using Playwright to find relevant information,
presents results with proper source attribution, and can store quality information
in the knowledge base for future reference.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    from playwright.async_api import Browser, Page, async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None
    Browser = None
    Page = None
    PLAYWRIGHT_AVAILABLE = False

from src.config import config
from src.config.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from src.knowledge_base import KnowledgeBase
from src.llm_interface import LLMInterface

logger = logging.getLogger(__name__)


class LibrarianAssistantAgent:
    """An agent that researches information on the web and manages knowledge."""

    # Agent identifier for SSOT config lookup
    AGENT_ID = "librarian_assistant"

    def _init_llm_config(self) -> None:
        """
        Initialize LLM configuration from SSOT config.

        Sets up llm_provider, llm_endpoint, and model_name attributes
        using explicit SSOT configuration. Issue #620.
        """
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)
        logger.info(
            "Librarian Assistant Agent initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider,
            self.llm_endpoint,
            self.model_name,
        )

    def _init_agent_config(self) -> None:
        """
        Initialize agent-specific configuration settings.

        Sets up search limits, quality thresholds, search engines,
        and trusted domains from config. Issue #620.
        """
        self.enabled = self.config.get_nested("librarian_assistant.enabled", True)
        self.max_search_results = self.config.get_nested(
            "librarian_assistant.max_search_results", 5
        )
        self.max_content_length = self.config.get_nested(
            "librarian_assistant.max_content_length", 2000
        )
        self.quality_threshold = self.config.get_nested(
            "librarian_assistant.quality_threshold", 0.7
        )
        self.auto_store_quality = self.config.get_nested(
            "librarian_assistant.auto_store_quality", True
        )
        self.search_engines = self.config.get_nested(
            "librarian_assistant.search_engines",
            {
                "duckduckgo": "https://duckduckgo.com/?q={query}",
                "bing": "https://www.bing.com/search?q={query}",
                "google": "https://www.google.com/search?q={query}",
            },
        )
        self.trusted_domains = self.config.get_nested(
            "librarian_assistant.trusted_domains",
            [
                "wikipedia.org",
                "github.com",
                "stackoverflow.com",
                "medium.com",
                "arxiv.org",
                "nature.com",
                "sciencedirect.com",
                "ieee.org",
                "acm.org",
            ],
        )

    def __init__(self):
        """Initialize the Librarian Assistant Agent with explicit LLM configuration."""
        self.config = config
        self.knowledge_base = KnowledgeBase()
        self.llm = LLMInterface()

        self._init_llm_config()
        self._init_agent_config()

        self.playwright = None
        self.browser = None

    async def _initialize_playwright(self) -> bool:
        """Initialize Playwright browser instance."""
        if not PLAYWRIGHT_AVAILABLE:
            logger.error(
                "Playwright not available. Install with: pip install playwright"
            )
            return False

        try:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
                # Use Chromium for better compatibility with modern websites
                self.browser = await self.playwright.chromium.launch(
                    headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                logger.info("Playwright browser initialized successfully")
            return True
        except Exception as e:
            logger.error("Failed to initialize Playwright: %s", e)
            return False

    async def _cleanup_playwright(self):
        """Clean up Playwright resources."""
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.browser = None
            self.playwright = None
            logger.info("Playwright resources cleaned up")
        except Exception as e:
            logger.error("Error cleaning up Playwright: %s", e)

    async def _setup_search_page(self, page, search_engine: str, query: str) -> None:
        """Setup page for search (Issue #398: extracted)."""
        await page.set_extra_http_headers(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                )
            }
        )
        search_url_template = self.search_engines.get(
            search_engine, self.search_engines["duckduckgo"]
        )
        search_url = search_url_template.format(query=query.replace(" ", "+"))
        logger.info("Searching with %s: %s", search_engine, query)
        await page.goto(search_url, wait_until="domcontentloaded", timeout=10000)
        await page.wait_for_timeout(2000)

    async def _extract_results_by_engine(
        self, page, search_engine: str
    ) -> List[Dict[str, Any]]:
        """Extract results based on search engine (Issue #398: extracted)."""
        if search_engine == "duckduckgo":
            return await self._extract_duckduckgo_results(page)
        elif search_engine == "bing":
            return await self._extract_bing_results(page)
        elif search_engine == "google":
            return await self._extract_google_results(page)
        return []

    async def search_web(
        self, query: str, search_engine: str = "duckduckgo"
    ) -> List[Dict[str, Any]]:
        """Search the web for information (Issue #398: refactored)."""
        if not self.enabled or not await self._initialize_playwright():
            if not self.enabled:
                return []
            logger.error("Cannot perform web search - Playwright not available")
            return []

        page = None
        try:
            page = await self.browser.new_page()
            await self._setup_search_page(page, search_engine, query)
            results = await self._extract_results_by_engine(page, search_engine)
            results = results[: self.max_search_results]
            logger.info("Found %d search results", len(results))
            return results
        except Exception as e:
            logger.error("Error during web search: %s", e)
            return []
        finally:
            if page:
                await page.close()

    async def _extract_single_ddg_result(self, element) -> Optional[Dict[str, Any]]:
        """Extract single DuckDuckGo result (Issue #334 - extracted helper)."""
        title_element = await element.query_selector("h2 a, h3 a")
        if not title_element:
            return None
        title = await title_element.inner_text()
        url = await title_element.get_attribute("hre")
        if not url or not title:
            return None
        snippet_element = await element.query_selector('[data-result="snippet"]')
        snippet = await snippet_element.inner_text() if snippet_element else ""
        return {
            "title": title.strip(),
            "url": url,
            "snippet": snippet.strip(),
            "source": "DuckDuckGo",
        }

    async def _extract_duckduckgo_results(self, page: Page) -> List[Dict[str, Any]]:
        """Extract search results from DuckDuckGo."""
        results = []
        try:
            await page.wait_for_selector('[data-testid="result"]', timeout=5000)
            result_elements = await page.query_selector_all('[data-testid="result"]')

            for element in result_elements:
                try:
                    result = await self._extract_single_ddg_result(element)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.debug("Error extracting DuckDuckGo result: %s", e)

        except Exception as e:
            logger.error("Error extracting DuckDuckGo results: %s", e)

        return results

    async def _extract_single_bing_result(self, element) -> Optional[Dict[str, Any]]:
        """Extract single Bing result (Issue #334 - extracted helper)."""
        title_element = await element.query_selector("h2 a")
        if not title_element:
            return None
        title = await title_element.inner_text()
        url = await title_element.get_attribute("hre")
        if not url or not title:
            return None
        snippet_element = await element.query_selector(".b_caption p")
        snippet = await snippet_element.inner_text() if snippet_element else ""
        return {
            "title": title.strip(),
            "url": url,
            "snippet": snippet.strip(),
            "source": "Bing",
        }

    async def _extract_bing_results(self, page: Page) -> List[Dict[str, Any]]:
        """Extract search results from Bing."""
        results = []
        try:
            await page.wait_for_selector(".b_algo", timeout=5000)
            result_elements = await page.query_selector_all(".b_algo")

            for element in result_elements:
                try:
                    result = await self._extract_single_bing_result(element)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.debug("Error extracting Bing result: %s", e)

        except Exception as e:
            logger.error("Error extracting Bing results: %s", e)

        return results

    async def _extract_single_google_result(self, element) -> Optional[Dict[str, Any]]:
        """Extract single Google result (Issue #334 - extracted helper)."""
        title_element = await element.query_selector("h3")
        link_element = await element.query_selector("a")
        if not title_element or not link_element:
            return None
        title = await title_element.inner_text()
        url = await link_element.get_attribute("hre")
        if not url or not title or not url.startswith("http"):
            return None
        snippet_elements = await element.query_selector_all(".VwiC3b, .s3v9rd")
        snippet = ""
        if snippet_elements:
            snippet = await snippet_elements[0].inner_text()
        return {
            "title": title.strip(),
            "url": url,
            "snippet": snippet.strip(),
            "source": "Google",
        }

    async def _extract_google_results(self, page: Page) -> List[Dict[str, Any]]:
        """Extract search results from Google."""
        results = []
        try:
            await page.wait_for_selector(".g", timeout=5000)
            result_elements = await page.query_selector_all(".g")

            for element in result_elements:
                try:
                    result = await self._extract_single_google_result(element)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.debug("Error extracting Google result: %s", e)

        except Exception as e:
            logger.error("Error extracting Google results: %s", e)

        return results

    async def _get_page_metadata(self, page, url: str) -> Dict[str, Any]:
        """Extract page metadata (Issue #398: extracted)."""
        title = await page.title()
        description = ""
        try:
            desc_element = await page.query_selector('meta[name="description"]')
            if desc_element:
                description = await desc_element.get_attribute("content") or ""
        except Exception:  # nosec B110 - optional metadata extraction
            pass
        domain = urlparse(url).netloc.lower()
        is_trusted = any(trusted in domain for trusted in self.trusted_domains)
        return {
            "title": title,
            "description": description,
            "domain": domain,
            "is_trusted": is_trusted,
        }

    def _build_content_result(
        self, url: str, metadata: Dict, content: str
    ) -> Dict[str, Any]:
        """Build content extraction result (Issue #398: extracted)."""
        return {
            "url": url,
            "title": metadata["title"],
            "description": metadata["description"],
            "content": content[: self.max_content_length] if content else "",
            "domain": metadata["domain"],
            "is_trusted": metadata["is_trusted"],
            "timestamp": datetime.now().isoformat(),
            "content_length": len(content) if content else 0,
        }

    async def extract_content(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract content from a web page (Issue #398: refactored)."""
        if not await self._initialize_playwright():
            return None

        page = None
        try:
            page = await self.browser.new_page()
            await page.set_extra_http_headers(
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            logger.info("Extracting content from: %s", url)
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=15000
            )
            if not response or response.status >= 400:
                logger.error(
                    "Failed to load page: %s (status: %s)",
                    url,
                    response.status if response else "timeout",
                )
                return None
            await page.wait_for_timeout(2000)
            metadata = await self._get_page_metadata(page, url)
            content = await self._extract_main_content(page)
            logger.info(
                "Extracted %d characters from %s",
                len(content) if content else 0,
                metadata["domain"],
            )
            return self._build_content_result(url, metadata, content)
        except Exception as e:
            logger.error("Error extracting content from %s: %s", url, e)
            return None
        finally:
            if page:
                await page.close()

    async def _try_content_selectors(self, page: Page) -> Optional[str]:
        """Try content selectors to find main content (Issue #398: extracted)."""
        content_selectors = [
            "main",
            "article",
            ".content",
            ".main-content",
            ".post-content",
            ".entry-content",
            "#content",
            ".markdown-body",
            ".mw-parser-output",
            ".answer",
        ]
        for selector in content_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    content = await element.inner_text()
                    if content and len(content.strip()) > 100:
                        return content.strip()
            except Exception:  # nosec B112 - retry on selector failures
                continue
        return None

    async def _extract_body_fallback(self, page: Page) -> str:
        """Extract and clean body content as fallback (Issue #398: extracted)."""
        await page.evaluate(
            """() => {
            const elementsToRemove = document.querySelectorAll(
                'script, style, nav, header, footer, .nav, .navbar, .header, .footer, .sidebar'
            );
            elementsToRemove.forEach(el => el.remove());
        }"""
        )
        body = await page.query_selector("body")
        if body:
            content = await body.inner_text()
            content = re.sub(r"\n\s*\n", "\n\n", content)
            content = re.sub(r" +", " ", content)
            return content.strip()
        return ""

    async def _extract_main_content(self, page: Page) -> str:
        """Extract main content from a web page (Issue #398: refactored)."""
        content = await self._try_content_selectors(page)
        if content:
            return content
        try:
            return await self._extract_body_fallback(page)
        except Exception as e:
            logger.error("Error extracting body content: %s", e)
            return ""

    def _build_quality_prompt(self, content_data: Dict[str, Any]) -> str:
        """Build quality assessment prompt (Issue #398: extracted)."""
        return f"""Please assess the quality of this web content for knowledge base inclusion:
Title: {content_data.get('title', 'N/A')}
Domain: {content_data.get('domain', 'N/A')}
Is Trusted: {content_data.get('is_trusted', False)}
Content Length: {content_data.get('content_length', 0)} chars
Content Sample: {content_data.get('content', '')[:500]}...

Evaluate 0.0-1.0 based on: accuracy, completeness, credibility, clarity, usefulness.
Respond in JSON: {{"score": 0.0-1.0, "reasoning": "...", "recommendation": "store|review|reject", "key_topics": [], "reliability_factors": {{"trusted_domain": bool, "content_quality": "high/medium/low", "information_density": "high/medium/low"}}}}"""

    def _build_fallback_assessment(
        self, content_data: Dict[str, Any], error_msg: str = None
    ) -> Dict[str, Any]:
        """Build fallback assessment (Issue #398: extracted)."""
        if error_msg:
            return {
                "score": 0.3,
                "reasoning": f"Error during assessment: {error_msg}",
                "recommendation": "review",
                "key_topics": [],
                "reliability_factors": {
                    "trusted_domain": False,
                    "content_quality": "unknown",
                    "information_density": "unknown",
                },
            }
        return {
            "score": 0.6 if content_data.get("is_trusted") else 0.4,
            "reasoning": "Automatic assessment - LLM response could not be parsed",
            "recommendation": "review",
            "key_topics": [],
            "reliability_factors": {
                "trusted_domain": content_data.get("is_trusted", False),
                "content_quality": "medium",
                "information_density": "medium",
            },
        }

    async def assess_content_quality(
        self, content_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess content quality using LLM (Issue #398: refactored)."""
        try:
            prompt = self._build_quality_prompt(content_data)
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            try:
                assessment = json.loads(response)
                assessment["score"] = max(
                    0.0, min(1.0, float(assessment.get("score", 0.5)))
                )
                return assessment
            except json.JSONDecodeError:
                logger.warning(
                    "Could not parse quality assessment JSON, using fallback"
                )
                return self._build_fallback_assessment(content_data)
        except Exception as e:
            logger.error("Error assessing content quality: %s", e)
            return self._build_fallback_assessment(content_data, str(e))

    def _build_kb_metadata(
        self, content_data: Dict[str, Any], assessment: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build metadata for KB storage (Issue #398: extracted)."""
        return {
            "source": content_data.get("url", "web_research"),
            "domain": content_data.get("domain", "unknown"),
            "title": content_data.get("title", "Untitled"),
            "quality_score": assessment.get("score", 0.0),
            "recommendation": assessment.get("recommendation", "review"),
            "key_topics": assessment.get("key_topics", []),
            "is_trusted": content_data.get("is_trusted", False),
            "stored_by": "librarian_assistant",
            "timestamp": content_data.get("timestamp", datetime.now().isoformat()),
        }

    async def store_in_knowledge_base(
        self, content_data: Dict[str, Any], assessment: Dict[str, Any]
    ) -> bool:
        """Store quality content in knowledge base (Issue #398: refactored)."""
        try:
            document_content = f"""Title: {content_data.get('title', 'Untitled')}
Source: {content_data.get('url', 'Unknown')}
Domain: {content_data.get('domain', 'Unknown')}
Retrieved: {content_data.get('timestamp', 'Unknown')}

{content_data.get('content', '')}"""
            metadata = self._build_kb_metadata(content_data, assessment)
            success = self.knowledge_base.add_document(document_content, metadata)
            if success:
                logger.info(
                    "Stored content from %s in knowledge base",
                    content_data.get("domain"),
                )
            else:
                logger.error("Failed to store content from %s", content_data.get("url"))
            return success
        except Exception as e:
            logger.error("Error storing content in knowledge base: %s", e)
            return False

    def _should_store_content(
        self, assessment: Dict[str, Any], store_enabled: bool
    ) -> bool:
        """Check if content should be stored (Issue #334 - extracted helper)."""
        if not store_enabled:
            return False
        if assessment.get("score", 0) < self.quality_threshold:
            return False
        return assessment.get("recommendation") == "store"

    async def _process_single_search_result(
        self,
        result: Dict[str, Any],
        store_quality_content: bool,
        stored_list: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Process single search result (Issue #334 - extracted helper)."""
        content = await self.extract_content(result["url"])
        if not content:
            return None
        assessment = await self.assess_content_quality(content)
        content["quality_assessment"] = assessment

        if self._should_store_content(assessment, store_quality_content):
            stored = await self.store_in_knowledge_base(content, assessment)
            if stored:
                stored_list.append(
                    {
                        "url": content["url"],
                        "title": content["title"],
                        "quality_score": assessment.get("score", 0),
                    }
                )
        return content

    def _build_source_entry(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Build source entry from content (Issue #334 - extracted helper)."""
        return {
            "title": content["title"],
            "url": content["url"],
            "domain": content["domain"],
            "is_trusted": content["is_trusted"],
            "quality_score": content.get("quality_assessment", {}).get("score", 0),
        }

    def _init_research_results(self, query: str) -> Dict[str, Any]:
        """Initialize research results structure (Issue #398: extracted)."""
        return {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "search_results": [],
            "content_extracted": [],
            "stored_in_kb": [],
            "summary": "",
            "sources": [],
        }

    async def _extract_and_summarize(
        self,
        query: str,
        search_results: List,
        store_quality_content: bool,
        research_results: Dict,
    ) -> None:
        """Extract content and summarize (Issue #398: extracted)."""
        extracted_content = []
        for result in search_results[:3]:
            content = await self._process_single_search_result(
                result, store_quality_content, research_results["stored_in_kb"]
            )
            if content:
                extracted_content.append(content)
        research_results["content_extracted"] = extracted_content
        if extracted_content:
            research_results["summary"] = await self._create_research_summary(
                query, extracted_content
            )
            research_results["sources"] = [
                self._build_source_entry(c) for c in extracted_content
            ]
        logger.info(
            "Research completed: %d sources analyzed, %d stored in KB",
            len(extracted_content),
            len(research_results["stored_in_kb"]),
        )

    async def research_query(
        self, query: str, store_quality_content: bool = None
    ) -> Dict[str, Any]:
        """Research a query by searching the web (Issue #398: refactored)."""
        if not self.enabled:
            return {"enabled": False, "message": "Librarian Assistant is disabled"}
        if store_quality_content is None:
            store_quality_content = self.auto_store_quality
        research_results = self._init_research_results(query)
        try:
            logger.info("Researching query: %s", query)
            search_results = await self.search_web(query)
            research_results["search_results"] = search_results
            if not search_results:
                research_results["summary"] = "No search results found for the query."
                return research_results
            await self._extract_and_summarize(
                query, search_results, store_quality_content, research_results
            )
        except Exception as e:
            logger.error("Error during research: %s", e)
            research_results["error"] = str(e)
        finally:
            await self._cleanup_playwright()
        return research_results

    async def _create_research_summary(
        self, query: str, content_list: List[Dict[str, Any]]
    ) -> str:
        """Create a summary of research findings."""
        try:
            # Prepare content for summarization
            source_contents = []
            for i, content in enumerate(content_list, 1):
                quality_info = content.get("quality_assessment", {})
                source_contents.append(
                    f"Source {i} - {content['title']} ({content['domain']})\n"
                    f"Quality Score: {quality_info.get('score', 'N/A')}\n"
                    f"Content: {content['content'][:800]}...\n"
                )

            combined_content = "\n---\n".join(source_contents)

            prompt = f"""
Based on the following web research results for the query "{query}", please provide a comprehensive summary that:

1. Synthesizes the key information found
2. Clearly attributes information to sources
3. Notes any contradictions or uncertainties
4. Highlights the most reliable information

Research Results:
{combined_content}

Please format your response to include:
- Main findings with source attribution
- Key facts and concepts discovered
- Source reliability assessment
- Any limitations or gaps in the information

Format sources as: [Source: Domain Name]
"""

            summary = await self.llm.chat([{"role": "user", "content": prompt}])
            return summary

        except Exception as e:
            logger.error("Error creating research summary: %s", e)
            return f"Research completed but summary generation failed: {str(e)}"


# Singleton instance (thread-safe)
import threading

_librarian_assistant = None
_librarian_assistant_lock = threading.Lock()


def get_librarian_assistant() -> LibrarianAssistantAgent:
    """Get the singleton Librarian Assistant Agent instance (thread-safe).

    Returns:
        The Librarian Assistant Agent instance
    """
    global _librarian_assistant
    if _librarian_assistant is None:
        with _librarian_assistant_lock:
            # Double-check after acquiring lock
            if _librarian_assistant is None:
                _librarian_assistant = LibrarianAssistantAgent()
    return _librarian_assistant
