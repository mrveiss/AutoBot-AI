# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Web Research Assistant for AutoBot
Handles web research queries and integrates findings into knowledge base
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List


try:
    from agents.advanced_web_research import AdvancedWebResearcher

    ADVANCED_RESEARCH_AVAILABLE = True
except ImportError:
    ADVANCED_RESEARCH_AVAILABLE = False
    logging.warning("Advanced web research not available (missing dependencies)")

logger = logging.getLogger(__name__)


class WebResearchAssistant:
    """
    Assistant that performs web research and integrates results with KB
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize web research assistant with config and search cache."""
        self.config = config or {}
        self.search_cache = {}  # Cache for recent searches
        self._cache_lock = asyncio.Lock()  # Lock for search_cache access
        self.quality_threshold = 0.7  # Minimum quality score for KB storage
        # Enable advanced research by default when available
        self.use_advanced_research = ADVANCED_RESEARCH_AVAILABLE and self.config.get(
            "enable_advanced_research", True
        )
        self.advanced_researcher = None

    async def research_query(self, query: str) -> Dict[str, Any]:
        """
        Research a query on the web and return structured results (thread-safe)
        """
        logger.info("Starting web research for query: %s", query)

        # Check cache first (thread-safe)
        async with self._cache_lock:
            if query in self.search_cache:
                logger.info("Returning cached results for query: %s", query)
                cached_result = dict(self.search_cache[query])  # Copy
                cached_result["from_cache"] = True
                return cached_result

        try:
            # Use advanced research if available and enabled
            if self.use_advanced_research:
                return await self._advanced_research(query)
            else:
                # Fallback to basic research
                return await self._basic_research(query)

        except Exception as e:
            logger.error("Web research failed for query %s: %s", query, str(e))
            return {
                "status": "error",
                "query": query,
                "error": str(e),
                "sources": [],
                "summary": None,
                "timestamp": datetime.now().isoformat(),
            }

    async def _advanced_research(self, query: str) -> Dict[str, Any]:
        """Perform advanced web research with anti-detection"""
        logger.info("Using advanced web research for: %s", query)

        if not self.advanced_researcher:
            self.advanced_researcher = AdvancedWebResearcher(self.config)
            await self.advanced_researcher.initialize()

        # Use advanced researcher
        search_results = await self.advanced_researcher.search_web(query, max_results=8)

        if search_results.get("status") == "success":
            # Convert to expected format
            processed_results = self._convert_advanced_results(search_results, query)
            # Cache results (thread-safe)
            async with self._cache_lock:
                self.search_cache[query] = processed_results
            return processed_results
        else:
            # Fallback to basic research
            logger.warning("Advanced research failed, falling back to basic research")
            return await self._basic_research(query)

    def _convert_advanced_results(
        self, search_results: Dict[str, Any], query: str
    ) -> Dict[str, Any]:
        """Convert advanced research results to standard format"""
        sources = []

        for result in search_results.get("results", []):
            source = {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "domain": result.get("domain", ""),
                "snippet": result.get("snippet", ""),
                "content": result.get("content", ""),
                "quality_score": result.get("quality_score", 0.5),
                "relevance": result.get("relevance_score", 0.5),
                "search_engine": result.get("search_engine", "unknown"),
                "timestamp": result.get("timestamp", datetime.now().isoformat()),
            }
            sources.append(source)

        # Generate summary
        summary = self._generate_summary(sources, query)

        # Identify high-quality sources for KB storage
        kb_worthy_sources = [
            source
            for source in sources
            if source["quality_score"] >= self.quality_threshold
        ]

        return {
            "status": "success",
            "query": query,
            "sources": sources,
            "summary": summary,
            "stored_in_kb": kb_worthy_sources,
            "search_engines_used": search_results.get("search_engines_used", 0),
            "total_found": search_results.get("total_found", 0),
            "timestamp": datetime.now().isoformat(),
            "from_cache": False,
            "research_method": "advanced",
        }

    async def _basic_research(self, query: str) -> Dict[str, Any]:
        """Fallback basic research method"""
        logger.info("Using basic web research for: %s", query)

        # Simulate web search (in a real implementation, this would use
        # search APIs or web scraping)
        search_results = await self._perform_web_search(query)

        # Process and filter results
        processed_results = await self._process_search_results(search_results, query)

        # Cache results (thread-safe)
        async with self._cache_lock:
            self.search_cache[query] = processed_results

        logger.info(
            f"Web research completed for query: {query}, "
            f"found {len(processed_results.get('sources', []))} sources"
        )

        processed_results["research_method"] = "basic"
        return processed_results

    async def _perform_web_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Perform actual web search using AdvancedWebResearcher.
        Falls back to the advanced researcher even in basic mode.
        """
        try:
            # Initialize advanced researcher if not already done
            if not self.advanced_researcher:
                self.advanced_researcher = AdvancedWebResearcher(self.config)
                await self.advanced_researcher.initialize()

            # Use advanced researcher for actual web search
            search_results = await self.advanced_researcher.search_web(query, max_results=5)

            if search_results.get("status") == "success":
                # Convert to list format expected by _process_search_results
                results = []
                for result in search_results.get("results", []):
                    results.append({
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "snippet": result.get("snippet", ""),
                        "domain": result.get("domain", ""),
                        "content": result.get("content", result.get("snippet", "")),
                    })
                return results
            else:
                logger.warning(
                    "Web search returned non-success status: %s",
                    search_results.get("error", "Unknown error")
                )
                return []

        except Exception as e:
            logger.error("Web search failed: %s", str(e))
            return []

    async def _process_search_results(
        self, search_results: List[Dict[str, Any]], query: str
    ) -> Dict[str, Any]:
        """
        Process raw search results into structured format
        """
        processed_sources = []

        for result in search_results:
            # Score result quality
            quality_score = self._calculate_quality_score(result, query)

            processed_source = {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "domain": result.get("domain", ""),
                "snippet": result.get("snippet", ""),
                "content": result.get("content", ""),
                "quality_score": quality_score,
                "relevance": self._calculate_relevance(result, query),
                "timestamp": datetime.now().isoformat(),
            }

            processed_sources.append(processed_source)

        # Sort by quality score
        processed_sources.sort(key=lambda x: x["quality_score"], reverse=True)

        # Generate summary
        summary = self._generate_summary(processed_sources, query)

        # Identify high-quality sources for KB storage
        kb_worthy_sources = [
            source
            for source in processed_sources
            if source["quality_score"] >= self.quality_threshold
        ]

        return {
            "status": "success",
            "query": query,
            "sources": processed_sources,
            "summary": summary,
            "stored_in_kb": kb_worthy_sources,
            "timestamp": datetime.now().isoformat(),
            "from_cache": False,
        }

    def _calculate_quality_score(self, result: Dict[str, Any], query: str) -> float:
        """
        Calculate quality score for a search result
        """
        score = 0.5  # Base score

        # Domain reputation (simplified)
        trusted_domains = [
            "github.com",
            "stackoverflow.com",
            "docs.python.org",
            "ubuntu.com",
            "redhat.com",
            "debian.org",
            "archlinux.org",
        ]

        domain = result.get("domain", "")
        if any(trusted in domain for trusted in trusted_domains):
            score += 0.3

        # Content length (more content generally better)
        content_length = len(result.get("content", ""))
        if content_length > 1000:
            score += 0.2
        elif content_length > 500:
            score += 0.1

        # Query term presence in title
        title = result.get("title", "").lower()
        query_terms = query.lower().split()
        title_matches = sum(1 for term in query_terms if term in title)
        score += (title_matches / len(query_terms)) * 0.2

        return min(score, 1.0)  # Cap at 1.0

    def _calculate_relevance(self, result: Dict[str, Any], query: str) -> float:
        """
        Calculate relevance score for a search result
        """
        query_terms = set(query.lower().split())

        # Check title relevance
        title_terms = set(result.get("title", "").lower().split())
        title_overlap = len(query_terms & title_terms) / len(query_terms)

        # Check content relevance
        content_terms = set(result.get("content", "").lower().split())
        content_overlap = len(query_terms & content_terms) / len(query_terms)

        # Weighted average
        relevance = (title_overlap * 0.6) + (content_overlap * 0.4)
        return relevance

    def _generate_summary(self, sources: List[Dict[str, Any]], query: str) -> str:
        """
        Generate a summary of search results
        """
        if not sources:
            return "No relevant information found."

        top_sources = sources[:3]  # Use top 3 sources

        summary_parts = [
            f"Based on web research for '{query}', here are the key findings:"
        ]

        for i, source in enumerate(top_sources, 1):
            title = source["title"]
            snippet = (
                source["snippet"][:200] + "..."
                if len(source["snippet"]) > 200
                else source["snippet"]
            )

            summary_parts.append(f"{i}. {title}: {snippet}")

        if len(sources) > 3:
            summary_parts.append(f"({len(sources) - 3} additional sources found)")

        return "\n\n".join(summary_parts)

    async def search_and_store_knowledge(
        self, query: str, knowledge_base
    ) -> Dict[str, Any]:
        """
        Research query and automatically store high-quality results in KB
        """
        research_results = await self.research_query(query)

        if research_results.get("status") == "success":
            stored_count = 0

            # Store high-quality sources in knowledge base
            for source in research_results.get("stored_in_kb", []):
                try:
                    # Format content for knowledge base storage
                    kb_content = self._format_for_kb(source, query)

                    # Add to knowledge base
                    await knowledge_base.add_document(
                        content=kb_content,
                        metadata={
                            "source": "web_research",
                            "query": query,
                            "url": source["url"],
                            "title": source["title"],
                            "quality_score": source["quality_score"],
                            "timestamp": source["timestamp"],
                        },
                    )
                    stored_count += 1

                except Exception as e:
                    logger.error("Failed to store source in KB: %s", str(e))

            research_results["kb_storage_count"] = stored_count
            logger.info("Stored %s sources in knowledge base", stored_count)

        return research_results

    def _format_for_kb(self, source: Dict[str, Any], query: str) -> str:
        """
        Format source content for knowledge base storage
        """
        title = source["title"]
        content = source["content"]
        url = source["url"]
        quality_score = source["quality_score"]
        relevance = source["relevance"]

        formatted_content = f"""
Title: {title}
Source: {url}
Query Context: {query}

Content:
{content}

Quality Score: {quality_score}
Relevance Score: {relevance}
"""

        return formatted_content.strip()

    async def clear_cache(self):
        """Clear the search cache (thread-safe)"""
        async with self._cache_lock:
            self.search_cache.clear()
        logger.info("Web research cache cleared")

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics (thread-safe)"""
        async with self._cache_lock:
            return {
                "cached_queries": len(self.search_cache),
                "cache_keys": list(self.search_cache.keys()),
            }
