#!/usr/bin/env python3
"""
Research Agent API for AutoBot
Provides web research capabilities for multi-agent workflows
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.constants.network_constants import NetworkConstants

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ResearchRequest(BaseModel):
    query: str
    focus: str = "general"
    max_results: int = 5
    include_installation: bool = False


class ResearchResult(BaseModel):
    title: str
    url: str
    content: str
    relevance_score: float
    source_type: str  # "documentation", "tutorial", "forum", "official"


class ResearchResponse(BaseModel):
    success: bool
    query: str
    results: List[ResearchResult]
    summary: str
    execution_time: float
    sources_count: int


@dataclass
class WebPage:
    url: str
    title: str
    content: str
    links: List[str]
    source_type: str


class ResearchAgent:
    """
    Research Agent that performs web research for complex queries.

    This agent simulates Playwright-based web scraping and research
    capabilities that would be available in the Docker container.
    """

    def __init__(self):
        self.app = FastAPI(title="AutoBot Research Agent", version="1.0.0")
        self.session: Optional[aiohttp.ClientSession] = None

        # Setup routes
        self.setup_routes()

        # Mock data for demonstration (in real implementation, this would use Playwright)
        self.mock_research_data = {
            "network scanning tools": {
                "nmap": {
                    "title": "Nmap - Network Discovery and Security Auditing",
                    "url": "https://nmap.org/",
                    "content": "Nmap is a free and open source utility for network discovery and security auditing. Features include host discovery, port scanning, version detection, and OS detection.",
                    "installation": "sudo apt-get install nmap",
                    "usage": "nmap -sS -O target_ip",
                },
                "masscan": {
                    "title": "Masscan - Fast Port Scanner",
                    "url": "https://github.com/robertdavidgraham/masscan",
                    "content": "Masscan is a TCP port scanner that can scan the entire Internet in under 6 minutes. It's designed to be fast and efficient for large-scale scanning.",
                    "installation": "sudo apt-get install masscan",
                    "usage": "masscan -p1-65535 192.168.1.0/24 --rate=1000",
                },
                "zmap": {
                    "title": "ZMap - Fast Internet-wide Network Scanner",
                    "url": "https://zmap.io/",
                    "content": "ZMap is a fast single packet network scanner designed for Internet-wide network surveys. It can scan the entire Internet in about 45 minutes.",
                    "installation": "sudo apt-get install zmap",
                    "usage": "zmap -p 443 -o results.txt",
                },
            }
        }

    def setup_routes(self):
        """Setup FastAPI routes for the research agent."""

        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy", "agent": "research", "version": "1.0.0"}

        @self.app.post("/research", response_model=ResearchResponse)
        async def research_endpoint(request: ResearchRequest):
            return await self.perform_research(request)

        @self.app.post("/research/tools")
        async def research_tools(request: ResearchRequest):
            """Specialized endpoint for researching tools and software."""
            return await self.research_specific_tools(request)

        @self.app.get("/research/installation/{tool_name}")
        async def get_installation_guide(tool_name: str):
            """Get detailed installation guide for a specific tool."""
            return await self.get_tool_installation_guide(tool_name)

    async def perform_research(self, request: ResearchRequest) -> ResearchResponse:
        """Perform web research based on the request parameters."""
        start_time = time.time()

        logger.info(
            f"Starting research for query: '{request.query}' with focus: '{request.focus}'"
        )

        try:
            # In real implementation, this would use Playwright to scrape web pages
            results = await self._mock_web_research(
                request.query, request.focus, request.max_results
            )

            # Generate summary
            summary = self._generate_research_summary(results, request.query)

            execution_time = time.time() - start_time

            return ResearchResponse(
                success=True,
                query=request.query,
                results=results,
                summary=summary,
                execution_time=execution_time,
                sources_count=len(results),
            )

        except Exception as e:
            logger.error(f"Research failed for query '{request.query}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Research failed: {str(e)}")

    async def research_specific_tools(self, request: ResearchRequest) -> Dict[str, Any]:
        """Research specific tools with installation and usage information."""
        query_lower = request.query.lower()

        # Check if this matches our mock data
        if "network scanning" in query_lower or "network scan" in query_lower:
            tools_data = self.mock_research_data["network scanning tools"]

            research_results = []
            for tool_name, tool_info in tools_data.items():
                result = ResearchResult(
                    title=tool_info["title"],
                    url=tool_info["url"],
                    content=tool_info["content"],
                    relevance_score=0.95,
                    source_type="official",
                )
                research_results.append(result)

            return {
                "success": True,
                "tools_found": list(tools_data.keys()),
                "detailed_info": tools_data,
                "research_results": [r.dict() for r in research_results],
                "recommendation": "nmap is the most versatile and widely-used network scanning tool",
                "summary": f"Found {len(tools_data)} network scanning tools: {', '.join(tools_data.keys())}. Recommendation: nmap is the most versatile and widely-used network scanning tool.",
            }

        # Fallback to general research
        return await self.perform_research(request)

    async def get_tool_installation_guide(self, tool_name: str) -> Dict[str, Any]:
        """Get detailed installation guide for a specific tool."""
        tool_lower = tool_name.lower()

        # Check mock data
        for category_data in self.mock_research_data.values():
            if tool_lower in category_data:
                tool_info = category_data[tool_lower]
                return {
                    "success": True,
                    "tool_name": tool_name,
                    "installation_command": tool_info.get(
                        "installation", "Not available"
                    ),
                    "usage_example": tool_info.get("usage", "Not available"),
                    "description": tool_info.get("content", ""),
                    "official_url": tool_info.get("url", ""),
                    "prerequisites": self._get_tool_prerequisites(tool_name),
                    "verification_command": self._get_verification_command(tool_name),
                }

        # Tool not found in mock data
        return {
            "success": False,
            "tool_name": tool_name,
            "error": "Tool information not available in research database",
        }

    def _get_tool_prerequisites(self, tool_name: str) -> List[str]:
        """Get prerequisites for tool installation."""
        prereqs = {
            "nmap": ["sudo privileges", "network access"],
            "masscan": [
                "sudo privileges",
                "build-essential (if compiling from source)",
            ],
            "zmap": ["sudo privileges", "libgmp3-dev libpcap-dev"],
        }
        return prereqs.get(tool_name.lower(), ["sudo privileges"])

    def _get_verification_command(self, tool_name: str) -> str:
        """Get command to verify tool installation."""
        verification = {
            "nmap": "nmap --version",
            "masscan": "masscan --version",
            "zmap": "zmap --version",
        }
        return verification.get(tool_name.lower(), f"{tool_name} --version")

    async def _mock_web_research(
        self, query: str, focus: str, max_results: int
    ) -> List[ResearchResult]:
        """Mock web research that simulates Playwright scraping."""
        # Simulate research delay
        await asyncio.sleep(0.5)

        results = []

        # Generate mock results based on query
        if "network scan" in query.lower():
            base_results = [
                ResearchResult(
                    title="Top Network Scanning Tools 2024",
                    url="https://example.com/network-tools-2024",
                    content="Comprehensive guide to network scanning tools including Nmap, Masscan, and Zmap with installation instructions and usage examples.",
                    relevance_score=0.95,
                    source_type="tutorial",
                ),
                ResearchResult(
                    title="Nmap Official Documentation",
                    url="https://nmap.org/book/",
                    content="Official documentation for Nmap network scanner including installation guide, command reference, and scripting examples.",
                    relevance_score=0.92,
                    source_type="documentation",
                ),
                ResearchResult(
                    title="Network Security Scanning Best Practices",
                    url="https://example.com/security-scanning-practices",
                    content="Best practices for ethical network scanning, including legal considerations and responsible disclosure.",
                    relevance_score=0.88,
                    source_type="tutorial",
                ),
            ]
            results.extend(base_results[:max_results])
        else:
            # Generic research results
            for i in range(min(max_results, 3)):
                result = ResearchResult(
                    title=f"Research Result {i+1} for '{query}'",
                    url=f"https://example.com/result-{i+1}",
                    content=f"Mock research content related to '{query}' with {focus} focus. This would contain actual web-scraped content in the real implementation.",
                    relevance_score=0.85 - (i * 0.05),
                    source_type="general",
                )
                results.append(result)

        return results

    def _generate_research_summary(
        self, results: List[ResearchResult], query: str
    ) -> str:
        """Generate a summary of research results."""
        if not results:
            return f"No relevant results found for '{query}'"

        high_quality_results = [r for r in results if r.relevance_score > 0.8]

        if "network scan" in query.lower():
            return (
                f"Found {len(results)} relevant resources about network scanning tools. "
                "Key tools identified include Nmap (most popular), Masscan (fastest), and Zmap (Internet-scale). "
                "All tools have detailed installation guides and usage examples available. "
                "Nmap is recommended for beginners due to its comprehensive documentation and versatility."
            )

        return (
            f"Research completed for '{query}' with {len(results)} results found. "
            f"{len(high_quality_results)} high-quality sources identified. "
            f"Results include {', '.join(set(r.source_type for r in results))} sources."
        )

    async def start_server(self, host: str = "0.0.0.0", port: int = 8005):
        """Start the research agent server."""
        import uvicorn

        logger.info(f"Starting Research Agent server on {host}:{port}")
        uvicorn.run(self.app, host=host, port=port)


# Create global research agent instance
research_agent = ResearchAgent()

if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Test mode - run sample research
        async def test_research():
            request = ResearchRequest(
                query="network scanning tools",
                focus="installation_usage",
                max_results=3,
            )

            print("🔍 Testing Research Agent")
            print("=" * 40)

            # Test general research
            result = await research_agent.perform_research(request)
            print(f"Query: {result.query}")
            print(f"Results: {result.sources_count}")
            print(f"Summary: {result.summary}")
            print()

            # Test tool-specific research
            tools_result = await research_agent.research_specific_tools(request)
            print("Tool-specific research:")
            print(f"Tools found: {tools_result.get('tools_found', [])}")
            print(f"Recommendation: {tools_result.get('recommendation', 'N/A')}")
            print()

            # Test installation guide
            install_guide = await research_agent.get_tool_installation_guide("nmap")
            print("Installation guide for nmap:")
            print(f"Command: {install_guide.get('installation_command', 'N/A')}")
            print(f"Usage: {install_guide.get('usage_example', 'N/A')}")
            print(f"Prerequisites: {install_guide.get('prerequisites', [])}")

        asyncio.run(test_research())
    else:
        # Start the server
        asyncio.run(research_agent.start_server())
