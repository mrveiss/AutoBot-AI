# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for POST /knowledge/crawl endpoint.

Issue #7508: Endpoint validation, success path, failure path, ingest path,
render-mode override, max_depth / respect_robots / same_origin propagation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fetch_result(url: str = "https://example.com", success: bool = True) -> MagicMock:
    """Return a MagicMock shaped like a FetchResult."""
    fr = MagicMock()
    fr.url = url
    fr.success = success
    fr.markdown = "# Example\n\nContent here." if success else ""
    fr.error_code = None if success else "connection"
    fr.retryable = not success
    return fr


# ---------------------------------------------------------------------------
# CrawlRequest validation
# ---------------------------------------------------------------------------


def test_crawl_request_defaults() -> None:
    """CrawlRequest defaults are correct."""
    from api.knowledge_crawl import CrawlRequest

    req = CrawlRequest(seeds=["https://example.com"])
    assert req.max_depth == 1
    assert req.max_pages == 100
    assert req.respect_robots is True
    assert req.ingest is True
    assert req.same_origin is True
    assert req.render == "auto"


def test_crawl_request_seeds_required() -> None:
    """Missing seeds raises ValidationError."""
    with pytest.raises(ValidationError):
        from api.knowledge_crawl import CrawlRequest

        CrawlRequest()


def test_crawl_request_empty_seeds_rejected() -> None:
    """Empty seeds list raises ValidationError (min_length=1)."""
    with pytest.raises(ValidationError):
        from api.knowledge_crawl import CrawlRequest

        CrawlRequest(seeds=[])


def test_crawl_request_all_render_modes() -> None:
    """All valid render modes are accepted."""
    from api.knowledge_crawl import CrawlRequest

    for mode in ("auto", "fast", "playwright"):
        req = CrawlRequest(seeds=["https://example.com"], render=mode)
        assert req.render == mode


def test_crawl_request_invalid_render_rejected() -> None:
    """Invalid render mode raises ValidationError."""
    with pytest.raises(ValidationError):
        from api.knowledge_crawl import CrawlRequest

        CrawlRequest(seeds=["https://example.com"], render="turbo")


def test_crawl_request_max_depth_ge_1() -> None:
    """max_depth < 1 raises ValidationError."""
    with pytest.raises(ValidationError):
        from api.knowledge_crawl import CrawlRequest

        CrawlRequest(seeds=["https://example.com"], max_depth=0)


def test_crawl_request_max_pages_ge_1() -> None:
    """max_pages < 1 raises ValidationError."""
    with pytest.raises(ValidationError):
        from api.knowledge_crawl import CrawlRequest

        CrawlRequest(seeds=["https://example.com"], max_pages=0)


# ---------------------------------------------------------------------------
# crawl_url_endpoint — success path, no ingest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_endpoint_success_no_ingest() -> None:
    """Returns CrawlResponse with pages on happy path (ingest=False)."""
    from api.knowledge_crawl import CrawlRequest, crawl_url_endpoint

    req = CrawlRequest(seeds=["https://example.com"], ingest=False)
    mock_result = [_make_fetch_result("https://example.com")]

    with patch("api.knowledge_crawl.WebCrawlerConnector") as MockConnector:
        instance = MockConnector.return_value
        instance.crawl = AsyncMock(return_value=mock_result)

        response = await crawl_url_endpoint(req)

    assert response.count == 1
    assert response.indexed is False
    assert response.pages[0]["url"] == "https://example.com"
    assert response.pages[0]["success"] is True


@pytest.mark.asyncio
async def test_crawl_endpoint_returns_correct_page_count() -> None:
    """count matches the number of pages returned by the connector."""
    from api.knowledge_crawl import CrawlRequest, crawl_url_endpoint

    req = CrawlRequest(seeds=["https://example.com", "https://example.org"], ingest=False)
    mock_results = [
        _make_fetch_result("https://example.com"),
        _make_fetch_result("https://example.org"),
        _make_fetch_result("https://example.com/about"),
    ]

    with patch("api.knowledge_crawl.WebCrawlerConnector") as MockConnector:
        instance = MockConnector.return_value
        instance.crawl = AsyncMock(return_value=mock_results)

        response = await crawl_url_endpoint(req)

    assert response.count == 3
    assert len(response.pages) == 3


# ---------------------------------------------------------------------------
# crawl_url_endpoint — max_depth propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_endpoint_honours_max_depth() -> None:
    """max_depth from the request is forwarded to connector.crawl()."""
    from api.knowledge_crawl import CrawlRequest, crawl_url_endpoint

    req = CrawlRequest(seeds=["https://example.com"], max_depth=3, ingest=False)

    with patch("api.knowledge_crawl.WebCrawlerConnector") as MockConnector:
        instance = MockConnector.return_value
        instance.crawl = AsyncMock(return_value=[])

        await crawl_url_endpoint(req)

    instance.crawl.assert_awaited_once_with(
        seed_urls=["https://example.com"],
        max_depth=3,
        max_pages=100,
        respect_robots=True,
        ingest=False,
        same_origin=True,
    )


