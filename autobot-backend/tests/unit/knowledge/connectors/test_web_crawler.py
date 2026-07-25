# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for knowledge.connectors.web_crawler — Issue #7402.

Tests BFS recursion, same_origin filter, robots.txt enforcement,
max_pages cap, ingest path, and backward-compat (depth=1 default).

All external I/O (_fetch_bs4, RobotsCache, KB ingest) is mocked so
tests run without network access or ChromaDB.
"""

from typing import List, Tuple
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from knowledge.connectors.models import ConnectorConfig, SyncResult
from knowledge.connectors.web_crawler import (
    WebCrawlerConnector,
    _fetch_result_to_content,
    _get_domain,
    _url_to_source_id,
)
from web_fetch.types import FetchResult, RenderMode

# ---------------------------------------------------------------------------
# Fixture static site — HTML so extract_links works correctly
# ---------------------------------------------------------------------------
# URL → (html_string, http_status) mapping
_FIXTURE_PAGES: dict = {
    "https://example.com": (
        """<html><head><title>Root</title></head><body>
<h1>Root Page</h1>
<p>Welcome. Enough content here for the crawl to consider this page valid.</p>
<a href="/about">About</a>
<a href="/blog">Blog</a>
<a href="https://external.com/page">External</a>
</body></html>""",
        200,
    ),
    "https://example.com/about": (
        """<html><head><title>About</title></head><body>
<h1>About Us</h1>
<p>We are a company with lots of content on this page for testing.</p>
<a href="/contact">Contact</a>
</body></html>""",
        200,
    ),
    "https://example.com/blog": (
        """<html><head><title>Blog</title></head><body>
<h1>Blog</h1>
<p>Our latest posts. Enough text for the test suite to validate crawl depth.</p>
</body></html>""",
        200,
    ),
    "https://example.com/contact": (
        """<html><head><title>Contact</title></head><body>
<h1>Contact</h1>
<p>Reach us at hello@example.com. This is a depth-2 page from About.</p>
</body></html>""",
        200,
    ),
    "https://external.com/page": (
        """<html><head><title>External</title></head><body>
