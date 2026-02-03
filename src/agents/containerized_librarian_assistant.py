# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Containerized Librarian Assistant Agent for Web Research.

This agent performs web research using a Playwright service running in Docker container,
presents results with proper source attribution, and can store quality information
in the knowledge base for future reference.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.knowledge_base import KnowledgeBase
from src.llm_interface import LLMInterface
from src.config import config
from src.utils.http_client import get_http_client

from ..utils.service_registry import get_service_url

logger = logging.getLogger(__name__)


class ContainerizedLibrarianAssistant:
    """An agent that researches information using containerized Playwright service."""

    def __init__(self):
        """Initialize the Containerized Librarian Assistant Agent."""
        self.config = config
        self.knowledge_base = KnowledgeBase()
        self.llm = LLMInterface()

        # Configuration
        self.enabled = self.config.get_nested("librarian_assistant.enabled", True)
        self.playwright_service_url = self.config.get_nested(
            "librarian_assistant.playwright_service_url",
            get_service_url("playwright-vnc"),
        )
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

        # Trusted domains for content assessment
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

        # Use HTTP client singleton for requests to Playwright service
        self.http_client = get_http_client()

    async def _check_playwright_service(self) -> bool:
        """Check if Playwright service is available."""
        try:
            async with await self.http_client.get(f"{self.playwright_service_url}/health") as response:
                if response.status == 200:
                    logger.info("Playwright service is healthy")
                    return True
                else:
                    logger.error(
                        f"Playwright service unhealthy: status {response.status}"
                    )
                    return False
        except Exception as e:
            logger.error("Cannot reach Playwright service: %s", e)
            return False

    async def search_web(
        self, query: str, search_engine: str = "duckduckgo"
    ) -> List[Dict[str, Any]]:
        """Search the web for information using containerized Playwright service.

        Args:
            query: Search query
            search_engine: Which search engine to use

        Returns:
            List of search results with URLs and content
        """
        if not self.enabled:
            return []

        if not await self._check_playwright_service():
            logger.error("Playwright service not available")
            return []

        try:
            payload = {"query": query, "search_engine": search_engine}

            logger.info(
                f"Searching with {search_engine} via Playwright service: {query}"
            )

            async with await self.http_client.post(
                f"{self.playwright_service_url}/search", json=payload
            ) as response:
                if response.status != 200:
                    logger.error("Search request failed: status %s", response.status)
                    return []

                result = await response.json()

                if result.get("success"):
                    results = result.get("results", [])
                    logger.info("Found %s search results", len(results))
                    return results[: self.max_search_results]
                else:
                    logger.error(
                        f"Search failed: {result.get('error', 'Unknown error')}"
                    )
                    return []

        except Exception as e:
            logger.error("Error during web search: %s", e)
            return []

    async def extract_content(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract content from a web page using containerized Playwright.

        Args:
            url: URL to extract content from

        Returns:
            Dictionary containing extracted content and metadata
        """
        if not await self._check_playwright_service():
            return None

        try:
            payload = {"url": url}

            logger.info("Extracting content via Playwright service: %s", url)

            async with await self.http_client.post(
                f"{self.playwright_service_url}/extract", json=payload
            ) as response:
                if response.status != 200:
                    logger.error("Content extraction failed: status %s", response.status)
                    return None

                result = await response.json()

                if result.get("success"):
                    content_data = {
                        "url": result["url"],
                        "title": result["title"],
                        "description": result["description"],
                        "content": result["content"],
                        "domain": result["domain"],
                        "is_trusted": result["is_trusted"],
                        "timestamp": result["timestamp"],
                        "content_length": result["content_length"],
                    }

                    logger.info(
                        f"Extracted {result['content_length']} characters from "
                        f"{result['domain']}"
                    )
                    return content_data
                else:
                    logger.error(
                        "Content extraction failed: "
                        f"{result.get('error', 'Unknown error')}"
                    )
                    return None

        except Exception as e:
            logger.error("Error extracting content from %s: %s", url, e)
            return None

    def _build_fallback_assessment(
        self, content_data: Dict[str, Any], error_msg: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build fallback assessment when LLM fails (Issue #665: extracted helper)."""
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
        """Assess the quality of extracted content using LLM (Issue #665: uses extracted helper).

        Args:
            content_data: Content data with text and metadata

        Returns:
            Quality assessment with score and reasoning
        """
        try:
            prompt = """
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
    "key_topics": ["list", "o", "main", "topics"],
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
                logger.warning(
                    "Could not parse quality assessment JSON, using fallback"
                )
                return self._build_fallback_assessment(content_data)

        except Exception as e:
            logger.error("Error assessing content quality: %s", e)
            return self._build_fallback_assessment(content_data, str(e))

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
            document_content = """
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
                "stored_by": "containerized_librarian_assistant",
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
                logger.error("Failed to store content from %s", content_data.get('url'))
                return False

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
                stored_list.append({
                    "url": content["url"],
                    "title": content["title"],
                    "quality_score": assessment.get("score", 0),
                })
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
            return {
                "enabled": False,
                "message": "Containerized Librarian Assistant is disabled",
            }

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
            if not await self._check_playwright_service():
                research_results["error"] = "Playwright service not available"
                return research_results

            logger.info("Researching query: %s", query)
            search_results = await self.search_web(query)
            research_results["search_results"] = search_results

            if not search_results:
                research_results["summary"] = "No search results found for the query."
                return research_results

            # Extract content from top 3 results
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
                f"Research completed: {len(extracted_content)} sources analyzed, "
                f"{len(research_results['stored_in_kb'])} stored in KB"
            )

        except Exception as e:
            logger.error("Error during research: %s", e)
            research_results["error"] = str(e)

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

_containerized_librarian_assistant = None
_containerized_librarian_assistant_lock = threading.Lock()


def get_containerized_librarian_assistant() -> ContainerizedLibrarianAssistant:
    """Get the singleton Containerized Librarian Assistant Agent instance (thread-safe).

    Returns:
        The Containerized Librarian Assistant Agent instance
    """
    global _containerized_librarian_assistant
    if _containerized_librarian_assistant is None:
        with _containerized_librarian_assistant_lock:
            # Double-check after acquiring lock
            if _containerized_librarian_assistant is None:
                _containerized_librarian_assistant = ContainerizedLibrarianAssistant()
    return _containerized_librarian_assistant
