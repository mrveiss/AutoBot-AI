# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for web research tools in tools/tool_registry.py.

Issue #7509: scrape_url, crawl_site, map_site, extract_structured_data
registered in get_available_tools() and dispatch table.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# get_available_tools
# ---------------------------------------------------------------------------


def test_get_available_tools_includes_web_research_tools() -> None:
    """All 4 web research tools appear in get_available_tools."""
    with (
        patch("tools.tool_registry.ToolRegistry.__init__", return_value=None),
        patch("chat_workflow.tool_handler.BROWSER_TOOL_NAMES", frozenset()),
    ):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        tools = registry.get_available_tools()

    assert "scrape_url" in tools
    assert "crawl_site" in tools
    assert "map_site" in tools
    assert "extract_structured_data" in tools


def test_get_available_tools_preserves_web_search() -> None:
    """Regression: web_search still in get_available_tools after #7509."""
    with (
        patch("tools.tool_registry.ToolRegistry.__init__", return_value=None),
        patch("chat_workflow.tool_handler.BROWSER_TOOL_NAMES", frozenset()),
    ):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        tools = registry.get_available_tools()

    assert "web_search" in tools


# ---------------------------------------------------------------------------
# Dispatch table — normalized name lookup
# ---------------------------------------------------------------------------


def test_dispatch_scrapeurl_resolves() -> None:
    """Normalized 'scrapeurl' resolves to scrape_url handler."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        handler = registry._get_tool_handler("scrapeurl")

    assert handler is not None


def test_dispatch_crawlsite_resolves() -> None:
    """Normalized 'crawlsite' resolves to crawl_site handler."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        handler = registry._get_tool_handler("crawlsite")

    assert handler is not None


def test_dispatch_mapsite_resolves() -> None:
    """Normalized 'mapsite' resolves to map_site handler."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        handler = registry._get_tool_handler("mapsite")

    assert handler is not None


def test_dispatch_extractstructureddata_resolves() -> None:
    """Normalized 'extractstructureddata' resolves to extract_structured_data handler."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        handler = registry._get_tool_handler("extractstructureddata")

    assert handler is not None


# ---------------------------------------------------------------------------
# scrape_url method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_url_success() -> None:
    """scrape_url returns markdown on success."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        registry.logger = MagicMock()

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.url = "https://example.com"
    mock_result.title = "Example Domain"
    mock_result.markdown = "# Hello"
    mock_result.status_code = 200
    mock_result.source = "jina"

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result):
        result = await registry.scrape_url("https://example.com")

    assert result["status"] == "success"
    assert "Hello" in result["result"]


@pytest.mark.asyncio
async def test_scrape_url_fetch_failure() -> None:
    """scrape_url returns error status when fetch fails."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        registry.logger = MagicMock()

    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error_code = "timeout"

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result):
        result = await registry.scrape_url("https://slow.example.com")

    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# map_site method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_map_site_success() -> None:
    """map_site returns markdown on success."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        registry.logger = MagicMock()

    from web_fetch.site_mapper import SiteMapEntry, SiteMapResult

    mock_site_result = SiteMapResult(
        domain="example.com",
        source="sitemap",
        entries=[SiteMapEntry(url="https://example.com/", title=None, depth=0)],
    )

    with (
        patch("web_fetch.site_mapper.SiteMapper.map_site", new_callable=AsyncMock, return_value=mock_site_result),
        patch("chat_workflow.tool_handler._format_map_results", return_value="## Mapped 1 URLs from example.com"),
    ):
        result = await registry.map_site("example.com")

    assert result["status"] == "success"
    assert "Mapped" in result["result"]
