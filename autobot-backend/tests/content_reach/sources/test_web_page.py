# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for content_reach.sources.web_page (TrafilaturaBackend, JinaReaderBackend, build_web_page_chain)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from content_reach.base import BackendError, ContentRequest
from source_attribution import SourceType

# ---------------------------------------------------------------------------
# TrafilaturaBackend — probe()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trafilatura_probe_true_when_importable():
    """probe() returns True when trafilatura is importable (installed here)."""
    pytest.importorskip("trafilatura")
    from content_reach.sources.web_page import TrafilaturaBackend

    backend = TrafilaturaBackend()
    result = await backend.probe()
    assert result is True


@pytest.mark.asyncio
async def test_trafilatura_probe_false_when_absent(monkeypatch):
    """probe() returns False when the lazy import helper raises ImportError."""
    from content_reach.sources import web_page as wp_mod

    monkeypatch.setattr(
        wp_mod,
        "_import_trafilatura",
        lambda: (_ for _ in ()).throw(ImportError("no trafilatura")),
    )

    from content_reach.sources.web_page import TrafilaturaBackend

    backend = TrafilaturaBackend()
    result = await backend.probe()
    assert result is False


# ---------------------------------------------------------------------------
# TrafilaturaBackend — fetch()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trafilatura_fetch_maps_extracted_text(monkeypatch):
    """fetch() maps trafilatura-extracted text into a successful ContentResult."""
    from content_reach.sources import web_page as wp_mod

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>raw html</body></html>"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(wp_mod, "_trafilatura_extract", lambda html: "Extracted article text")

    from content_reach.sources.web_page import TrafilaturaBackend

    backend = TrafilaturaBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/article")
    result = await backend.fetch(request)

    assert result.success is True
    assert result.backend_used == "trafilatura"
    assert result.source_type is SourceType.WEB_PAGE
    assert result.text == "Extracted article text"
    assert result.url == "https://example.com/article"


@pytest.mark.asyncio
async def test_trafilatura_fetch_none_extraction_raises(monkeypatch):
    """None returned by trafilatura.extract → BackendError."""
    from content_reach.sources import web_page as wp_mod

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html></html>"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(wp_mod, "_trafilatura_extract", lambda html: None)

    from content_reach.sources.web_page import TrafilaturaBackend

    backend = TrafilaturaBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/empty")
    with pytest.raises(BackendError):
        await backend.fetch(request)


@pytest.mark.asyncio
async def test_trafilatura_fetch_empty_extraction_raises(monkeypatch):
    """Empty string returned by trafilatura.extract → BackendError."""
    from content_reach.sources import web_page as wp_mod

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html></html>"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(wp_mod, "_trafilatura_extract", lambda html: "   ")

    from content_reach.sources.web_page import TrafilaturaBackend

    backend = TrafilaturaBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/whitespace")
    with pytest.raises(BackendError):
        await backend.fetch(request)


@pytest.mark.asyncio
async def test_trafilatura_fetch_absent_lib_raises_backend_error(monkeypatch):
    """If trafilatura is absent, fetch() raises BackendError (not ImportError)."""
    from content_reach.sources import web_page as wp_mod

    monkeypatch.setattr(
        wp_mod,
        "_import_trafilatura",
        lambda: (_ for _ in ()).throw(ImportError("no trafilatura")),
    )

    from content_reach.sources.web_page import TrafilaturaBackend

    backend = TrafilaturaBackend()
    request = ContentRequest(url="https://example.com/article")
    with pytest.raises(BackendError, match="trafilatura not installed"):
        await backend.fetch(request)


@pytest.mark.asyncio
async def test_trafilatura_fetch_httpx_error_raises_backend_error(monkeypatch):
    """httpx.HTTPError raised by client.get() → BackendError (not raw httpx error)."""
    from content_reach.sources import web_page as wp_mod

    monkeypatch.setattr(wp_mod, "_trafilatura_extract", lambda html: "text")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    from content_reach.sources.web_page import TrafilaturaBackend

    backend = TrafilaturaBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/article")
    with pytest.raises(BackendError):
        await backend.fetch(request)


# ---------------------------------------------------------------------------
# JinaReaderBackend — fetch()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jina_reader_fetch_maps_text():
    """fetch() maps a 200 response body to a successful ContentResult."""
    from content_reach.sources.web_page import JinaReaderBackend

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Article text from Jina"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    backend = JinaReaderBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/page")
    result = await backend.fetch(request)

    assert result.success is True
    assert result.backend_used == "jina_reader"
    assert result.source_type is SourceType.WEB_PAGE
    assert result.text == "Article text from Jina"


@pytest.mark.asyncio
async def test_jina_reader_fetch_sends_accept_header():
    """fetch() sends Accept: text/plain header to the Jina reader endpoint."""
    from content_reach.sources.web_page import JinaReaderBackend

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Content here"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    backend = JinaReaderBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/page")
    await backend.fetch(request)

    call_kwargs = mock_client.get.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert headers.get("Accept") == "text/plain"


@pytest.mark.asyncio
async def test_jina_reader_non_200_raises():
    """Non-200 response raises BackendError."""
    from content_reach.sources.web_page import JinaReaderBackend

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = ""

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    backend = JinaReaderBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/page")
    with pytest.raises(BackendError):
        await backend.fetch(request)


@pytest.mark.asyncio
async def test_jina_reader_empty_text_raises():
    """200 response with empty text raises BackendError."""
    from content_reach.sources.web_page import JinaReaderBackend

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "   "

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    backend = JinaReaderBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/page")
    with pytest.raises(BackendError):
        await backend.fetch(request)


@pytest.mark.asyncio
async def test_jina_reader_httpx_error_raises_backend_error():
    """httpx.HTTPError raised by client.get() → BackendError (not raw httpx error)."""
    from content_reach.sources.web_page import JinaReaderBackend

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    backend = JinaReaderBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/page")
    with pytest.raises(BackendError):
        await backend.fetch(request)


# ---------------------------------------------------------------------------
# build_web_page_chain()
# ---------------------------------------------------------------------------


def test_build_web_page_chain_order():
    """Chain has trafilatura → jina_reader → browser in that order with WEB_PAGE type."""
    from content_reach.sources.web_page import build_web_page_chain

    chain = build_web_page_chain()
    assert chain.backend_names() == ["trafilatura", "jina_reader", "browser"]
    assert chain.source_type is SourceType.WEB_PAGE
    assert chain.source == "web_page"
