# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for ContentReachSearchProvider (#10932)."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_loop.search.content_reach_provider import ContentReachSearchProvider


def _make_success_result(structured: Dict[str, Any] | None = None, text: str = "", url: str = "") -> MagicMock:
    """Build a mock ContentResult with success=True."""
    r = MagicMock()
    r.success = True
    r.structured = structured or {}
    r.text = text
    r.url = url
    r.metadata = {}
    return r


def _make_failure_result() -> MagicMock:
    r = MagicMock()
    r.success = False
    r.structured = {}
    r.text = ""
    r.url = ""
    r.metadata = {"error": "all backends failed"}
    return r


def _make_registry(result: MagicMock, *, chain_present: bool = True) -> MagicMock:
    """Build a mock ContentSourceRegistry."""
    reg = MagicMock()
    reg.get_chain = MagicMock(return_value=MagicMock() if chain_present else None)
    reg.fetch = AsyncMock(return_value=result)
    return reg


@pytest.mark.asyncio
async def test_structured_results_mapped_to_search_results():
    structured = {
        "results": [
            {"title": "Result One", "href": "https://example.com/1", "body": "Snippet one content here"},
            {"title": "Result Two", "href": "https://example.com/2", "body": "Snippet two content here"},
        ]
    }
    reg = _make_registry(_make_success_result(structured=structured))
    provider = ContentReachSearchProvider()

    with patch("agent_loop.search.content_reach_provider.ContentReachSearchProvider._ensure_registered"):
        with patch("content_reach.registry.get_content_source_registry", return_value=reg):
            results = await provider.search("test query", count=5)

    assert len(results) == 2
    assert results[0].title == "Result One"
    assert results[0].url == "https://example.com/1"
    assert results[0].snippet == "Snippet one content here"
    assert results[0].source == "content_reach"
    assert results[1].url == "https://example.com/2"


@pytest.mark.asyncio
async def test_structured_results_skips_entries_without_url():
    structured = {
        "results": [
            {"title": "No URL entry", "href": "", "body": "body"},
            {"title": "Has URL", "href": "https://example.com/ok", "body": "good"},
        ]
    }
    reg = _make_registry(_make_success_result(structured=structured))
    provider = ContentReachSearchProvider()

    with patch("agent_loop.search.content_reach_provider.ContentReachSearchProvider._ensure_registered"):
        with patch("content_reach.registry.get_content_source_registry", return_value=reg):
            results = await provider.search("q")

    assert len(results) == 1
    assert results[0].url == "https://example.com/ok"


@pytest.mark.asyncio
async def test_structured_results_capped_at_count():
    items = [{"title": f"T{i}", "href": f"https://example.com/{i}", "body": "b"} for i in range(10)]
    reg = _make_registry(_make_success_result(structured={"results": items}))
    provider = ContentReachSearchProvider()

    with patch("agent_loop.search.content_reach_provider.ContentReachSearchProvider._ensure_registered"):
        with patch("content_reach.registry.get_content_source_registry", return_value=reg):
            results = await provider.search("q", count=3)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_text_only_result_returns_single_search_result():
    """JinaSearchBackend returns text + url but no structured results."""
    reg = _make_registry(
        _make_success_result(
            structured={},
            text="Some jina result text",
            url="https://s.jina.ai/test",
        )
    )
    provider = ContentReachSearchProvider()

    with patch("agent_loop.search.content_reach_provider.ContentReachSearchProvider._ensure_registered"):
        with patch("content_reach.registry.get_content_source_registry", return_value=reg):
            results = await provider.search("test query")

    assert len(results) == 1
    assert results[0].url == "https://s.jina.ai/test"
    assert results[0].snippet == "Some jina result text"
    assert results[0].source == "content_reach"


@pytest.mark.asyncio
async def test_text_only_without_url_returns_empty():
    """Text result with no URL → no usable SearchResult."""
    reg = _make_registry(_make_success_result(structured={}, text="some text", url=""))
    provider = ContentReachSearchProvider()

    with patch("agent_loop.search.content_reach_provider.ContentReachSearchProvider._ensure_registered"):
        with patch("content_reach.registry.get_content_source_registry", return_value=reg):
            results = await provider.search("q")

    assert results == []


@pytest.mark.asyncio
async def test_unsuccessful_result_returns_empty():
    reg = _make_registry(_make_failure_result())
    provider = ContentReachSearchProvider()

    with patch("agent_loop.search.content_reach_provider.ContentReachSearchProvider._ensure_registered"):
        with patch("content_reach.registry.get_content_source_registry", return_value=reg):
            results = await provider.search("q")

    assert results == []


@pytest.mark.asyncio
async def test_is_available_returns_true():
    provider = ContentReachSearchProvider()
    assert await provider.is_available() is True


@pytest.mark.asyncio
async def test_ensure_registered_calls_register_default_sources_when_chain_absent():
    """When web_search chain is absent, register_default_sources should be called."""
    reg = MagicMock()
    reg.get_chain = MagicMock(return_value=None)

    provider = ContentReachSearchProvider()

    with patch("content_reach.bootstrap.register_default_sources") as mock_register:
        provider._ensure_registered(reg)
        mock_register.assert_called_once_with(reg)


@pytest.mark.asyncio
async def test_ensure_registered_skips_when_chain_present():
    """When web_search chain already exists, register_default_sources must NOT be called."""
    reg = MagicMock()
    reg.get_chain = MagicMock(return_value=MagicMock())

    provider = ContentReachSearchProvider()

    with patch("content_reach.bootstrap.register_default_sources") as mock_register:
        provider._ensure_registered(reg)
        mock_register.assert_not_called()


@pytest.mark.asyncio
async def test_snippet_truncated_at_300_chars():
    long_body = "x" * 500
    structured = {"results": [{"title": "T", "href": "https://example.com/x", "body": long_body}]}
    reg = _make_registry(_make_success_result(structured=structured))
    provider = ContentReachSearchProvider()

    with patch("agent_loop.search.content_reach_provider.ContentReachSearchProvider._ensure_registered"):
        with patch("content_reach.registry.get_content_source_registry", return_value=reg):
            results = await provider.search("q")

    assert len(results[0].snippet) == 300
