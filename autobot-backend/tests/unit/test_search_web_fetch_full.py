# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for search_web fetch_full mode. Issue #7404.

Covers:
- Backward compat: fetch_full=False returns identical shape to current.
- Happy path: fetch_full=True returns each result with markdown populated.
- Partial failure: one URL failing does not fail the whole call.
- Robots-disallowed URL returns markdown=None, fetch_error="robots_blocked".
- max_pages cap honored.
- WEB_SEARCH_SCHEMA updated with fetch_full/max_pages.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from chat_workflow.tool_handler import (
    WEB_SEARCH_SCHEMA,
    _fetch_pages_concurrent,
    _fetch_single_page,
    _format_full_search_results,
)
from web_fetch.types import ERR_ROBOTS_BLOCKED, FetchResult, RenderMode

# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestWebSearchSchemaUpdated:
    def test_fetch_full_in_schema(self) -> None:
        props = WEB_SEARCH_SCHEMA["properties"]
        assert "fetch_full" in props, "fetch_full must be in WEB_SEARCH_SCHEMA properties"
        assert props["fetch_full"]["type"] == "boolean"

    def test_max_pages_in_schema(self) -> None:
        props = WEB_SEARCH_SCHEMA["properties"]
        assert "max_pages" in props, "max_pages must be in WEB_SEARCH_SCHEMA properties"
        assert props["max_pages"]["type"] == "integer"
        assert props["max_pages"]["minimum"] == 1
        assert props["max_pages"]["maximum"] == 10

    def test_query_still_required(self) -> None:
        assert WEB_SEARCH_SCHEMA["required"] == ["query"]

    def test_fetch_full_not_required(self) -> None:
        assert "fetch_full" not in WEB_SEARCH_SCHEMA.get("required", [])

    def test_max_pages_not_required(self) -> None:
        assert "max_pages" not in WEB_SEARCH_SCHEMA.get("required", [])


# ---------------------------------------------------------------------------
# _fetch_single_page unit tests
# ---------------------------------------------------------------------------


