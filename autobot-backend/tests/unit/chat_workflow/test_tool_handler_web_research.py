# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for web research tool schemas and dispatch in chat_workflow/tool_handler.py.

Issue #7509: scrape_url, crawl_site, map_site, extract_structured_data schemas
registered in _BUILTIN_TOOL_SCHEMAS; dispatch routed to _handle_web_research_tool.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Schema presence tests
# ---------------------------------------------------------------------------


def test_scrape_url_schema_registered() -> None:
    """SCRAPE_URL_SCHEMA is present in _BUILTIN_TOOL_SCHEMAS."""
    from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS, SCRAPE_URL_SCHEMA

    assert "scrape_url" in _BUILTIN_TOOL_SCHEMAS
    assert _BUILTIN_TOOL_SCHEMAS["scrape_url"] is SCRAPE_URL_SCHEMA


def test_crawl_site_schema_registered() -> None:
    """CRAWL_SITE_SCHEMA is present in _BUILTIN_TOOL_SCHEMAS."""
    from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS, CRAWL_SITE_SCHEMA

    assert "crawl_site" in _BUILTIN_TOOL_SCHEMAS
    assert _BUILTIN_TOOL_SCHEMAS["crawl_site"] is CRAWL_SITE_SCHEMA


def test_map_site_schema_registered() -> None:
    """MAP_SITE_SCHEMA is present in _BUILTIN_TOOL_SCHEMAS."""
    from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS, MAP_SITE_SCHEMA

    assert "map_site" in _BUILTIN_TOOL_SCHEMAS
    assert _BUILTIN_TOOL_SCHEMAS["map_site"] is MAP_SITE_SCHEMA


def test_extract_structured_data_schema_registered() -> None:
    """EXTRACT_STRUCTURED_DATA_SCHEMA is present in _BUILTIN_TOOL_SCHEMAS."""
    from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS, EXTRACT_STRUCTURED_DATA_SCHEMA

    assert "extract_structured_data" in _BUILTIN_TOOL_SCHEMAS
    assert _BUILTIN_TOOL_SCHEMAS["extract_structured_data"] is EXTRACT_STRUCTURED_DATA_SCHEMA


def test_web_search_schema_unchanged() -> None:
    """Regression: WEB_SEARCH_SCHEMA still present and has required 'query'."""
    from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS, WEB_SEARCH_SCHEMA

    assert "web_search" in _BUILTIN_TOOL_SCHEMAS
    assert "query" in WEB_SEARCH_SCHEMA["properties"]
    assert WEB_SEARCH_SCHEMA["required"] == ["query"]


def test_scrape_url_schema_requires_url() -> None:
    """SCRAPE_URL_SCHEMA requires the 'url' property."""
    from chat_workflow.tool_handler import SCRAPE_URL_SCHEMA

    assert "url" in SCRAPE_URL_SCHEMA["properties"]
    assert "url" in SCRAPE_URL_SCHEMA.get("required", [])


def test_crawl_site_schema_requires_seed_urls() -> None:
    """CRAWL_SITE_SCHEMA requires 'seed_urls'."""
    from chat_workflow.tool_handler import CRAWL_SITE_SCHEMA

    assert "seed_urls" in CRAWL_SITE_SCHEMA["properties"]
    assert "seed_urls" in CRAWL_SITE_SCHEMA.get("required", [])


def test_map_site_schema_requires_domain() -> None:
    """MAP_SITE_SCHEMA requires 'domain'."""
    from chat_workflow.tool_handler import MAP_SITE_SCHEMA

    assert "domain" in MAP_SITE_SCHEMA["properties"]
    assert "domain" in MAP_SITE_SCHEMA.get("required", [])


def test_extract_structured_data_schema_requires_url_and_schema() -> None:
    """EXTRACT_STRUCTURED_DATA_SCHEMA requires 'url' and 'schema'."""
    from chat_workflow.tool_handler import EXTRACT_STRUCTURED_DATA_SCHEMA

    required = EXTRACT_STRUCTURED_DATA_SCHEMA.get("required", [])
    assert "url" in required
    assert "schema" in required


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


def test_format_crawl_results_success() -> None:
    """_format_crawl_results returns a markdown string with page count."""
    from chat_workflow.tool_handler import _format_crawl_results

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.url = "https://example.com/page"
    mock_result.markdown = "# Page content"
    mock_result.error_code = None

    output = _format_crawl_results(["https://example.com"], [mock_result])
    assert "Crawled 1 pages" in output
    assert "https://example.com/page" in output
    assert "Page content" in output


def test_format_crawl_results_failure() -> None:
    """_format_crawl_results marks failed pages."""
    from chat_workflow.tool_handler import _format_crawl_results

    mock_result = MagicMock()
    mock_result.success = False
    mock_result.url = "https://broken.example.com"
    mock_result.error_code = "connection"

    output = _format_crawl_results(["https://broken.example.com"], [mock_result])
    assert "FAILED" in output
    assert "connection" in output


def test_format_map_results() -> None:
    """_format_map_results returns a markdown list grouped by depth."""
    from chat_workflow.tool_handler import _format_map_results
    from web_fetch.site_mapper import SiteMapEntry, SiteMapResult

    entries = [
        SiteMapEntry(url="https://example.com/", title=None, depth=0),
        SiteMapEntry(url="https://example.com/about", title=None, depth=1),
    ]
    site_result = SiteMapResult(domain="example.com", source="sitemap", entries=entries)

    output = _format_map_results(site_result)
    assert "Mapped 2 URLs" in output
    assert "example.com" in output
    assert "sitemap" in output
    assert "https://example.com/" in output


# ---------------------------------------------------------------------------
# _exec_scrape_url unit test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exec_scrape_url_success() -> None:
    """_exec_scrape_url returns markdown content on success."""
    from chat_workflow.tool_handler import ToolHandlerMixin

    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.url = "https://example.com"
    mock_result.title = "Example"
    mock_result.markdown = "Hello world"
    mock_result.status_code = 200
    mock_result.source = "bs4"

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result):
        output = await mixin._exec_scrape_url({"url": "https://example.com", "render": "auto"})

    assert "https://example.com" in output
    assert "Hello world" in output


@pytest.mark.asyncio
async def test_exec_scrape_url_failure() -> None:
    """_exec_scrape_url returns an error message on fetch failure."""
    from chat_workflow.tool_handler import ToolHandlerMixin

    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)

    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error_code = "connection"

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result):
        output = await mixin._exec_scrape_url({"url": "https://broken.example.com"})

    assert "Fetch failed" in output
    assert "connection" in output
