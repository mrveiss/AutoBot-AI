# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for 3 new MCP endpoints in api/knowledge_mcp.py.

Issue #7509: POST /mcp/scrape_url, /mcp/crawl_site, /mcp/map_site.
Also verifies /mcp/tools surfaces all new tool names.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# /mcp/tools listing
# ---------------------------------------------------------------------------


def test_mcp_tools_includes_scrape_url() -> None:
    """_get_knowledge_search_tools includes scrape_url."""
    from api.knowledge_mcp import _get_knowledge_search_tools

    tools = _get_knowledge_search_tools()
    names = [t.name for t in tools]
    assert "scrape_url" in names


def test_mcp_tools_includes_crawl_site() -> None:
    """_get_knowledge_search_tools includes crawl_site."""
    from api.knowledge_mcp import _get_knowledge_search_tools

    tools = _get_knowledge_search_tools()
    names = [t.name for t in tools]
    assert "crawl_site" in names


def test_mcp_tools_includes_map_site() -> None:
    """_get_knowledge_search_tools includes map_site."""
    from api.knowledge_mcp import _get_knowledge_search_tools

    tools = _get_knowledge_search_tools()
    names = [t.name for t in tools]
    assert "map_site" in names


def test_mcp_tools_preserves_extract_structured_data() -> None:
    """Regression: extract_structured_data still in tool list."""
    from api.knowledge_mcp import _get_knowledge_search_tools

    tools = _get_knowledge_search_tools()
    names = [t.name for t in tools]
    assert "extract_structured_data" in names


# ---------------------------------------------------------------------------
# /mcp/scrape_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_scrape_url_success() -> None:
    """mcp_scrape_url returns success with markdown on happy path."""
    from api.knowledge_mcp import mcp_scrape_url

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.url = "https://example.com"
    mock_result.title = "Example"
    mock_result.markdown = "# Hello"
    mock_result.status_code = 200
    mock_result.source = "bs4"

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result):
        response = await mcp_scrape_url({"url": "https://example.com"})

    assert response["success"] is True
    assert "Hello" in response["markdown"]


@pytest.mark.asyncio
async def test_mcp_scrape_url_missing_url() -> None:
    """mcp_scrape_url returns error when url is missing."""
    from api.knowledge_mcp import mcp_scrape_url

    response = await mcp_scrape_url({})
    assert response["success"] is False
    assert "url is required" in response["error"]


@pytest.mark.asyncio
async def test_mcp_scrape_url_fetch_failure() -> None:
    """mcp_scrape_url returns error when fetch fails."""
    from api.knowledge_mcp import mcp_scrape_url

    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error_code = "timeout"

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result):
        response = await mcp_scrape_url({"url": "https://slow.example.com"})

    assert response["success"] is False
    assert response.get("error_code") == "timeout"


# ---------------------------------------------------------------------------
# /mcp/crawl_site
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_crawl_site_missing_seed_urls() -> None:
    """mcp_crawl_site returns error when seed_urls is empty."""
    from api.knowledge_mcp import mcp_crawl_site

    response = await mcp_crawl_site({})
    assert response["success"] is False
    assert "seed_urls" in response["error"]


@pytest.mark.asyncio
async def test_mcp_crawl_site_success() -> None:
    """mcp_crawl_site returns success with page_count and markdown."""
    from api.knowledge_mcp import mcp_crawl_site

    mock_fetch_result = MagicMock()
    mock_fetch_result.success = True
    mock_fetch_result.url = "https://example.com"
    mock_fetch_result.markdown = "# Home"
    mock_fetch_result.error_code = None

    with (
        patch(
            "knowledge.connectors.web_crawler.WebCrawlerConnector.crawl",
            new_callable=AsyncMock,
            return_value=[mock_fetch_result],
        ),
        patch(
            "chat_workflow.tool_handler._format_crawl_results",
            return_value="## Crawled 1 pages from https://example.com",
        ),
    ):
        response = await mcp_crawl_site({"seed_urls": ["https://example.com"]})

    assert response["success"] is True
    assert response["page_count"] == 1
    assert "Crawled" in response["markdown"]


# ---------------------------------------------------------------------------
# /mcp/map_site
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_map_site_missing_domain() -> None:
    """mcp_map_site returns error when domain is missing."""
    from api.knowledge_mcp import mcp_map_site

    response = await mcp_map_site({})
    assert response["success"] is False
    assert "domain" in response["error"]


@pytest.mark.asyncio
async def test_mcp_map_site_success() -> None:
    """mcp_map_site returns success with url_count and markdown."""
    from api.knowledge_mcp import mcp_map_site
    from web_fetch.site_mapper import SiteMapEntry, SiteMapResult

    mock_site_result = SiteMapResult(
        domain="example.com",
        source="sitemap",
        entries=[SiteMapEntry(url="https://example.com/", title=None, depth=0)],
    )

    with (
        patch("web_fetch.site_mapper.SiteMapper.map_site", new_callable=AsyncMock, return_value=mock_site_result),
        patch(
            "chat_workflow.tool_handler._format_map_results",
            return_value="## Mapped 1 URLs from example.com (source: sitemap)",
        ),
    ):
        response = await mcp_map_site({"domain": "example.com"})

    assert response["success"] is True
    assert response["url_count"] == 1
    assert response["source"] == "sitemap"
    assert "Mapped" in response["markdown"]
