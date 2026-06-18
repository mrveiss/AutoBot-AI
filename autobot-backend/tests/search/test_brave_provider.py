# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Offline unit tests for BraveSearchProvider (#9023)."""

from __future__ import annotations

import pytest

import agent_loop.search.brave_provider as brave_mod
from agent_loop.search.base import CATEGORY_NEWS
from agent_loop.search.brave_provider import BraveSearchProvider
from tests.search.conftest import FakeHTTPClient, FakeResponse

_WEB_SAMPLE = {
    "web": {
        "results": [
            {
                "title": "Brave One",
                "url": "https://example.com/a",
                "description": "Web snippet",
                "age": "2 days ago",
                "meta_url": {"hostname": "example.com"},
            },
            {"title": "Brave Two", "url": "https://example.com/b", "description": "Second"},
        ]
    }
}

_NEWS_SAMPLE = {
    "results": [
        {"title": "News One", "url": "https://news.example/1", "description": "News snippet", "page_age": "1h"}
    ]
}


def _patch_client(monkeypatch, client: FakeHTTPClient) -> None:
    monkeypatch.setattr(brave_mod, "get_http_client", lambda: client)


@pytest.mark.asyncio
async def test_web_search_normalizes_and_sets_auth_header(monkeypatch):
    client = FakeHTTPClient(FakeResponse(json_data=_WEB_SAMPLE))
    _patch_client(monkeypatch, client)
    provider = BraveSearchProvider(settings={"api_key": "key-abc"})

    results = await provider.search("python")

    assert [r.url for r in results] == ["https://example.com/a", "https://example.com/b"]
    assert results[0].title == "Brave One"
    assert results[0].snippet == "Web snippet"
    assert results[0].freshness == "2 days ago"
    assert results[0].source == "example.com"
    call = client.calls[0]
    assert call["headers"]["X-Subscription-Token"] == "key-abc"
    assert call["url"].endswith("/web/search")


@pytest.mark.asyncio
async def test_news_category_uses_news_endpoint(monkeypatch):
    client = FakeHTTPClient(FakeResponse(json_data=_NEWS_SAMPLE))
    _patch_client(monkeypatch, client)
    provider = BraveSearchProvider(settings={"api_key": "key-abc"})

    results = await provider.search("headline", category=CATEGORY_NEWS)

    assert client.calls[0]["url"].endswith("/news/search")
    assert results[0].title == "News One"
    assert results[0].freshness == "1h"


@pytest.mark.asyncio
async def test_rate_limit_raises_for_fallback(monkeypatch):
    client = FakeHTTPClient(FakeResponse(status=429, text="quota"))
    _patch_client(monkeypatch, client)
    provider = BraveSearchProvider(settings={"api_key": "key-abc"})

    with pytest.raises(RuntimeError, match="429"):
        await provider.search("q")


@pytest.mark.asyncio
async def test_other_error_raises(monkeypatch):
    client = FakeHTTPClient(FakeResponse(status=500, text="boom"))
    _patch_client(monkeypatch, client)
    provider = BraveSearchProvider(settings={"api_key": "key-abc"})

    with pytest.raises(RuntimeError):
        await provider.search("q")


@pytest.mark.asyncio
async def test_count_param_and_limit(monkeypatch):
    client = FakeHTTPClient(FakeResponse(json_data=_WEB_SAMPLE))
    _patch_client(monkeypatch, client)
    provider = BraveSearchProvider(settings={"api_key": "key-abc"})

    results = await provider.search("q", count=1)

    assert client.calls[0]["params"]["count"] == "1"
    assert len(results) == 1


@pytest.mark.asyncio
async def test_unconfigured_unavailable_and_raises():
    provider = BraveSearchProvider(settings={})
    assert await provider.is_available() is False
    with pytest.raises(RuntimeError):
        await provider.search("q")
