# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Import smoke test — verifies public API exports of the web_fetch package."""

from web_fetch import (
    ERR_CIRCUIT_OPEN,
    ERR_CONNECTION,
    ERR_HTTP_ERROR,
    ERR_ROBOTS_BLOCKED,
    ERR_SSRF_BLOCKED,
    ERR_TIMEOUT,
    ERR_TOO_LARGE,
    ERR_UNKNOWN,
    FetchResult,
    Frontier,
    RenderMode,
    RobotsCache,
    WebFetcher,
)


def test_public_api_imports() -> None:
    assert WebFetcher is not None
    assert RenderMode is not None
    assert FetchResult is not None
    assert Frontier is not None
    assert RobotsCache is not None


def test_render_mode_values() -> None:
    assert RenderMode.AUTO == "auto"
    assert RenderMode.FAST == "fast"
    assert RenderMode.PLAYWRIGHT == "playwright"


def test_fetch_result_instantiates() -> None:
    r = FetchResult(url="https://example.com", success=True, markdown="# Hi")
    assert r.url == "https://example.com"
    assert r.success is True
    assert r.markdown == "# Hi"


def test_error_constants_are_strings() -> None:
    for const in (
        ERR_SSRF_BLOCKED,
        ERR_ROBOTS_BLOCKED,
        ERR_CIRCUIT_OPEN,
        ERR_HTTP_ERROR,
        ERR_TIMEOUT,
        ERR_CONNECTION,
        ERR_TOO_LARGE,
        ERR_UNKNOWN,
    ):
        assert isinstance(const, str)


def test_frontier_instantiates() -> None:
    f = Frontier("https://example.com", max_pages=5)
    item = f.next()
    assert item is not None
    url, depth = item
    assert url == "https://example.com"
    assert depth == 0


def test_robots_cache_instantiates() -> None:
    rc = RobotsCache(redis_client=None)
    assert rc is not None
