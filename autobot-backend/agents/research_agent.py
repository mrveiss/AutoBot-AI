#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Research Agent API for AutoBot
Provides web research capabilities for multi-agent workflows
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from agents.advanced_web_research import AdvancedWebResearcher
from constants.network_constants import NetworkConstants
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger

# Get centralized logger
logger = get_logger(__name__, "backend")


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

    This agent uses Playwright-based web scraping through the AdvancedWebResearcher
    to provide real web research capabilities.
    """

    def __init__(self):
        """Initialize research agent with FastAPI app and real web research."""
        self.app = FastAPI(title="AutoBot Research Agent", version="1.0.0")
        self._http_client = get_http_client()  # Use singleton HTTP client
        self._web_researcher = None  # Lazy-initialized AdvancedWebResearcher

        # Setup routes
        self.setup_routes()

        # Tool information database (static reference data, not mock research results)
        self._tool_reference_data = {
            "nmap": {
                "installation": "sudo apt-get install nmap",
                "usage": "nmap -sS -O target_ip",
                "verification": "nmap --version",
                "prerequisites": ["sudo privileges", "network access"],
            },
            "masscan": {
                "installation": "sudo apt-get install masscan",
                "usage": "masscan -p1-65535 <target_network> --rate=1000",
                "verification": "masscan --version",
                "prerequisites": [
                    "sudo privileges",
                    "build-essential (if compiling from source)",
                ],
            },
            "zmap": {
                "installation": "sudo apt-get install zmap",
                "usage": "zmap -p 443 -o results.txt",
                "verification": "zmap --version",
                "prerequisites": ["sudo privileges", "libgmp3-dev libpcap-dev"],
            },
        }

    def setup_routes(self):
        """Setup FastAPI routes for the research agent."""

        @self.app.get("/health")
        async def health_check():
            """Return health check status for the research agent."""
            return {"status": "healthy", "agent": "research", "version": "1.0.0"}

        @self.app.post("/research", response_model=ResearchResponse)
        async def research_endpoint(request: ResearchRequest):
            """Handle research requests and return structured results."""
            return await self.perform_research(request)

        @self.app.post("/research/tools")
        async def research_tools(request: ResearchRequest):
            """Specialized endpoint for researching tools and software."""
            return await self.research_specific_tools(request)

        @self.app.get("/research/installation/{tool_name}")
        async def get_installation_guide(tool_name: str):
            """Get detailed installation guide for a specific tool by name."""
            return await self.get_tool_installation_guide(tool_name)

    async def _get_web_researcher(self) -> AdvancedWebResearcher:
        """Get or initialize the web researcher (lazy initialization)."""
        if self._web_researcher is None:
            self._web_researcher = AdvancedWebResearcher({"headless": True})
            await self._web_researcher.initialize()
        return self._web_researcher

    async def perform_research(self, request: ResearchRequest) -> ResearchResponse:
        """Perform web research based on the request parameters using Playwright."""
        start_time = time.time()

        logger.info(
            "Starting research for query: '%s' with focus: '%s'",
            request.query,
            request.focus,
        )

        try:
            # Use real Playwright-based web research
            researcher = await self._get_web_researcher()
            search_results = await researcher.search_web(
                request.query, request.max_results
            )

            # Convert search results to ResearchResult format
            results = []
            if search_results.get("status") == "success":
                for item in search_results.get("results", []):
                    result = ResearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("snippet", item.get("content", "")),
                        relevance_score=item.get("relevance_score", 0.8),
                        source_type=item.get("search_engine", "web"),
                    )
                    results.append(result)

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
            logger.error("Research failed for query '%s': %s", request.query, str(e))
            raise HTTPException(status_code=500, detail=f"Research failed: {str(e)}")

    async def research_specific_tools(self, request: ResearchRequest) -> Dict[str, Any]:
        """Research specific tools with installation and usage information."""
        query_lower = request.query.lower()

        # Perform real web research for tool information
        try:
            researcher = await self._get_web_researcher()
            search_results = await researcher.search_web(
                request.query, request.max_results
            )

            research_results = []
            if search_results.get("status") == "success":
                for item in search_results.get("results", []):
                    result = ResearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("snippet", item.get("content", "")),
                        relevance_score=item.get("relevance_score", 0.8),
                        source_type=item.get("search_engine", "web"),
                    )
                    research_results.append(result)

            # Enhance with tool reference data if we have it
            tools_found = []
            detailed_info = {}
            for tool_name, tool_info in self._tool_reference_data.items():
                if tool_name in query_lower:
                    tools_found.append(tool_name)
                    detailed_info[tool_name] = tool_info

            return {
                "success": True,
                "tools_found": tools_found,
                "detailed_info": detailed_info,
                "research_results": [r.model_dump() for r in research_results],
                "web_search_results": search_results.get("results", []),
                "summary": self._generate_research_summary(
                    research_results, request.query
                ),
            }

        except Exception as e:
            logger.error("Tool research failed: %s", str(e))
            # Fallback to general research
            return await self.perform_research(request)

    async def _fetch_web_resources(self, tool_name: str, max_results: int = 3) -> list:
        """
        Fetch web resources for tool installation guide.

        Args:
            tool_name: Name of the tool to search for
            max_results: Maximum number of search results to return

        Returns:
            List of web search results, empty list on failure.
            Issue #620.
        """
        try:
            researcher = await self._get_web_researcher()
            search_results = await researcher.search_web(
                f"{tool_name} installation guide", max_results=max_results
            )
            if search_results.get("status") == "success":
                return search_results.get("results", [])
        except Exception as e:
            logger.warning("Web search for %s failed: %s", tool_name, str(e))
        return []

    def _build_guide_from_reference(
        self, tool_name: str, tool_info: Dict[str, Any], web_results: list
    ) -> Dict[str, Any]:
        """
        Build installation guide from reference data.

        Args:
            tool_name: Name of the tool
            tool_info: Tool information from reference database
            web_results: Additional web search results

        Returns:
            Complete installation guide dictionary.
            Issue #620.
        """
        return {
            "success": True,
            "tool_name": tool_name,
            "installation_command": tool_info.get("installation", "Not available"),
            "usage_example": tool_info.get("usage", "Not available"),
            "prerequisites": tool_info.get("prerequisites", ["sudo privileges"]),
            "verification_command": tool_info.get(
                "verification", f"{tool_name} --version"
            ),
            "web_resources": web_results,
        }

    async def get_tool_installation_guide(self, tool_name: str) -> Dict[str, Any]:
        """Get detailed installation guide for a specific tool."""
        tool_lower = tool_name.lower()

        # Check tool reference data
        if tool_lower in self._tool_reference_data:
            tool_info = self._tool_reference_data[tool_lower]
            web_results = await self._fetch_web_resources(tool_name, max_results=3)
            return self._build_guide_from_reference(tool_name, tool_info, web_results)

        # Tool not in reference data - search web for installation info
        web_results = await self._fetch_web_resources(tool_name, max_results=5)
        if web_results:
            return {
                "success": True,
                "tool_name": tool_name,
                "installation_command": "See web resources below",
                "usage_example": "See web resources below",
                "prerequisites": ["sudo privileges"],
                "verification_command": f"{tool_name} --version",
                "web_resources": web_results,
                "note": "Tool not in reference database, showing web search results",
            }

        return {
            "success": False,
            "tool_name": tool_name,
            "error": "Tool information not available and web search failed",
        }

    def _get_verification_command(self, tool_name: str) -> str:
        """Get command to verify tool installation."""
        tool_lower = tool_name.lower()
        if tool_lower in self._tool_reference_data:
            return self._tool_reference_data[tool_lower].get(
                "verification", f"{tool_name} --version"
            )
        return f"{tool_name} --version"

    def _generate_research_summary(
        self, results: List[ResearchResult], query: str
    ) -> str:
        """Generate a summary of research results from web search."""
        if not results:
            return f"No relevant results found for '{query}'"

        high_quality_results = [r for r in results if r.relevance_score > 0.8]
        source_types = set(r.source_type for r in results if r.source_type)

        summary = (
            f"Research completed for '{query}' with {len(results)} results found. "
            f"{len(high_quality_results)} high-quality sources identified."
        )

        if source_types:
            summary += f" Results from: {', '.join(source_types)}."

        if results:
            top_result = results[0]
            summary += f" Top result: '{top_result.title}'"

        return summary

    async def start_server(
        self, host: str = NetworkConstants.BIND_ALL_INTERFACES, port: int = 8005
    ):
        """Start the research agent server."""
        import uvicorn

        logger.info("Starting Research Agent server on %s:%s", host, port)
        uvicorn.run(self.app, host=host, port=port)


# Create global research agent instance
research_agent = ResearchAgent()

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Test mode - run sample research
        async def test_research():
            """Run sample research tests for validation."""
            request = ResearchRequest(
                query="network scanning tools",
                focus="installation_usage",
                max_results=3,
            )

            print("🔍 Testing Research Agent")  # noqa: print
            print("=" * 40)  # noqa: print

            # Test general research
            result = await research_agent.perform_research(request)
            print(f"Query: {result.query}")  # noqa: print
            print(f"Results: {result.sources_count}")  # noqa: print
            print(f"Summary: {result.summary}")  # noqa: print
            print()  # noqa: print

            # Test tool-specific research
            tools_result = await research_agent.research_specific_tools(request)
            print("Tool-specific research:")  # noqa: print
            print(f"Tools found: {tools_result.get('tools_found', [])}")  # noqa: print
            print(  # noqa: print
                f"Recommendation: {tools_result.get('recommendation', 'N/A')}"
            )  # noqa: print
            print()  # noqa: print

            # Test installation guide
            install_guide = await research_agent.get_tool_installation_guide("nmap")
            print("Installation guide for nmap:")  # noqa: print
            print(  # noqa: print
                f"Command: {install_guide.get('installation_command', 'N/A')}"
            )  # noqa: print
            print(f"Usage: {install_guide.get('usage_example', 'N/A')}")  # noqa: print
            print(  # noqa: print
                f"Prerequisites: {install_guide.get('prerequisites', [])}"
            )  # noqa: print

        asyncio.run(test_research())
    else:
        # Start the server
        asyncio.run(research_agent.start_server())