# ---------------------------------------------------------------------------
# crawl_url_endpoint — respect_robots propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_endpoint_respect_robots_true() -> None:
    """respect_robots=True (default) is forwarded to connector.crawl()."""
    from api.knowledge_crawl import CrawlRequest, crawl_url_endpoint

    req = CrawlRequest(seeds=["https://example.com"], respect_robots=True, ingest=False)

    with patch("api.knowledge_crawl.WebCrawlerConnector") as MockConnector:
        instance = MockConnector.return_value
        instance.crawl = AsyncMock(return_value=[])

        await crawl_url_endpoint(req)

    _, kwargs = instance.crawl.await_args
    assert kwargs.get("respect_robots") is True or instance.crawl.await_args[0][3] is True


@pytest.mark.asyncio
async def test_crawl_endpoint_respect_robots_false() -> None:
    """respect_robots=False admin override is forwarded to connector.crawl()."""
    from api.knowledge_crawl import CrawlRequest, crawl_url_endpoint

    req = CrawlRequest(seeds=["https://example.com"], respect_robots=False, ingest=False)

    with patch("api.knowledge_crawl.WebCrawlerConnector") as MockConnector:
        instance = MockConnector.return_value
        instance.crawl = AsyncMock(return_value=[])

        await crawl_url_endpoint(req)

    instance.crawl.assert_awaited_once_with(
        seed_urls=["https://example.com"],
        max_depth=1,
        max_pages=100,
        respect_robots=False,
        ingest=False,
        same_origin=True,
    )


# ---------------------------------------------------------------------------
# crawl_url_endpoint — ingest path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_endpoint_ingest_true_sets_indexed() -> None:
    """ingest=True causes indexed=True in the response and is forwarded to connector."""
    from api.knowledge_crawl import CrawlRequest, crawl_url_endpoint

    req = CrawlRequest(seeds=["https://example.com"], ingest=True)

    with patch("api.knowledge_crawl.WebCrawlerConnector") as MockConnector:
        instance = MockConnector.return_value
        instance.crawl = AsyncMock(return_value=[_make_fetch_result()])

        response = await crawl_url_endpoint(req)

    assert response.indexed is True
    call_kwargs = instance.crawl.await_args[1]
    assert call_kwargs.get("ingest") is True


# ---------------------------------------------------------------------------
# crawl_url_endpoint — render enum conversion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_endpoint_render_converted_to_enum() -> None:
    """render='fast' is converted to RenderMode without raising."""
    from api.knowledge_crawl import CrawlRequest, crawl_url_endpoint

    req = CrawlRequest(seeds=["https://example.com"], render="fast", ingest=False)

    with patch("api.knowledge_crawl.WebCrawlerConnector") as MockConnector:
        instance = MockConnector.return_value
        instance.crawl = AsyncMock(return_value=[])

        # Should not raise — RenderMode("fast") succeeds
        response = await crawl_url_endpoint(req)

    assert response.count == 0


# ---------------------------------------------------------------------------
# crawl_url_endpoint — failure path (502)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_endpoint_connector_exception_returns_502() -> None:
    """Exception from connector.crawl() maps to 502 with crawl_failed error_code."""
    from fastapi import HTTPException

    from api.knowledge_crawl import CrawlRequest, crawl_url_endpoint

    req = CrawlRequest(seeds=["https://broken.example.com"], ingest=False)

    with patch("api.knowledge_crawl.WebCrawlerConnector") as MockConnector:
        instance = MockConnector.return_value
        instance.crawl = AsyncMock(side_effect=RuntimeError("network unreachable"))

        with pytest.raises(HTTPException) as exc_info:
            await crawl_url_endpoint(req)

    assert exc_info.value.status_code == 502
    detail = exc_info.value.detail
    assert detail["success"] is False
    assert detail["error_code"] == "crawl_failed"
    assert detail["retryable"] is True


# ---------------------------------------------------------------------------
# _fetch_results_to_pages helper
# ---------------------------------------------------------------------------


def test_fetch_results_to_pages_maps_fields() -> None:
    """_fetch_results_to_pages correctly maps FetchResult attributes to dict."""
    from api.knowledge_crawl import _fetch_results_to_pages

    fr = _make_fetch_result("https://example.com/page", success=True)
    fr.markdown = "## Page content"

    pages = _fetch_results_to_pages([fr])

    assert len(pages) == 1
    page = pages[0]
    assert page["url"] == "https://example.com/page"
    assert page["markdown"] == "## Page content"
    assert page["success"] is True
    assert "depth" in page


def test_fetch_results_to_pages_failed_result() -> None:
    """_fetch_results_to_pages includes failed pages with success=False."""
    from api.knowledge_crawl import _fetch_results_to_pages

    fr = _make_fetch_result("https://bad.example.com", success=False)

    pages = _fetch_results_to_pages([fr])

    assert pages[0]["success"] is False
