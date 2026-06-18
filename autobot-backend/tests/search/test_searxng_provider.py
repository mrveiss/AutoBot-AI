# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Offline unit tests for SearXNGSearchProvider (#9022)."""

from __future__ import annotations

import pytest

import agent_loop.search.searxng_provider as searxng_mod
from agent_loop.search.base import CATEGORY_NEWS
from agent_loop.search.searxng_provider import SearXNGSearchProvider
from tests.search.conftest import FakeHTTPClient, FakeResponse

_SAMPLE = {
    "results": [
        {
            "title": "Result One",
            "url": "https://example.com/1",
            "content": "First snippet",
            "engine": "duckduckgo",
            "publishedDate": "2026-06-01",
        },
        {"title": "Result Two", "url": "https://example.com/2", "content": "Second snippet"},
    ]
}


def _patch_client(monkeypatch, client: FakeHTTPClient) -> None:
    monkeypatch.setattr(searxng_mod, "get_http_client", lambda: client)


@pytest.mark.asyncio
async def test_search_normalizes_results(monkeypatch):
    client = FakeHTTPClient(FakeResponse(json_data=_SAMPLE))
    _patch_client(monkeypatch, client)
    provider = SearXNGSearchProvider(settings={"instance_url": "https://searx.local/"})

    results = await provider.search("python")

    assert [r.url for r in results] == ["https://example.com/1", "https://example.com/2"]
    assert results[0].title == "Result One"
    assert results[0].snippet == "First snippet"
    assert results[0].freshness == "2026-06-01"
    assert results[0].source == "duckduckgo"
    # Trailing slash on instance_url is stripped (no double slash in URL).
    assert client.calls[0]["url"] == "https://searx.local/search"


@pytest.mark.asyncio
async def test_category_maps_to_searxng_categories(monkeypatch):
    client = FakeHTTPClient(FakeResponse(json_data=_SAMPLE))
    _patch_client(monkeypatch, client)
    provider = SearXNGSearchProvider(settings={"instance_url": "https://searx.local"})

    await provider.search("breaking", category=CATEGORY_NEWS)

    assert client.calls[0]["params"]["categories"] == "news"
    assert client.calls[0]["params"]["format"] == "json"


@pytest.mark.asyncio
async def test_basic_auth_and_token_headers(monkeypatch):
    client = FakeHTTPClient(FakeResponse(json_data=_SAMPLE))
    _patch_client(monkeypatch, client)
    provider = SearXNGSearchProvider(
        settings={
            "instance_url": "https://searx.local",
            "basic_auth_user": "u",
            "basic_auth_pass": "p",
            "token": "tok123",
        }
    )

    await provider.search("query")

    call = client.calls[0]
    assert call["headers"]["Authorization"] == "Bearer tok123"
    assert call["auth"].login == "u"
    assert call["auth"].password == "p"


@pytest.mark.asyncio
async def test_count_limits_results(monkeypatch):
    client = FakeHTTPClient(FakeResponse(json_data=_SAMPLE))
    _patch_client(monkeypatch, client)
    provider = SearXNGSearchProvider(settings={"instance_url": "https://searx.local"})

    results = await provider.search("q", count=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_non_200_raises_for_fallback(monkeypatch):
    client = FakeHTTPClient(FakeResponse(status=502, text="bad gateway"))
    _patch_client(monkeypatch, client)
    provider = SearXNGSearchProvider(settings={"instance_url": "https://searx.local"})

    with pytest.raises(RuntimeError):
        await provider.search("q")


@pytest.mark.asyncio
async def test_unconfigured_is_unavailable_and_raises():
    provider = SearXNGSearchProvider(settings={})
    assert await provider.is_available() is False
    with pytest.raises(RuntimeError):
        await provider.search("q")


@pytest.mark.asyncio
async def test_configured_is_available():
    provider = SearXNGSearchProvider(settings={"instance_url": "https://searx.local"})
    assert await provider.is_available() is True
