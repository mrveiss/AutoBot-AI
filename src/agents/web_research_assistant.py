"""
Web Research Assistant for AutoBot
Handles web research queries and integrates findings into knowledge base
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List
from src.constants.network_constants import NetworkConstants

try:
    from src.agents.advanced_web_research import AdvancedWebResearcher

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
        self.config = config or {}
        self.search_cache = {}  # Cache for recent searches
        self.quality_threshold = 0.7  # Minimum quality score for KB storage
        self.use_advanced_research = ADVANCED_RESEARCH_AVAILABLE and self.config.get(
            "enable_advanced_research", False
        )
        self.advanced_researcher = None

    async def research_query(self, query: str) -> Dict[str, Any]:
        """
        Research a query on the web and return structured results
        """
        logger.info(f"Starting web research for query: {query}")

        # Check cache first
        if query in self.search_cache:
            logger.info(f"Returning cached results for query: {query}")
            cached_result = self.search_cache[query]
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
            logger.error(f"Web research failed for query {query}: {str(e)}")
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
        logger.info(f"Using advanced web research for: {query}")

        if not self.advanced_researcher:
            self.advanced_researcher = AdvancedWebResearcher(self.config)
            await self.advanced_researcher.initialize()

        # Use advanced researcher
        search_results = await self.advanced_researcher.search_web(query, max_results=8)

        if search_results.get("status") == "success":
            # Convert to expected format
            processed_results = self._convert_advanced_results(search_results, query)
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
        logger.info(f"Using basic web research for: {query}")

        # Simulate web search (in a real implementation, this would use
        # search APIs or web scraping)
        search_results = await self._perform_web_search(query)

        # Process and filter results
        processed_results = await self._process_search_results(search_results, query)

        # Cache results
        self.search_cache[query] = processed_results

        logger.info(
            f"Web research completed for query: {query}, "
            f"found {len(processed_results.get('sources', []))} sources"
        )

        processed_results["research_method"] = "basic"
        return processed_results

    async def _perform_web_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Perform actual web search (placeholder implementation)
        In a real implementation, this would use search APIs
        """
        # Simulate search delay
        await asyncio.sleep(0.5)

        # Return mock search results based on query content
        if "network scan" in query.lower() or "nmap" in query.lower():
            return [
                {
                    "title": "Network Scanning with Nmap - Complete Guide",
                    "url": "https://example.com/nmap-guide",
                    "snippet": (
                        "Comprehensive guide to network scanning using Nmap, "
                        "including installation, basic commands, and advanced "
                        "techniques..."
                    ),
                    "domain": "example.com",
                    "content": self._get_nmap_content(),
                },
                {
                    "title": "Top Network Scanning Tools for Linux",
                    "url": "https://security.example.com/network-tools",
                    "snippet": (
                        "Review of the best network scanning tools including "
                        "Nmap, Masscan, and Zmap for penetration testing..."
                    ),
                    "domain": "security.example.com",
                    "content": self._get_network_tools_content(),
                },
            ]
        elif "forensics" in query.lower() or "steganography" in query.lower():
            return [
                {
                    "title": "Digital Forensics Tools and Techniques",
                    "url": "https://forensics.example.com/tools",
                    "snippet": (
                        "Overview of digital forensics tools including binwalk, "
                        "foremost, and steghide for evidence analysis..."
                    ),
                    "domain": "forensics.example.com",
                    "content": self._get_forensics_content(),
                }
            ]
        else:
            # Generic placeholder results
            return [
                {
                    "title": f"Information about {query}",
                    "url": "https://example.com/info",
                    "snippet": (
                        f"General information and resources related to {query}..."
                    ),
                    "domain": "example.com",
                    "content": f"This is general content about {query}. "
                    "It includes basic information and common use cases.",
                }
            ]

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

    def _get_nmap_content(self) -> str:
        """Mock nmap content"""
        return """
        Nmap (Network Mapper) is a powerful network discovery and \
security auditing tool.

        Installation:
        - Ubuntu/Debian: sudo apt-get install nmap
        - CentOS/RHEL: sudo yum install nmap
        - Arch: sudo pacman -S nmap

        Basic Usage:
        - nmap target - Basic scan
        - nmap -sS target - SYN scan (stealth)
        - nmap -sV target - Service version detection
        - nmap -O target - OS detection
        - nmap -A target - Aggressive scan

        Common Options:
        - -p: Specify ports (e.g., -p 80,443 or -p-)
        - -sU: UDP scan
        - -T: Timing template (0-5)
        - -oA: Output in all formats

        Advanced Features:
        - NSE scripts for vulnerability detection
        - Firewall evasion techniques
        - Custom packet crafting
        """

    def _get_network_tools_content(self) -> str:
        """Mock network tools content"""
        return """
        Top Network Scanning Tools for Security Professionals:

        1. Nmap - The gold standard for network discovery
        2. Masscan - Ultra-fast port scanner
        3. Zmap - Internet-wide network scanner
        4. Netcat - Network Swiss Army knife
        5. Wireshark - Network protocol analyzer

        Each tool has specific use cases and advantages for different
        types of network analysis and security assessments.
        """

    def _get_forensics_content(self) -> str:
        """Mock forensics content"""
        return """
        Digital Forensics Tools Overview:

        File Analysis:
        - binwalk: Firmware and file system analysis
        - foremost: File carving and recovery
        - scalpel: Advanced file carving

        Steganography:
        - steghide: Hide/extract data in images
        - outguess: JPEG steganography
        - stegsolve: Image analysis tool

        Memory Analysis:
        - volatility: Memory dump analysis framework
        - rekall: Advanced memory analysis

        Network Forensics:
        - tcpdump: Packet capture
        - wireshark: Packet analysis
        """

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
                    logger.error(f"Failed to store source in KB: {str(e)}")

            research_results["kb_storage_count"] = stored_count
            logger.info(f"Stored {stored_count} sources in knowledge base")

        return research_results

    def _format_for_kb(self, source: Dict[str, Any], query: str) -> str:
        """
        Format source content for knowledge base storage
        """
        title = source["title"]
        content = source["content"]
        url = source["url"]

        formatted_content = """
Title: {title}
Source: {url}
Query Context: {query}

Content:
{content}

Quality Score: {source['quality_score']}
Relevance Score: {source['relevance']}
"""

        return formatted_content.strip()

    def clear_cache(self):
        """Clear the search cache"""
        self.search_cache.clear()
        logger.info("Web research cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "cached_queries": len(self.search_cache),
            "cache_keys": list(self.search_cache.keys()),
        }
