#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for POST /knowledge/scrape endpoint and shim modules.

Issue #7401: Scrape-consolidation acceptance criteria.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_fetch_result(success: bool = True, markdown: str = "# Hello\nworld", title: str = "Test Page"):
    """Build a minimal FetchResult-like object for mocking."""
    result = MagicMock()
    result.success = success
    result.markdown = markdown
    result.title = title
    result.url = "https://example.com/page"
    result.source = "jina"
    result.error_code = None if success else "connection"
    result.retryable = not success
    return result


# ---------------------------------------------------------------------------
# ScrapeRequest validation
# ---------------------------------------------------------------------------


def test_scrape_request_defaults():
    """ScrapeRequest defaults are correct."""
    from api.knowledge_scrape import ScrapeRequest

    req = ScrapeRequest(url="https://example.com")
    assert req.render == "auto"
    assert req.ingest is False
    assert req.format == "markdown"


def test_scrape_request_render_values():
    """All render modes are accepted."""
    from api.knowledge_scrape import ScrapeRequest

    for mode in ("auto", "fast", "playwright"):
        req = ScrapeRequest(url="https://example.com", render=mode)
        assert req.render == mode


def test_scrape_request_rejects_bad_render():
    """Invalid render mode raises ValidationError."""
    from pydantic import ValidationError

    from api.knowledge_scrape import ScrapeRequest

    with pytest.raises(ValidationError):
        ScrapeRequest(url="https://example.com", render="turbo")


# ---------------------------------------------------------------------------
# scrape_url — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_url_success_no_ingest():
    """scrape_url returns markdown and indexed=False when ingest=False."""
    from api.knowledge_scrape import ScrapeRequest, scrape_url

    mock_result = _make_fetch_result()

    with patch("api.knowledge_scrape.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result):
        response = await scrape_url(ScrapeRequest(url="https://example.com", ingest=False))

    assert response.url == "https://example.com/page"
    assert response.indexed is False
    assert response.markdown == "# Hello\nworld"
    assert response.metadata.title == "Test Page"
    assert response.metadata.fetched_at  # non-empty ISO timestamp


@pytest.mark.asyncio
async def test_scrape_url_success_with_ingest():
    """scrape_url returns indexed=True when ingest succeeds."""
    from api.knowledge_scrape import ScrapeRequest, scrape_url

    mock_result = _make_fetch_result()

    with (
        patch("api.knowledge_scrape.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result),
        patch("web_fetch.ingest.ingest_markdown", new_callable=AsyncMock, return_value=True),
    ):
        response = await scrape_url(ScrapeRequest(url="https://example.com", ingest=True))

    assert response.indexed is True


@pytest.mark.asyncio
async def test_scrape_url_ingest_failure_is_non_fatal():
    """When ingest raises, scrape_url still returns success (indexed=False)."""
    from api.knowledge_scrape import ScrapeRequest, scrape_url

    mock_result = _make_fetch_result()

    with (
        patch("api.knowledge_scrape.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result),
        patch("web_fetch.ingest.ingest_markdown", new_callable=AsyncMock, side_effect=RuntimeError("chromadb down")),
    ):
        response = await scrape_url(ScrapeRequest(url="https://example.com", ingest=True))

    assert response.url == "https://example.com/page"
    assert response.indexed is False


@pytest.mark.asyncio
async def test_scrape_url_playwright_render():
    """render=playwright is passed through to WebFetcher."""
    from api.knowledge_scrape import ScrapeRequest, scrape_url
    from web_fetch import RenderMode

    mock_result = _make_fetch_result()
    captured_render = {}

    async def fake_fetch(url, render=RenderMode.AUTO, **kw):
        captured_render["mode"] = render
        return mock_result

    with patch("api.knowledge_scrape.WebFetcher.fetch", side_effect=fake_fetch):
        await scrape_url(ScrapeRequest(url="https://example.com", render="playwright"))

    assert captured_render["mode"] == RenderMode.PLAYWRIGHT


# ---------------------------------------------------------------------------
# scrape_url — failure path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_url_fetch_failure_raises_502():
    """WebFetcher failure → HTTPException 502."""
    from fastapi import HTTPException

    from api.knowledge_scrape import ScrapeRequest, scrape_url

    mock_result = _make_fetch_result(success=False)

    with patch("api.knowledge_scrape.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result):
        with pytest.raises(HTTPException) as exc_info:
            await scrape_url(ScrapeRequest(url="https://example.com"))

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["success"] is False
    assert "error_code" in exc_info.value.detail


# ---------------------------------------------------------------------------
# LinkResult / process_url shim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_url_returns_link_result_on_success():
    """process_url translates FetchResult → LinkResult correctly.

    WebFetcher is imported inside process_url, so we patch web_fetch.WebFetcher
    at the module level it is resolved from.
    """
    from media.link.pipeline import LinkResult, process_url

    mock_fr = _make_fetch_result()

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_fr):
        lr = await process_url("https://example.com")

    assert isinstance(lr, LinkResult)
    assert lr.success is True
    assert lr.markdown == "# Hello\nworld"
    assert lr.title == "Test Page"
    assert lr.error_code is None


@pytest.mark.asyncio
async def test_process_url_returns_link_result_on_failure():
    """process_url translates FetchResult failure → LinkResult failure."""
    from media.link.pipeline import LinkResult, process_url

    mock_fr = _make_fetch_result(success=False, markdown="", title="")

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_fr):
        lr = await process_url("https://broken.example.com")

    assert isinstance(lr, LinkResult)
    assert lr.success is False
    assert lr.error_code == "connection"
    assert lr.retryable is True


# ---------------------------------------------------------------------------
# system_integration.web_fetch shim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_integration_web_fetch_delegator_success():
    """SystemIntegration.web_fetch() delegates to WebFetcher and returns dict."""
    from system_integration import SystemIntegration

    si = SystemIntegration()
    mock_fr = _make_fetch_result()

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_fr):
        result = await si.web_fetch("https://example.com/page")

    assert result["status"] == "success"
    assert result["content"] == "# Hello\nworld"
    assert result["url"] == "https://example.com/page"


@pytest.mark.asyncio
async def test_system_integration_web_fetch_delegator_failure():
    """SystemIntegration.web_fetch() returns error dict on fetch failure."""
    from system_integration import SystemIntegration

    si = SystemIntegration()
    mock_fr = _make_fetch_result(success=False, markdown="", title="")

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_fr):
        result = await si.web_fetch("https://broken.example.com")

    assert result["status"] == "error"
    assert "url" in result