class TestFetchSinglePage:
    @pytest.mark.asyncio
    async def test_success_attaches_markdown(self) -> None:
        entry = {"title": "Example", "url": "https://example.com", "snippet": "A page"}
        ok_result = FetchResult(
            url="https://example.com",
            success=True,
            markdown="# Hello\n\nSome content.",
            render_mode=RenderMode.AUTO,
            source="jina",
        )
        with patch("web_fetch.fetcher.WebFetcher.fetch", return_value=ok_result):
            result = await _fetch_single_page(entry)

        assert result["markdown"] == "# Hello\n\nSome content."
        assert result["fetch_error"] is None
        assert result["title"] == "Example"
        assert result["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_robots_blocked_returns_error_code(self) -> None:
        entry = {"title": "Blocked", "url": "https://blocked.com/private", "snippet": ""}
        blocked_result = FetchResult(
            url="https://blocked.com/private",
            success=False,
            error_code=ERR_ROBOTS_BLOCKED,
        )
        with patch("web_fetch.fetcher.WebFetcher.fetch", return_value=blocked_result):
            result = await _fetch_single_page(entry)

        assert result["markdown"] is None
        assert result["fetch_error"] == ERR_ROBOTS_BLOCKED

    @pytest.mark.asyncio
    async def test_http_500_returns_error_code(self) -> None:
        entry = {"title": "Error", "url": "https://server-error.com", "snippet": ""}
        error_result = FetchResult(
            url="https://server-error.com",
            success=False,
            error_code="http_error",
            status_code=500,
        )
        with patch("web_fetch.fetcher.WebFetcher.fetch", return_value=error_result):
            result = await _fetch_single_page(entry)

        assert result["markdown"] is None
        assert result["fetch_error"] == "http_error"

    @pytest.mark.asyncio
    async def test_exception_in_fetch_returns_unknown_error(self) -> None:
        entry = {"title": "Crash", "url": "https://crash.com", "snippet": ""}
        with patch("web_fetch.fetcher.WebFetcher.fetch", side_effect=RuntimeError("boom")):
            result = await _fetch_single_page(entry)

        assert result["markdown"] is None
        assert result["fetch_error"] == "unknown"

    @pytest.mark.asyncio
    async def test_missing_url_returns_no_url_error(self) -> None:
        entry = {"title": "No URL", "snippet": "no link here"}
        result = await _fetch_single_page(entry)
        assert result["markdown"] is None
        assert result["fetch_error"] == "no_url"


# ---------------------------------------------------------------------------
# _fetch_pages_concurrent — partial failure test
# ---------------------------------------------------------------------------


class TestFetchPagesConcurrent:
    @pytest.mark.asyncio
    async def test_partial_failure_does_not_abort_call(self) -> None:
        """One URL with HTTP 500 must not prevent other URLs from being fetched."""
        entries = [
            {"title": "Good 1", "url": "https://good1.com", "snippet": ""},
            {"title": "Bad", "url": "https://bad.com", "snippet": ""},
            {"title": "Good 2", "url": "https://good2.com", "snippet": ""},
        ]

        async def fake_fetch_side_effect(url, render):
            if "bad" in url:
                return FetchResult(url=url, success=False, error_code="http_error", status_code=500)
            return FetchResult(
                url=url, success=True, markdown=f"Content for {url}", render_mode=RenderMode.AUTO, source="jina"
            )

        with patch("web_fetch.fetcher.WebFetcher.fetch", side_effect=fake_fetch_side_effect):
            results = await _fetch_pages_concurrent(entries, max_pages=3)

        assert len(results) == 3
        assert results[0]["markdown"] is not None
        assert results[1]["markdown"] is None
        assert results[1]["fetch_error"] == "http_error"
        assert results[2]["markdown"] is not None

    @pytest.mark.asyncio
    async def test_max_pages_cap_respected(self) -> None:
        """Only max_pages entries should be fetched, even if more entries are provided."""
        entries = [{"title": f"Page {i}", "url": f"https://p{i}.com", "snippet": ""} for i in range(8)]
        ok = FetchResult(url="x", success=True, markdown="content", render_mode=RenderMode.AUTO, source="jina")

        with patch("web_fetch.fetcher.WebFetcher.fetch", return_value=ok):
            results = await _fetch_pages_concurrent(entries, max_pages=3)

        assert len(results) == 3


# ---------------------------------------------------------------------------
# _format_full_search_results
# ---------------------------------------------------------------------------


class TestFormatFullSearchResults:
    def test_includes_title_and_url(self) -> None:
        entries = [
            {
                "title": "Example",
                "url": "https://example.com",
                "snippet": "desc",
                "markdown": "# Hello",
                "fetch_error": None,
            }
        ]
        output = _format_full_search_results("test query", entries)
        assert "Example" in output
        assert "https://example.com" in output
        assert "# Hello" in output

    def test_failed_entry_shows_fetch_error(self) -> None:
        entries = [
            {
                "title": "Blocked",
                "url": "https://blocked.com",
                "snippet": "",
                "markdown": None,
                "fetch_error": "robots_blocked",
            }
        ]
        output = _format_full_search_results("test query", entries)
        assert "robots_blocked" in output
        assert "[Page fetch failed:" in output

    def test_markdown_truncated_at_4000_chars(self) -> None:
        long_md = "x" * 5000
        entries = [
            {"title": "Long", "url": "https://long.com", "snippet": "", "markdown": long_md, "fetch_error": None}
        ]
        output = _format_full_search_results("q", entries)
        # 4000 x's should appear, but not all 5000
        assert "x" * 4000 in output
        assert "x" * 4001 not in output


# ---------------------------------------------------------------------------
# Integration test: ToolHandlerMixin._execute_web_search_full
# ---------------------------------------------------------------------------


class TestExecuteWebSearchFull:
    @pytest.mark.asyncio
    async def test_full_search_happy_path(self) -> None:
        """fetch_full=True returns formatted results with markdown per entry."""
        from chat_workflow.tool_handler import ToolHandlerMixin

        mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
        fake_entries = [
            {"title": "Page A", "url": "https://a.com", "snippet": "Snippet A"},
            {"title": "Page B", "url": "https://b.com", "snippet": "Snippet B"},
        ]
        ok_result = FetchResult(
            url="x", success=True, markdown="Full content here.", render_mode=RenderMode.AUTO, source="jina"
        )

        with (
            patch.object(mixin, "_web_search_structured_entries", return_value=fake_entries),
            patch("web_fetch.fetcher.WebFetcher.fetch", return_value=ok_result),
        ):
            result = await mixin._execute_web_search_full("my query", max_pages=5)

        assert "Page A" in result
        assert "Page B" in result
        assert "Full content here." in result
        assert "full page content" in result.lower()

    @pytest.mark.asyncio
    async def test_full_search_falls_back_when_no_entries(self) -> None:
        """When no structured entries found, falls back DIRECTLY to
        ``_web_search_via_browser_vm`` (NOT through ``_execute_web_search``
        which would re-issue a Playwright call — see #7478).
        """
        from chat_workflow.tool_handler import ToolHandlerMixin

        mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)

        with (
            patch.object(mixin, "_web_search_structured_entries", return_value=[]),
            patch.object(
                mixin,
                "_web_search_via_browser_vm",
                return_value="Fallback results",
            ) as mock_fallback,
            # #7478 regression pin: _execute_web_search must NOT be called on
            # the empty-entries fallback path. If it were, _web_search_via_playwright
            # would re-issue the (already-failed) Playwright call.
            patch.object(
                mixin,
                "_execute_web_search",
                side_effect=AssertionError("_execute_web_search must NOT be called from full-search fallback (#7478)"),
            ),
        ):
            result = await mixin._execute_web_search_full("no results query", max_pages=5)

        mock_fallback.assert_called_once_with("no results query")
        assert result == "Fallback results"

    @pytest.mark.asyncio
    async def test_backward_compat_execute_web_search_unchanged(self) -> None:
        """_execute_web_search (no fetch_full) returns same string shape as before."""
        from chat_workflow.tool_handler import ToolHandlerMixin

        mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)

        with patch.object(
            mixin, "_web_search_via_playwright", return_value='Web search results for "q":\n\n1. Example'
        ):
            result = await mixin._execute_web_search("q")

        assert "Web search results" in result
        assert "Example" in result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _async_result(val):
    """Wrap a synchronous value in an awaitable."""
    return val