<h1>External Site</h1><p>External content.</p>
</body></html>""",
        200,
    ),
}


def _fixture_bs4(url: str, timeout: float = 30.0) -> Tuple[str | None, int | None]:
    """Synchronous helper — used as coroutine side_effect via AsyncMock."""
    entry = _FIXTURE_PAGES.get(url)
    if entry is None:
        return None, None
    return entry


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------


def _make_config(
    urls: List[str],
    max_depth: int = 1,
    max_pages: int = 100,
    respect_robots: bool = True,
    same_origin: bool = True,
) -> ConnectorConfig:
    return ConnectorConfig(
        connector_id="test-crawler",
        connector_type="web_crawler",
        name="Test Crawler",
        config={
            "urls": urls,
            "max_depth": max_depth,
            "max_pages": max_pages,
            "respect_robots": respect_robots,
            "same_origin": same_origin,
        },
    )


def _make_fetch_result(
    url: str,
    markdown: str = "",
    success: bool = True,
    error_code: str | None = None,
) -> FetchResult:
    return FetchResult(
        url=url,
        success=success,
        markdown=markdown if success else "",
        title=url.split("/")[-1] or "root",
        render_mode=RenderMode.AUTO,
        source="bs4",
        error_code=error_code,
    )


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_url_to_source_id_stable(self) -> None:
        sid1 = _url_to_source_id("https://example.com/page")
        sid2 = _url_to_source_id("https://example.com/page")
        assert sid1 == sid2
        assert len(sid1) == 32

    def test_url_to_source_id_different_urls(self) -> None:
        assert _url_to_source_id("https://a.com") != _url_to_source_id("https://b.com")

    def test_get_domain(self) -> None:
        assert _get_domain("https://example.com/path") == "example.com"

    def test_get_domain_fallback(self) -> None:
        assert _get_domain("not-a-url") == "not-a-url"

    def test_fetch_result_to_content_success(self) -> None:
        result = _make_fetch_result("https://example.com", markdown="# Hello\n\nWorld content here.")
        content = _fetch_result_to_content(result, "test-conn")
        assert content is not None
        assert content.content == "# Hello\n\nWorld content here."
        assert content.metadata["url"] == "https://example.com"
        assert content.metadata["connector_id"] == "test-conn"

    def test_fetch_result_to_content_empty_markdown(self) -> None:
        result = _make_fetch_result("https://example.com", markdown="   ", success=True)
        assert _fetch_result_to_content(result, "conn") is None

    def test_fetch_result_to_content_failed(self) -> None:
        result = _make_fetch_result("https://example.com", success=False)
        assert _fetch_result_to_content(result, "conn") is None


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_bs4():
    """Patch WebFetcher.fetch_raw_html to return fixture site pages (coroutine-compatible)."""

    async def _side_effect(url, timeout=30.0):
        return _fixture_bs4(url, timeout)

    with patch("knowledge.connectors.web_crawler.WebFetcher.fetch_raw_html", side_effect=_side_effect):
        yield


@pytest.fixture()
def mock_robots_allow():
    """_build_robots_cache returns a RobotsCache that allows all URLs."""
    with patch("knowledge.connectors.web_crawler.WebCrawlerConnector._build_robots_cache") as m:
        cache = MagicMock()
        cache.is_allowed = AsyncMock(return_value=True)
        m.return_value = cache
        yield m


@pytest.fixture()
def mock_robots_none():
    """_build_robots_cache returns None (robots disabled)."""
    with patch("knowledge.connectors.web_crawler.WebCrawlerConnector._build_robots_cache") as m:
        m.return_value = None
        yield m


@pytest.fixture()
def mock_ingest():
    with patch("knowledge.connectors.web_crawler._ingest_results_to_kb", new=AsyncMock()) as m:
        yield m


# ---------------------------------------------------------------------------
# Crawl depth tests
# ---------------------------------------------------------------------------


class TestCrawlDepth:
    """Verify max_depth is actually honoured by the BFS."""

    async def test_depth_1_returns_only_seed(self, mock_bs4, mock_robots_none, mock_ingest) -> None:
        """crawl(max_depth=1) must return only the seed URL (no links followed)."""
        connector = WebCrawlerConnector(_make_config(["https://example.com"], max_depth=1))
        results = await connector.crawl(["https://example.com"], max_depth=1, ingest=False, same_origin=True)
        fetched_urls = [r.url for r in results]
        assert "https://example.com" in fetched_urls
        # With max_depth=1, only the seed (depth=0) is emitted; depth=1 links are
        # added to the frontier but rejected by add_links since depth > max_depth.
        assert "https://example.com/about" not in fetched_urls

    async def test_depth_2_follows_one_hop(self, mock_bs4, mock_robots_none, mock_ingest) -> None:
        """crawl(max_depth=2) must fetch seed + depth-1 links."""
        connector = WebCrawlerConnector(_make_config(["https://example.com"], max_depth=2))
        results = await connector.crawl(["https://example.com"], max_depth=2, ingest=False, same_origin=True)
        fetched_urls = {r.url for r in results}
        assert "https://example.com" in fetched_urls
        assert "https://example.com/about" in fetched_urls
        assert "https://example.com/blog" in fetched_urls
        # /contact is linked from /about at depth=2; adding it would require
        # depth=3 in the frontier, so it should NOT appear.
        assert "https://example.com/contact" not in fetched_urls

    async def test_depth_3_follows_two_hops(self, mock_bs4, mock_robots_none, mock_ingest) -> None:
        """crawl(max_depth=3) must fetch seed + two link-hops deep."""
        connector = WebCrawlerConnector(_make_config(["https://example.com"], max_depth=3))
        results = await connector.crawl(["https://example.com"], max_depth=3, ingest=False, same_origin=True)
        fetched_urls = {r.url for r in results}
        assert "https://example.com/contact" in fetched_urls


# ---------------------------------------------------------------------------
# Same-origin tests
# ---------------------------------------------------------------------------


class TestSameOrigin:
    """same_origin=True must reject cross-domain links."""

    async def test_same_origin_true_rejects_external(self, mock_bs4, mock_robots_none) -> None:
        connector = WebCrawlerConnector(_make_config(["https://example.com"], max_depth=2))
        results = await connector.crawl(["https://example.com"], max_depth=2, ingest=False, same_origin=True)
        fetched_urls = {r.url for r in results}
        assert not any("external.com" in u for u in fetched_urls)

    async def test_same_origin_false_allows_external(self, mock_bs4, mock_robots_none) -> None:
        connector = WebCrawlerConnector(_make_config(["https://example.com"], max_depth=2, same_origin=False))
        results = await connector.crawl(["https://example.com"], max_depth=2, ingest=False, same_origin=False)
        fetched_urls = {r.url for r in results}
        assert "https://external.com/page" in fetched_urls


# ---------------------------------------------------------------------------
# Robots enforcement tests
# ---------------------------------------------------------------------------


class TestRobotsEnforcement:
    """respect_robots controls whether RobotsCache is consulted."""

    async def test_respect_robots_true_builds_cache(self, mock_bs4, mock_robots_allow) -> None:
        """When respect_robots=True, _build_robots_cache is called with True."""
        connector = WebCrawlerConnector(_make_config(["https://example.com"]))
        await connector.crawl(["https://example.com"], max_depth=1, ingest=False, respect_robots=True)
        mock_robots_allow.assert_awaited_once_with(True)

    async def test_respect_robots_false_skips_cache(self, mock_bs4, mock_robots_none) -> None:
        """When respect_robots=False, no RobotsCache is used (returns None)."""
        connector = WebCrawlerConnector(_make_config(["https://example.com"]))
        await connector.crawl(["https://example.com"], max_depth=1, ingest=False, respect_robots=False)
        mock_robots_none.assert_awaited_once_with(False)

    async def test_robots_blocked_url_skipped(self, mock_bs4) -> None:
        """URL disallowed by robots.txt returns a robots_blocked FetchResult."""
        connector = WebCrawlerConnector(_make_config(["https://example.com"], max_depth=1))
        with patch("knowledge.connectors.web_crawler.WebCrawlerConnector._build_robots_cache") as m:
            cache = MagicMock()
            cache.is_allowed = AsyncMock(return_value=False)
            m.return_value = cache
            results = await connector.crawl(["https://example.com"], max_depth=1, ingest=False, respect_robots=True)
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error_code == "robots_blocked"


# ---------------------------------------------------------------------------
# max_pages cap tests
# ---------------------------------------------------------------------------


class TestMaxPagesCap:
    """max_pages hard cap is respected regardless of depth."""

    async def test_max_pages_honored(self, mock_bs4, mock_robots_none) -> None:
        """crawl must stop after max_pages pages regardless of frontier size."""
        connector = WebCrawlerConnector(_make_config(["https://example.com"], max_depth=3, max_pages=2))
        results = await connector.crawl(
            ["https://example.com"], max_depth=3, max_pages=2, ingest=False, same_origin=True
        )
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# Ingest path tests
# ---------------------------------------------------------------------------


class TestIngestPath:
    """ingest=True must call _ingest_results_to_kb."""

    async def test_ingest_true_calls_ingest(self, mock_bs4, mock_robots_none) -> None:
        connector = WebCrawlerConnector(_make_config(["https://example.com"]))
        with patch("knowledge.connectors.web_crawler._ingest_results_to_kb", new=AsyncMock()) as mock_ingest_fn:
            await connector.crawl(["https://example.com"], max_depth=1, ingest=True)
            mock_ingest_fn.assert_awaited_once()

    async def test_ingest_false_skips_ingest(self, mock_bs4, mock_robots_none) -> None:
        connector = WebCrawlerConnector(_make_config(["https://example.com"]))
        with patch("knowledge.connectors.web_crawler._ingest_results_to_kb", new=AsyncMock()) as mock_ingest_fn:
            await connector.crawl(["https://example.com"], max_depth=1, ingest=False)
            mock_ingest_fn.assert_not_awaited()


# ---------------------------------------------------------------------------
# Scheduler / sync path tests
# ---------------------------------------------------------------------------


class TestSyncSchedulerPath:
    """connector.sync() must call crawl() with config-driven depth."""

    @pytest.fixture()
    def mock_crawl(self):
        with patch.object(WebCrawlerConnector, "crawl", new=AsyncMock(return_value=[])) as m:
            yield m

    async def test_sync_calls_crawl_with_config_depth(self, mock_crawl) -> None:
        """Scheduler-triggered sync(incremental=True) must call crawl()."""
        cfg = _make_config(["https://example.com"], max_depth=3, max_pages=50)
        connector = WebCrawlerConnector(cfg)
        result = await connector.sync(incremental=True)

        mock_crawl.assert_awaited_once_with(
            seed_urls=["https://example.com"],
            max_depth=3,
            max_pages=50,
            respect_robots=True,
            ingest=False,
            same_origin=True,
            on_seed_complete=ANY,
        )
        assert result.status == "success"

    async def test_sync_returns_sync_result(self, mock_crawl) -> None:
        connector = WebCrawlerConnector(_make_config(["https://example.com"]))
        result = await connector.sync(incremental=False)
        assert isinstance(result, SyncResult)
        assert result.connector_id == "test-crawler"

    async def test_sync_error_sets_failed_status(self) -> None:
        """sync() must catch exceptions and return status='failed'."""
        connector = WebCrawlerConnector(_make_config(["https://example.com"]))
        with patch.object(WebCrawlerConnector, "crawl", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await connector.sync(incremental=True)
        assert result.status == "failed"
        assert any("boom" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Backward compat tests
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """crawl(max_depth=1) default must behave like the pre-change seed-only fetch."""

    async def test_default_depth_1_only_fetches_seeds(self, mock_bs4, mock_robots_none) -> None:
        """Default max_depth=1 returns only the seed page — no link following."""
        connector = WebCrawlerConnector(_make_config(["https://example.com"], max_depth=1))
        results = await connector.crawl(
            seed_urls=["https://example.com"],
            max_depth=1,
            ingest=False,
        )
        fetched_urls = [r.url for r in results]
        # Only the seed should be fetched (depth=0 only with max_depth=1)
        assert fetched_urls == ["https://example.com"]

    async def test_discover_sources_returns_seed_info(self) -> None:
        connector = WebCrawlerConnector(_make_config(["https://example.com/page"]))
        sources = await connector.discover_sources()
        assert len(sources) == 1
        assert sources[0].path == "https://example.com/page"
        assert sources[0].source_id == _url_to_source_id("https://example.com/page")

    async def test_fetch_content_uses_web_fetcher(self, mock_bs4, mock_robots_none) -> None:
        """fetch_content falls back to WebFetcher.fetch() for the single-URL path."""
        connector = WebCrawlerConnector(_make_config(["https://example.com"]))
        source_id = _url_to_source_id("https://example.com")
        fetch_result = _make_fetch_result("https://example.com", markdown="# Hello")
        with patch(
            "knowledge.connectors.web_crawler.WebFetcher.fetch",
            new=AsyncMock(return_value=fetch_result),
        ):
            content = await connector.fetch_content(source_id)
        assert content is not None
        assert content.content == "# Hello"

    async def test_fetch_content_unknown_source_id_returns_none(self) -> None:
        connector = WebCrawlerConnector(_make_config(["https://example.com"]))
        result = await connector.fetch_content("deadbeef" * 4)
        assert result is None


# ---------------------------------------------------------------------------
# Error propagation and checkpoint correctness tests (#8296, #8297)
# ---------------------------------------------------------------------------


class TestSync:
    async def test_sync_result_errors_propagated(self) -> None:
        """GH#8296: errors from _ingest_content must appear in SyncResult.errors."""
        cfg = _make_config(["https://example.com"])
        connector = WebCrawlerConnector(cfg)
        fetch_result = _make_fetch_result("https://example.com", markdown="# Some content here for ingest.")
        with patch.object(WebCrawlerConnector, "crawl", new=AsyncMock(return_value=[fetch_result])):
            with patch.object(connector, "_ingest_content", new=AsyncMock(side_effect=RuntimeError("ingest boom"))):
                result = await connector.sync(incremental=True)
        assert any("ingest boom" in e for e in result.errors)
        assert result.status == "partial"

    async def test_sync_only_checkpoints_crawled_seeds(self) -> None:
        """GH#8297: only seeds that actually started crawling are checkpointed."""
        urls = ["https://a.com", "https://b.com", "https://c.com"]
        cfg = _make_config(urls, max_pages=1)
        connector = WebCrawlerConnector(cfg)

        written: list = []

        def _capture(source_id: str) -> None:
            written.append(source_id)

        fetch_a = _make_fetch_result("https://a.com", markdown="content a")

        with patch.object(connector, "_crawl_seed", new=AsyncMock(return_value=[fetch_a])):
            with patch.object(connector, "_write_checkpoint", new=AsyncMock(side_effect=_capture)):
                with patch("knowledge.connectors.web_crawler._ingest_results_to_kb", new=AsyncMock()):
                    await connector.sync(incremental=True)

        assert _url_to_source_id("https://c.com") not in written
