# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Librarian Assistant Agent for Web Research.

This agent performs web research using the Playwright service running on the
browser VM (.25), presents results with proper source attribution, and stores
quality information in the knowledge base for future reference.

Architecture: called by the orchestrator when local KB results are insufficient
or the query requires current/external data.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import config
from knowledge_base import KnowledgeBase
from llm_interface import LLMInterface

from autobot_shared.http_client import get_http_client

from ..utils.service_registry import get_service_url

logger = logging.getLogger(__name__)


class LibrarianAssistant:
    """An agent that researches information using the browser VM Playwright service."""

    def __init__(self):
        """Initialize the Librarian Assistant Agent."""
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
        """Check if browser VM Playwright service is available."""
        try:
            async with await self.http_client.get(
                f"{self.playwright_service_url}/health"
            ) as response:
                if response.status == 200:
                    logger.info("Playwright service is healthy")
                    return True
                else:
                    logger.error(
                        "Playwright service unhealthy: status %s", response.status
                    )
                    return False
        except Exception as e:
            logger.error("Cannot reach Playwright service: %s", e)
            return False

    async def search_web(
        self, query: str, search_engine: str = "duckduckgo"
    ) -> List[Dict[str, Any]]:
        """Search the web for information using the browser VM Playwright service.

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
                "Searching with %s via Playwright service: %s", search_engine, query
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
                        "Search failed: %s", result.get("error", "Unknown error")
                    )
                    return []

        except Exception as e:
            logger.error("Error during web search: %s", e)
            return []

    def _build_content_data(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Build content data dictionary from extraction result.

        Args:
            result: Raw result from Playwright extraction service

        Returns:
            Formatted content data dictionary. Issue #620.
        """
        return {
            "url": result["url"],
            "title": result["title"],
            "description": result["description"],
            "content": result["content"],
            "domain": result["domain"],
            "is_trusted": result["is_trusted"],
            "timestamp": result["timestamp"],
            "content_length": result["content_length"],
        }

    async def extract_content(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract content from a web page using the browser VM Playwright service.

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
                    logger.error(
                        "Content extraction failed: status %s", response.status
                    )
                    return None

                result = await response.json()

                if result.get("success"):
                    content_data = self._build_content_data(result)
                    logger.info(
                        "Extracted %s characters from %s",
                        result["content_length"],
                        result["domain"],
                    )
                    return content_data
                else:
                    logger.error(
                        "Content extraction failed: %s",
                        result.get("error", "Unknown error"),
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

    def _build_assessment_prompt(self, content_data: Dict[str, Any]) -> str:
        """Build the LLM prompt for content quality assessment.

        Args:
            content_data: Content data with text and metadata

        Returns:
            Formatted prompt string for LLM. Issue #620.
        """
        title = content_data.get("title", "N/A")
        domain = content_data.get("domain", "N/A")
        is_trusted = content_data.get("is_trusted", False)
        content_length = content_data.get("content_length", 0)
        content_sample = content_data.get("content", "")[:500]

        return (
            f"Please assess the quality and reliability of this web content for "
            f"inclusion in a knowledge base:\n\n"
            f"Title: {title}\n"
            f"Domain: {domain}\n"
            f"Is Trusted Domain: {is_trusted}\n"
            f"Content Length: {content_length} characters\n\n"
            f"Content Sample (first 500 chars):\n{content_sample}...\n\n"
            "Please evaluate on a scale of 0.0 to 1.0 based on:\n"
            "1. Factual accuracy and reliability\n"
            "2. Information completeness\n"
            "3. Source credibility\n"
            "4. Content structure and clarity\n"
            "5. Relevance and usefulness\n\n"
            "Respond in JSON format:\n"
            "{\n"
            '    "score": 0.0-1.0,\n'
            '    "reasoning": "Brief explanation of the assessment",\n'
            '    "recommendation": "store|review|reject",\n'
            '    "key_topics": ["list", "of", "main", "topics"],\n'
            '    "reliability_factors": {\n'
            '        "trusted_domain": true/false,\n'
            '        "content_quality": "high/medium/low",\n'
            '        "information_density": "high/medium/low"\n'
            "    }\n"
            "}"
        )

    def _parse_assessment_response(
        self, response: str, content_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse LLM response into assessment dictionary.

        Args:
            response: Raw LLM response string
            content_data: Original content data for fallback

        Returns:
            Parsed assessment dictionary. Issue #620.
        """
        try:
            assessment = json.loads(response)
            score = max(0.0, min(1.0, float(assessment.get("score", 0.5))))
            assessment["score"] = score
            return assessment
        except json.JSONDecodeError:
            logger.warning("Could not parse quality assessment JSON, using fallback")
            return self._build_fallback_assessment(content_data)

    async def assess_content_quality(
        self, content_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess the quality of extracted content using LLM. Issue #620.

        Args:
            content_data: Content data with text and metadata

        Returns:
            Quality assessment with score and reasoning
        """
        try:
            prompt = self._build_assessment_prompt(content_data)
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            return self._parse_assessment_response(response, content_data)
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
            document_content = (
                f"Title: {content_data.get('title', 'Untitled')}\n"
                f"Source: {content_data.get('url', 'Unknown')}\n"
                f"Domain: {content_data.get('domain', 'Unknown')}\n"
                f"Retrieved: {content_data.get('timestamp', 'Unknown')}\n\n"
                f"{content_data.get('content', '')}"
            )

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

            success = self.knowledge_base.add_document(document_content, metadata)

            if success:
                logger.info(
                    "Stored content from %s in knowledge base",
                    content_data.get("domain"),
                )
                return True
            else:
                logger.error("Failed to store content from %s", content_data.get("url"))
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

    def _create_empty_research_results(self, query: str) -> Dict[str, Any]:
        """Create empty research results structure. Issue #620.

        Args:
            query: The research query

        Returns:
            Empty research results dictionary
        """
        return {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "search_results": [],
            "content_extracted": [],
            "stored_in_kb": [],
            "summary": "",
            "sources": [],
        }

    async def _extract_and_process_results(
        self,
        search_results: List[Dict[str, Any]],
        store_quality_content: bool,
        stored_list: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Extract and process top search results. Issue #620.

        Args:
            search_results: List of search results
            store_quality_content: Whether to store quality content
            stored_list: List to append stored items to

        Returns:
            List of extracted content
        """
        extracted = []
        for result in search_results[:3]:
            content = await self._process_single_search_result(
                result, store_quality_content, stored_list
            )
            if content:
                extracted.append(content)
        return extracted

    async def research_query(
        self, query: str, store_quality_content: bool = None
    ) -> Dict[str, Any]:
        """Research a query by searching the web and extracting content. Issue #620.

        Args:
            query: Research query
            store_quality_content: Whether to auto-store quality content

        Returns:
            Research results with sources and assessments
        """
        if not self.enabled:
            return {
                "enabled": False,
                "message": "Librarian Assistant is disabled",
            }

        if store_quality_content is None:
            store_quality_content = self.auto_store_quality

        research_results = self._create_empty_research_results(query)

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

            extracted_content = await self._extract_and_process_results(
                search_results, store_quality_content, research_results["stored_in_kb"]
            )
            research_results["content_extracted"] = extracted_content

            await self._finalize_research_results(
                query, extracted_content, research_results
            )
        except Exception as e:
            logger.error("Error during research: %s", e)
            research_results["error"] = str(e)

        return research_results

    async def _finalize_research_results(
        self,
        query: str,
        extracted_content: List[Dict[str, Any]],
        research_results: Dict[str, Any],
    ) -> None:
        """Finalize research results with summary and sources. Issue #620.

        Args:
            query: The original research query
            extracted_content: List of extracted content items
            research_results: Results dict to update in place
        """
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

    async def _create_research_summary(
        self, query: str, content_list: List[Dict[str, Any]]
    ) -> str:
        """Create a summary of research findings."""
        try:
            source_contents = []
            for i, content in enumerate(content_list, 1):
                quality_info = content.get("quality_assessment", {})
                source_contents.append(
                    f"Source {i} - {content['title']} ({content['domain']})\n"
                    f"Quality Score: {quality_info.get('score', 'N/A')}\n"
                    f"Content: {content['content'][:800]}...\n"
                )

            combined_content = "\n---\n".join(source_contents)

            prompt = (
                f'Based on the following web research results for the query "{query}", '
                "please provide a comprehensive summary that:\n\n"
                "1. Synthesizes the key information found\n"
                "2. Clearly attributes information to sources\n"
                "3. Notes any contradictions or uncertainties\n"
                "4. Highlights the most reliable information\n\n"
                f"Research Results:\n{combined_content}\n\n"
                "Please format your response to include:\n"
                "- Main findings with source attribution\n"
                "- Key facts and concepts discovered\n"
                "- Source reliability assessment\n"
                "- Any limitations or gaps in the information\n\n"
                "Format sources as: [Source: Domain Name]"
            )

            summary = await self.llm.chat([{"role": "user", "content": prompt}])
            return summary

        except Exception as e:
            logger.error("Error creating research summary: %s", e)
            return f"Research completed but summary generation failed: {str(e)}"


# Singleton instance (thread-safe)
import threading

_librarian_assistant = None
_librarian_assistant_lock = threading.Lock()


def get_librarian_assistant() -> LibrarianAssistant:
    """Get the singleton Librarian Assistant Agent instance (thread-safe).

    Returns:
        The Librarian Assistant Agent instance
    """
    global _librarian_assistant
    if _librarian_assistant is None:
        with _librarian_assistant_lock:
            if _librarian_assistant is None:
                _librarian_assistant = LibrarianAssistant()
    return _librarian_assistant