# ---------------------------------------------------------------------------
# web_fetch/ingest.py helpers
# ---------------------------------------------------------------------------


def test_url_to_rel_path():
    """_url_to_rel_path produces stable relative paths."""
    from web_fetch.ingest import _url_to_rel_path

    path = _url_to_rel_path("https://docs.example.com/guide/intro")
    assert path == "web/docs.example.com/guide/intro"


def test_url_to_rel_path_no_path():
    """Root URL produces 'index' path component."""
    from web_fetch.ingest import _url_to_rel_path

    path = _url_to_rel_path("https://example.com/")
    assert path == "web/example.com/index"


def test_prepend_title_adds_h1():
    """_prepend_title prepends H1 when markdown lacks one."""
    from web_fetch.ingest import _prepend_title

    result = _prepend_title("Some text", "My Title")
    assert result.startswith("# My Title\n")


def test_prepend_title_no_duplicate():
    """_prepend_title does not prepend when markdown already has H1."""
    from web_fetch.ingest import _prepend_title

    md = "# Already Here\n\ncontent"
    result = _prepend_title(md, "My Title")
    assert result == md


def test_prepend_title_empty_title():
    """_prepend_title returns markdown unchanged when title is empty."""
    from web_fetch.ingest import _prepend_title

    md = "Some text"
    assert _prepend_title(md, "") == md


@pytest.mark.asyncio
async def test_ingest_markdown_empty_content():
    """ingest_markdown returns False without calling DocIndexerService for empty input.

    get_doc_indexer_service is a lazy import inside ingest_markdown; patch at
    the source module so the import picks up the mock regardless of call order.
    """
    from web_fetch.ingest import ingest_markdown

    with patch("services.knowledge.doc_indexer.get_doc_indexer_service") as mock_get:
        result = await ingest_markdown("https://example.com", "")

    assert result is False
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_markdown_success():
    """ingest_markdown returns True when DocIndexerService stores >=1 chunk."""
    import sys

    from web_fetch.ingest import ingest_markdown

    mock_indexer = AsyncMock()
    mock_indexer._initialized = True
    mock_indexer._index_file_chunks = AsyncMock(return_value=(2, 3))

    mock_module = MagicMock()
    mock_module.get_doc_indexer_service = MagicMock(return_value=mock_indexer)

    with patch.dict(sys.modules, {"services.knowledge.doc_indexer": mock_module}):
        result = await ingest_markdown("https://example.com", "# Hello\nworld", "Hello")

    assert result is True


@pytest.mark.asyncio
async def test_ingest_markdown_zero_chunks():
    """ingest_markdown returns False when DocIndexerService stores 0 chunks."""
    import sys

    from web_fetch.ingest import ingest_markdown

    mock_indexer = AsyncMock()
    mock_indexer._initialized = True
    mock_indexer._index_file_chunks = AsyncMock(return_value=(0, 5))

    mock_module = MagicMock()
    mock_module.get_doc_indexer_service = MagicMock(return_value=mock_indexer)

    with patch.dict(sys.modules, {"services.knowledge.doc_indexer": mock_module}):
        result = await ingest_markdown("https://example.com", "# Hello\nworld")

    assert result is False
