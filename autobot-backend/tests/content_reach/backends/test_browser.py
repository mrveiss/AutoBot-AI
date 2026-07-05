# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for content_reach.backends.browser (BrowserBackend, BrowserSearchBackend)."""

from __future__ import annotations

import pytest

from content_reach.base import BackendError, ContentRequest
from content_reach.backends.browser import BrowserBackend, BrowserSearchBackend
from source_attribution import SourceType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubManager:
    """Minimal stub for the research browser manager."""

    def __init__(self, result: dict) -> None:
        self._result = result
        self.last_url: str | None = None

    async def research_url(self, conversation_id: str, url: str, extract_content: bool = True) -> dict:
        self.last_url = url
        return self._result


# ---------------------------------------------------------------------------
# probe()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browser_probe_reflects_playwright_available_true(monkeypatch):
    import research_browser_manager as rbm

    monkeypatch.setattr(rbm, "PLAYWRIGHT_AVAILABLE", True)
    backend = BrowserBackend(source_type=SourceType.WEB_PAGE)
    assert await backend.probe() is True


@pytest.mark.asyncio
async def test_browser_probe_reflects_playwright_available_false(monkeypatch):
    import research_browser_manager as rbm

    monkeypatch.setattr(rbm, "PLAYWRIGHT_AVAILABLE", False)
    backend = BrowserBackend(source_type=SourceType.WEB_PAGE)
    assert await backend.probe() is False


# ---------------------------------------------------------------------------
# fetch() — BrowserBackend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browser_fetch_maps_research_result(monkeypatch):
    stub_manager = _StubManager(
        {
            "success": True,
            "content": {
                "text_content": "hello",
                "structured_data": {"headings": []},
            },
            "title": "T",
        }
    )
    import content_reach.backends.browser as browser_mod

    monkeypatch.setattr(browser_mod, "_get_manager", lambda: stub_manager)

    backend = BrowserBackend(source_type=SourceType.WEB_PAGE)
    request = ContentRequest(url="https://example.com", query="")
    result = await backend.fetch(request)

    assert result.success is True
    assert result.text == "hello"
    assert result.backend_used == "browser"
    assert result.url == request.url
    assert result.structured == {"headings": []}


@pytest.mark.asyncio
async def test_browser_fetch_raises_without_url(monkeypatch):
    import content_reach.backends.browser as browser_mod

    monkeypatch.setattr(browser_mod, "_get_manager", lambda: _StubManager({}))

    backend = BrowserBackend(source_type=SourceType.WEB_PAGE)
    request = ContentRequest(query="x")  # url defaults to ""
    with pytest.raises(BackendError, match="url"):
        await backend.fetch(request)


@pytest.mark.asyncio
async def test_browser_fetch_raises_on_unsuccessful(monkeypatch):
    stub_manager = _StubManager({"success": False})
    import content_reach.backends.browser as browser_mod

    monkeypatch.setattr(browser_mod, "_get_manager", lambda: stub_manager)

    backend = BrowserBackend(source_type=SourceType.WEB_PAGE)
    request = ContentRequest(url="https://example.com")
    with pytest.raises(BackendError):
        await backend.fetch(request)


# ---------------------------------------------------------------------------
# fetch() — BrowserSearchBackend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browser_search_builds_ddg_url(monkeypatch):
    stub_manager = _StubManager(
        {
            "success": True,
            "content": {"text_content": "results", "structured_data": {}},
            "title": "DDG",
        }
    )
    import content_reach.backends.browser as browser_mod

    monkeypatch.setattr(browser_mod, "_get_manager", lambda: stub_manager)

    backend = BrowserSearchBackend(source_type=SourceType.WEB_SEARCH)
    request = ContentRequest(query="cats dogs")
    await backend.fetch(request)

    # The URL passed to research_url must be the DDG search URL with encoded query
    assert stub_manager.last_url is not None
    assert "duckduckgo.com" in stub_manager.last_url
    # Accept both + and %20 encoding — urllib.parse.quote_plus uses +
    assert "cats" in stub_manager.last_url
    assert "dogs" in stub_manager.last_url
