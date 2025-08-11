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
from src.knowledge_base import KnowledgeBase
from src.llm_interface import LLMInterface

logger = logging.getLogger(__name__)


class LibrarianAssistantAgent:
    """An agent that researches information on the web and manages knowledge."""

    def __init__(self):
        """Initialize the Librarian Assistant Agent."""
        self.config = config
        self.knowledge_base = KnowledgeBase()
        self.llm = LLMInterface()

        # Configuration
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

        # Search engines configuration
        self.search_engines = self.config.get_nested(
            "librarian_assistant.search_engines",
            {
                "duckduckgo": "https://duckduckgo.com/?q={query}",
                "bing": "https://www.bing.com/search?q={query}",
                "google": "https://www.google.com/search?q={query}",
            },
        )

        # Trusted domains for content extraction
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
            logger.error(f"Failed to initialize Playwright: {e}")
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
            logger.error(f"Error cleaning up Playwright: {e}")

    async def search_web(
        self, query: str, search_engine: str = "duckduckgo"
    ) -> List[Dict[str, Any]]:
        """Search the web for information using Playwright.

        Args:
            query: Search query
            search_engine: Which search engine to use

        Returns:
            List of search results with URLs and content
        """
        if not self.enabled:
            return []

        if not await self._initialize_playwright():
            logger.error("Cannot perform web search - Playwright not available")
            return []

        results = []
        page = None

        try:
            page = await self.browser.new_page()

            # Set user agent to avoid bot detection
            await page.set_extra_http_headers(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    )
                }
            )

            # Get search URL
            search_url_template = self.search_engines.get(
                search_engine, self.search_engines["duckduckgo"]
            )
            search_url = search_url_template.format(query=query.replace(" ", "+"))

            logger.info(f"Searching with {search_engine}: {query}")
            await page.goto(search_url, wait_until="domcontentloaded", timeout=10000)

            # Wait for search results to load
            await page.wait_for_timeout(2000)

            # Extract search result links based on search engine
            if search_engine == "duckduckgo":
                results = await self._extract_duckduckgo_results(page)
            elif search_engine == "bing":
                results = await self._extract_bing_results(page)
            elif search_engine == "google":
                results = await self._extract_google_results(page)

            # Limit results
            results = results[: self.max_search_results]

            logger.info(f"Found {len(results)} search results")

        except Exception as e:
            logger.error(f"Error during web search: {e}")
        finally:
            if page:
                await page.close()

        return results

    async def _extract_duckduckgo_results(self, page: Page) -> List[Dict[str, Any]]:
        """Extract search results from DuckDuckGo."""
        results = []
        try:
            # Wait for results to load
            await page.wait_for_selector('[data-testid="result"]', timeout=5000)

            # Extract result elements
            result_elements = await page.query_selector_all('[data-testid="result"]')

            for element in result_elements:
                try:
                    # Get title and URL
                    title_element = await element.query_selector("h2 a, h3 a")
                    if title_element:
                        title = await title_element.inner_text()
                        url = await title_element.get_attribute("href")

                        # Get snippet
                        snippet_element = await element.query_selector(
                            '[data-result="snippet"]'
                        )
                        snippet = (
                            await snippet_element.inner_text()
                            if snippet_element
                            else ""
                        )

                        if url and title:
                            results.append(
                                {
                                    "title": title.strip(),
                                    "url": url,
                                    "snippet": snippet.strip(),
                                    "source": "DuckDuckGo",
                                }
                            )
                except Exception as e:
                    logger.debug(f"Error extracting DuckDuckGo result: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error extracting DuckDuckGo results: {e}")

        return results

    async def _extract_bing_results(self, page: Page) -> List[Dict[str, Any]]:
        """Extract search results from Bing."""
        results = []
        try:
            # Wait for results
            await page.wait_for_selector(".b_algo", timeout=5000)
            result_elements = await page.query_selector_all(".b_algo")

            for element in result_elements:
                try:
                    title_element = await element.query_selector("h2 a")
                    if title_element:
                        title = await title_element.inner_text()
                        url = await title_element.get_attribute("href")

                        snippet_element = await element.query_selector(".b_caption p")
                        snippet = (
                            await snippet_element.inner_text()
                            if snippet_element
                            else ""
                        )

                        if url and title:
                            results.append(
                                {
                                    "title": title.strip(),
                                    "url": url,
                                    "snippet": snippet.strip(),
                                    "source": "Bing",
                                }
                            )
                except Exception as e:
                    logger.debug(f"Error extracting Bing result: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error extracting Bing results: {e}")

        return results

    async def _extract_google_results(self, page: Page) -> List[Dict[str, Any]]:
        """Extract search results from Google."""
        results = []
        try:
            # Wait for results
            await page.wait_for_selector(".g", timeout=5000)
            result_elements = await page.query_selector_all(".g")

            for element in result_elements:
                try:
                    title_element = await element.query_selector("h3")
                    link_element = await element.query_selector("a")

                    if title_element and link_element:
                        title = await title_element.inner_text()
                        url = await link_element.get_attribute("href")

                        snippet_elements = await element.query_selector_all(
                            ".VwiC3b, .s3v9rd"
                        )
                        snippet = ""
                        if snippet_elements:
                            snippet = await snippet_elements[0].inner_text()

                        if url and title and url.startswith("http"):
                            results.append(
                                {
                                    "title": title.strip(),
                                    "url": url,
                                    "snippet": snippet.strip(),
                                    "source": "Google",
                                }
                            )
                except Exception as e:
                    logger.debug(f"Error extracting Google result: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error extracting Google results: {e}")

        return results

    async def extract_content(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract content from a web page.

        Args:
            url: URL to extract content from

        Returns:
            Dictionary containing extracted content and metadata
        """
        if not await self._initialize_playwright():
            return None

        page = None
        try:
            page = await self.browser.new_page()

            # Set headers and navigate
            await page.set_extra_http_headers(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    )
                }
            )

            logger.info(f"Extracting content from: {url}")
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=15000
            )

            if not response or response.status >= 400:
                logger.error(
                    f"Failed to load page: {url} (status: "
                    f"{response.status if response else 'timeout'})"
                )
                return None

            # Wait for content to load
            await page.wait_for_timeout(2000)

            # Extract page metadata
            title = await page.title()

            # Try to get meta description
            description = ""
            try:
                desc_element = await page.query_selector('meta[name="description"]')
                if desc_element:
                    description = await desc_element.get_attribute("content") or ""
            except Exception:
                pass

            # Extract main content
            content = await self._extract_main_content(page)

            # Parse domain for trust assessment
            domain = urlparse(url).netloc.lower()
            is_trusted = any(trusted in domain for trusted in self.trusted_domains)

            # Get timestamp
            timestamp = datetime.now().isoformat()

            result = {
                "url": url,
                "title": title,
                "description": description,
                "content": content[: self.max_content_length] if content else "",
                "domain": domain,
                "is_trusted": is_trusted,
                "timestamp": timestamp,
                "content_length": len(content) if content else 0,
            }

            logger.info(
                f"Extracted {len(content) if content else 0} characters from {domain}"
            )
            return result

        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return None
        finally:
            if page:
                await page.close()

    async def _extract_main_content(self, page: Page) -> str:
        """Extract main content from a web page."""
        content_selectors = [
            "main",
            "article",
            ".content",
            ".main-content",
            ".post-content",
            ".entry-content",
            "#content",
            ".markdown-body",  # GitHub
            ".mw-parser-output",  # Wikipedia
            ".answer",  # Stack Overflow
        ]

        # Try each selector to find the main content
        for selector in content_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    content = await element.inner_text()
                    if content and len(content.strip()) > 100:
                        return content.strip()
            except Exception:
                continue

        # Fallback to body content, cleaned up
        try:
            # Remove script, style, nav, header, footer elements
            await page.evaluate(
                """
                () => {
                    const elementsToRemove = document.querySelectorAll(
                        'script, style, nav, header, footer, .nav, .navbar, ' +
                        '.header, .footer, .sidebar'
                    );
                    elementsToRemove.forEach(el => el.remove());
                }
            """
            )

            body = await page.query_selector("body")
            if body:
                content = await body.inner_text()
                # Clean up whitespace
                content = re.sub(r"\n\s*\n", "\n\n", content)
                content = re.sub(r" +", " ", content)
                return content.strip()
        except Exception as e:
            logger.error(f"Error extracting body content: {e}")

        return ""

    async def assess_content_quality(
        self, content_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess the quality of extracted content using LLM.

        Args:
            content_data: Content data with text and metadata

        Returns:
            Quality assessment with score and reasoning
        """
        try:
            prompt = f"""
Please assess the quality and reliability of this web content for "
"inclusion in a knowledge base:

Title: {content_data.get('title', 'N/A')}
Domain: {content_data.get('domain', 'N/A')}
Is Trusted Domain: {content_data.get('is_trusted', False)}
Content Length: {content_data.get('content_length', 0)} characters

Content Sample (first 500 chars):
{content_data.get('content', '')[:500]}...

Please evaluate on a scale of 0.0 to 1.0 based on:
1. Factual accuracy and reliability
2. Information completeness
3. Source credibility
4. Content structure and clarity
5. Relevance and usefulness

Respond in JSON format:
{{
    "score": 0.0-1.0,
    "reasoning": "Brief explanation of the assessment",
    "recommendation": "store|review|reject",
    "key_topics": ["list", "of", "main", "topics"],
    "reliability_factors": {{
        "trusted_domain": true/false,
        "content_quality": "high/medium/low",
        "information_density": "high/medium/low"
    }}
}}
"""

            response = await self.llm.chat([{"role": "user", "content": prompt}])

            # Try to parse JSON response
            try:
                assessment = json.loads(response)
                # Ensure score is within valid range
                score = max(0.0, min(1.0, float(assessment.get("score", 0.5))))
                assessment["score"] = score
                return assessment
            except json.JSONDecodeError:
                # Fallback assessment
                logger.warning(
                    "Could not parse quality assessment JSON, using fallback"
                )
                return {
                    "score": 0.6 if content_data.get("is_trusted") else 0.4,
                    "reasoning": (
                        "Automatic assessment - LLM response could not be parsed"
                    ),
                    "recommendation": "review",
                    "key_topics": [],
                    "reliability_factors": {
                        "trusted_domain": content_data.get("is_trusted", False),
                        "content_quality": "medium",
                        "information_density": "medium",
                    },
                }

        except Exception as e:
            logger.error(f"Error assessing content quality: {e}")
            return {
                "score": 0.3,
                "reasoning": f"Error during assessment: {str(e)}",
                "recommendation": "review",
                "key_topics": [],
                "reliability_factors": {
                    "trusted_domain": False,
                    "content_quality": "unknown",
                    "information_density": "unknown",
                },
            }

    async def store_in_knowledge_base(
        self, content_data: Dict[str, Any], assessment: Dict[str, Any]
    ) -> bool:
        """Store quality content in the knowledge base.

        Args:
            content_data: Content data to store
            assessment: Quality assessment results

        Returns:
            True if stored successfully
        """
        try:
            # Prepare document for storage
            document_content = f"""
Title: {content_data.get('title', 'Untitled')}
Source: {content_data.get('url', 'Unknown')}
Domain: {content_data.get('domain', 'Unknown')}
Retrieved: {content_data.get('timestamp', 'Unknown')}

{content_data.get('content', '')}
"""

            metadata = {
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

            # Store in knowledge base
            success = self.knowledge_base.add_document(document_content, metadata)

            if success:
                logger.info(
                    f"Stored content from {content_data.get('domain')} in "
                    "knowledge base"
                )
                return True
            else:
                logger.error(f"Failed to store content from {content_data.get('url')}")
                return False

        except Exception as e:
            logger.error(f"Error storing content in knowledge base: {e}")
            return False

    async def research_query(
        self, query: str, store_quality_content: bool = None
    ) -> Dict[str, Any]:
        """Research a query by searching the web and extracting content.

        Args:
            query: Research query
            store_quality_content: Whether to auto-store quality content

        Returns:
            Research results with sources and assessments
        """
        if not self.enabled:
            return {"enabled": False, "message": "Librarian Assistant is disabled"}

        if store_quality_content is None:
            store_quality_content = self.auto_store_quality

        research_results = {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "search_results": [],
            "content_extracted": [],
            "stored_in_kb": [],
            "summary": "",
            "sources": [],
        }

        try:
            # Step 1: Search for relevant URLs
            logger.info(f"Researching query: {query}")
            search_results = await self.search_web(query)
            research_results["search_results"] = search_results

            if not search_results:
                research_results["summary"] = "No search results found for the query."
                return research_results

            # Step 2: Extract content from top results
            extracted_content = []
            for result in search_results[
                :3
            ]:  # Limit to top 3 results for detailed extraction
                content = await self.extract_content(result["url"])
                if content:
                    # Assess content quality
                    assessment = await self.assess_content_quality(content)
                    content["quality_assessment"] = assessment

                    extracted_content.append(content)

                    # Store high-quality content if enabled
                    if (
                        store_quality_content
                        and assessment.get("score", 0) >= self.quality_threshold
                        and assessment.get("recommendation") == "store"
                    ):
                        stored = await self.store_in_knowledge_base(content, assessment)
                        if stored:
                            research_results["stored_in_kb"].append(
                                {
                                    "url": content["url"],
                                    "title": content["title"],
                                    "quality_score": assessment.get("score", 0),
                                }
                            )

            research_results["content_extracted"] = extracted_content

            # Step 3: Create summary with sources
            if extracted_content:
                summary = await self._create_research_summary(query, extracted_content)
                research_results["summary"] = summary

                # Collect sources
                sources = []
                for content in extracted_content:
                    sources.append(
                        {
                            "title": content["title"],
                            "url": content["url"],
                            "domain": content["domain"],
                            "is_trusted": content["is_trusted"],
                            "quality_score": content.get("quality_assessment", {}).get(
                                "score", 0
                            ),
                        }
                    )
                research_results["sources"] = sources

            logger.info(
                f"Research completed: {len(extracted_content)} sources analyzed, "
                f"{len(research_results['stored_in_kb'])} stored in KB"
            )

        except Exception as e:
            logger.error(f"Error during research: {e}")
            research_results["error"] = str(e)
        finally:
            # Clean up Playwright resources
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
Based on the following web research results for the query \"{query}\", "
"please provide a comprehensive summary that:

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
            logger.error(f"Error creating research summary: {e}")
            return f"Research completed but summary generation failed: {str(e)}"


# Singleton instance
_librarian_assistant = None


def get_librarian_assistant() -> LibrarianAssistantAgent:
    """Get the singleton Librarian Assistant Agent instance.

    Returns:
        The Librarian Assistant Agent instance
    """
    global _librarian_assistant
    if _librarian_assistant is None:
        _librarian_assistant = LibrarianAssistantAgent()
    return _librarian_assistant
