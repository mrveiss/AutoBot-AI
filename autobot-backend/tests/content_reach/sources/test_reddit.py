# Copyright (c) 2024 mrveiss. All rights reserved.
# Unauthorized copying of this file, via any medium is strictly prohibited.
# Proprietary and confidential.
# Written by mrveiss.
"""Tests for content_reach.sources.reddit (RedditJsonBackend, HnAlgoliaBackend, build_reddit_chain)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from content_reach.base import BackendError, ContentRequest
from source_attribution import SourceType

# ---------------------------------------------------------------------------
# Sample JSON fixtures
# ---------------------------------------------------------------------------

_REDDIT_SEARCH_JSON = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "Post 1",
                    "selftext": "Content 1",
                    "permalink": "/r/python/comments/abc/post_1/",
                }
            },
            {
                "data": {
                    "title": "Post 2",
                    "selftext": "",
                    "permalink": "/r/python/comments/def/post_2/",
                }
            },
        ]
    }
}

_HN_ALGOLIA_JSON = {
    "hits": [
        {
            "title": "HN Post 1",
            "url": "https://example.com/1",
            "points": 42,
            "objectID": "12345",
        },
        {
            "story_title": "HN Post 2",
            "url": None,
            "points": 10,
            "objectID": "67890",
        },
    ]
}


def _make_sync_mock_client(status_code: int, body: dict | None = None):
    """Build a MagicMock httpx.Client whose .get() returns a fixed response."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = body or {}
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = mock_response
    return mock_client, mock_response


# ---------------------------------------------------------------------------
# RedditJsonBackend — search mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reddit_search_maps_posts():
    """Mock returns 2-post reddit search JSON; result.structured['posts'] has 2 entries."""
    from content_reach.sources.reddit import RedditJsonBackend

    mock_client, _ = _make_sync_mock_client(200, _REDDIT_SEARCH_JSON)
    backend = RedditJsonBackend(client=mock_client)
    request = ContentRequest(query="python tips", limit=2)
    result = await backend.fetch(request)

    assert result.success is True
    assert result.source_type is SourceType.REDDIT
    posts = result.structured["posts"]
    assert len(posts) == 2
    assert posts[0]["title"] == "Post 1"
    assert posts[1]["title"] == "Post 2"


@pytest.mark.asyncio
async def test_reddit_search_sends_user_agent():
    """fetch() sends the expected User-Agent header."""
    from content_reach.sources.reddit import RedditJsonBackend, _USER_AGENT

    mock_client, _ = _make_sync_mock_client(200, _REDDIT_SEARCH_JSON)
    backend = RedditJsonBackend(client=mock_client)
    request = ContentRequest(query="python tips", limit=2)
    await backend.fetch(request)

    call_kwargs = mock_client.get.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert headers.get("User-Agent") == _USER_AGENT


# ---------------------------------------------------------------------------
# RedditJsonBackend — URL mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reddit_url_mode_appends_json():
    """URL mode with reddit.com URL appends .json suffix."""
    from content_reach.sources.reddit import RedditJsonBackend

    mock_client, _ = _make_sync_mock_client(200, _REDDIT_SEARCH_JSON)
    backend = RedditJsonBackend(client=mock_client)
    request = ContentRequest(url="https://www.reddit.com/r/python")
    await backend.fetch(request)

    called_url = mock_client.get.call_args.args[0]
    assert called_url.endswith(".json")


@pytest.mark.asyncio
async def test_reddit_url_mode_no_double_json():
    """URL already ending in .json does not get a second .json appended."""
    from content_reach.sources.reddit import RedditJsonBackend

    mock_client, _ = _make_sync_mock_client(200, _REDDIT_SEARCH_JSON)
    backend = RedditJsonBackend(client=mock_client)
    request = ContentRequest(url="https://www.reddit.com/r/python.json")
    await backend.fetch(request)

    called_url = mock_client.get.call_args.args[0]
    assert not called_url.endswith(".json.json")
    assert called_url.endswith(".json")


# ---------------------------------------------------------------------------
# RedditJsonBackend — error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reddit_non200_raises_backend_error():
    """Non-200 response raises BackendError."""
    from content_reach.sources.reddit import RedditJsonBackend

    mock_client, _ = _make_sync_mock_client(403)
    backend = RedditJsonBackend(client=mock_client)
    request = ContentRequest(query="python")
    with pytest.raises(BackendError, match="403"):
        await backend.fetch(request)


@pytest.mark.asyncio
async def test_reddit_empty_children_raises_backend_error():
    """Reddit JSON with empty data.children raises BackendError."""
    from content_reach.sources.reddit import RedditJsonBackend

    empty_json = {"data": {"children": []}}
    mock_client, _ = _make_sync_mock_client(200, empty_json)
    backend = RedditJsonBackend(client=mock_client)
    request = ContentRequest(query="python")
    with pytest.raises(BackendError, match="no posts"):
        await backend.fetch(request)


# ---------------------------------------------------------------------------
# HnAlgoliaBackend — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hn_maps_hits():
    """Mock returns 2-hit algolia JSON; result.structured['hits'] has 2 entries with hn_url."""
    from content_reach.sources.reddit import HnAlgoliaBackend

    mock_client, _ = _make_sync_mock_client(200, _HN_ALGOLIA_JSON)
    backend = HnAlgoliaBackend(client=mock_client)
    request = ContentRequest(query="python asyncio")
    result = await backend.fetch(request)

    assert result.success is True
    assert result.source_type is SourceType.REDDIT
    hits = result.structured["hits"]
    assert len(hits) == 2
    # First hit: has url field
    assert hits[0]["hn_url"] == "https://news.ycombinator.com/item?id=12345"
    # Second hit: url is None → fallback hn_url
    assert hits[1]["hn_url"] == "https://news.ycombinator.com/item?id=67890"
    # Second hit: story_title used
    assert hits[1]["title"] == "HN Post 2"


# ---------------------------------------------------------------------------
# HnAlgoliaBackend — error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hn_empty_hits_raises_backend_error():
    """Algolia response with empty hits raises BackendError."""
    from content_reach.sources.reddit import HnAlgoliaBackend

    mock_client, _ = _make_sync_mock_client(200, {"hits": []})
    backend = HnAlgoliaBackend(client=mock_client)
    request = ContentRequest(query="python asyncio")
    with pytest.raises(BackendError, match="no hits"):
        await backend.fetch(request)


# ---------------------------------------------------------------------------
# Shared — httpx.HTTPError wrapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_httpx_error_raises_backend_error():
    """httpx.HTTPError from either backend is wrapped into BackendError."""
    from content_reach.sources.reddit import HnAlgoliaBackend, RedditJsonBackend

    for BackendCls in (RedditJsonBackend, HnAlgoliaBackend):
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.HTTPError("connection failed")
        backend = BackendCls(client=mock_client)
        request = ContentRequest(query="test")
        with pytest.raises(BackendError):
            await backend.fetch(request)


# ---------------------------------------------------------------------------
# build_reddit_chain()
# ---------------------------------------------------------------------------


def test_build_reddit_chain_backend_names():
    """build_reddit_chain() returns chain with backends: reddit_json, hn_algolia, browser."""
    from content_reach.sources.reddit import build_reddit_chain

    chain = build_reddit_chain()
    assert chain.backend_names() == ["reddit_json", "hn_algolia", "browser"]
