# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for content_reach.sources.web_search (DdgsBackend, JinaSearchBackend, build_web_search_chain)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from content_reach.base import BackendError, ContentRequest
from source_attribution import SourceType

# ---------------------------------------------------------------------------
# DdgsBackend — probe()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ddgs_probe_true_when_importable():
    """probe() returns True when ddgs is importable (ddgs is installed here)."""
    pytest.importorskip("ddgs")
    from content_reach.sources.web_search import DdgsBackend

    backend = DdgsBackend()
    result = await backend.probe()
    assert result is True


@pytest.mark.asyncio
async def test_ddgs_probe_false_when_absent(monkeypatch):
    """probe() returns False when the lazy import helper raises ImportError."""
    from content_reach.sources import web_search as ws_mod

    monkeypatch.setattr(ws_mod, "_import_ddgs", lambda: (_ for _ in ()).throw(ImportError("no ddgs")))

    from content_reach.sources.web_search import DdgsBackend

    backend = DdgsBackend()
    result = await backend.probe()
    assert result is False


# ---------------------------------------------------------------------------
# DdgsBackend — fetch()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ddgs_fetch_maps_results(monkeypatch):
    """fetch() maps two DDGS results into ContentResult correctly."""
    from content_reach.sources import web_search as ws_mod

    fake_results = [
        {"title": "Alpha", "href": "https://alpha.com", "body": "Alpha snippet"},
        {"title": "Beta", "href": "https://beta.com", "body": "Beta snippet"},
    ]

    mock_ddgs_cls = MagicMock()
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = fake_results
    mock_ddgs_cls.return_value = mock_ddgs_instance

    monkeypatch.setattr(ws_mod, "DDGS", mock_ddgs_cls)

    from content_reach.sources.web_search import DdgsBackend

    backend = DdgsBackend()
    request = ContentRequest(query="test query", limit=2)
    result = await backend.fetch(request)

    assert result.success is True
    assert result.backend_used == "ddgs"
    assert result.source_type is SourceType.WEB_SEARCH
    assert len(result.structured["results"]) == 2
    assert result.structured["results"][0]["title"] == "Alpha"
    assert "Alpha" in result.text


@pytest.mark.asyncio
async def test_ddgs_fetch_empty_raises(monkeypatch):
    """.text() returning [] causes BackendError so the chain falls through."""
    from content_reach.sources import web_search as ws_mod

    mock_ddgs_cls = MagicMock()
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = []
    mock_ddgs_cls.return_value = mock_ddgs_instance

    monkeypatch.setattr(ws_mod, "DDGS", mock_ddgs_cls)

    from content_reach.sources.web_search import DdgsBackend

    backend = DdgsBackend()
    request = ContentRequest(query="empty query")
    with pytest.raises(BackendError):
        await backend.fetch(request)


# ---------------------------------------------------------------------------
# JinaSearchBackend — fetch()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jina_search_fetch():
    """fetch() maps a 200 response into a successful ContentResult."""
    from content_reach.sources.web_search import JinaSearchBackend

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Result text from Jina"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    # Support async context manager usage
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    backend = JinaSearchBackend(client=mock_client)
    request = ContentRequest(query="jina test query")
    result = await backend.fetch(request)

    assert result.success is True
    assert result.backend_used == "jina_search"
    assert result.source_type is SourceType.WEB_SEARCH
    assert "Result text from Jina" in result.text


@pytest.mark.asyncio
async def test_jina_search_non_200_raises():
    """Non-200 response raises BackendError."""
    from content_reach.sources.web_search import JinaSearchBackend

    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.text = ""

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    backend = JinaSearchBackend(client=mock_client)
    request = ContentRequest(query="failing query")
    with pytest.raises(BackendError):
        await backend.fetch(request)


@pytest.mark.asyncio
async def test_jina_search_empty_text_raises():
    """200 response with empty text raises BackendError."""
    from content_reach.sources.web_search import JinaSearchBackend

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "   "

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    backend = JinaSearchBackend(client=mock_client)
    request = ContentRequest(query="empty text")
    with pytest.raises(BackendError):
        await backend.fetch(request)


@pytest.mark.asyncio
async def test_jina_search_sends_accept_header():
    """fetch() sends Accept: application/json header to the Jina search endpoint."""
    from content_reach.sources.web_search import JinaSearchBackend

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Result text from Jina"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    backend = JinaSearchBackend(client=mock_client)
    request = ContentRequest(query="accept header check")
    await backend.fetch(request)

    call_kwargs = mock_client.get.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert headers.get("Accept") == "application/json"


@pytest.mark.asyncio
async def test_jina_search_httpx_error_raises_backend_error():
    """fetch() wraps httpx.HTTPError into BackendError."""
    from content_reach.sources.web_search import JinaSearchBackend

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection failed"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    backend = JinaSearchBackend(client=mock_client)
    request = ContentRequest(query="http error query")
    with pytest.raises(BackendError):
        await backend.fetch(request)


# ---------------------------------------------------------------------------
# build_web_search_chain()
# ---------------------------------------------------------------------------


def test_build_web_search_chain_order():
    """Chain has ddgs → jina_search → browser_search in that order with WEB_SEARCH type."""
    from content_reach.sources.web_search import build_web_search_chain

    chain = build_web_search_chain()
    assert chain.backend_names() == ["ddgs", "jina_search", "browser_search"]
    assert chain.source_type is SourceType.WEB_SEARCH
    assert chain.source == "web_search"
