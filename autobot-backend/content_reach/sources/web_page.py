# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Web-page content source: TrafilaturaBackend → JinaReaderBackend → BrowserBackend (#10932).

Chain priority:
  1. TrafilaturaBackend — HTML fetch via httpx + text extraction via trafilatura (sync, in asyncio.to_thread)
  2. JinaReaderBackend  — GET https://r.jina.ai/<url> (pure httpx, always available)
  3. BrowserBackend     — Playwright-backed page fetch (browser required)
"""

from __future__ import annotations

import asyncio

import httpx

from autobot_shared.logging_manager import get_logger
from content_reach.backends.browser import BrowserBackend
from content_reach.base import BackendError, ContentBackend, ContentRequest, ContentResult
from content_reach.chain import ContentSourceChain
from source_attribution import SourceReliability, SourceType

logger = get_logger(__name__)

# Module-level HTTP timeout constant (seconds).
_HTTP_TIMEOUT = 15.0

# Jina Reader base URL.
_JINA_READER_BASE = "https://r.jina.ai/"


def _import_trafilatura():
    """Lazy import of trafilatura; raises ImportError if not installed."""
    import trafilatura as _trafilatura

    return _trafilatura


# Module-level monkeypatchable sync extractor (wraps trafilatura.extract).
# Tests can patch this to bypass the real library without asyncio.to_thread.
def _trafilatura_extract(html: str):
    """Call trafilatura.extract on html; returns str|None."""
    tf = _import_trafilatura()
    return tf.extract(html)


class TrafilaturaBackend(ContentBackend):
    """Web-page backend using httpx to fetch HTML + trafilatura to extract text.

    probe() returns True iff trafilatura is importable.
    fetch() GETs the URL via httpx.AsyncClient, then calls trafilatura.extract
    in asyncio.to_thread (trafilatura is sync). None/empty extraction → BackendError.

    Accepts an optional injected httpx.AsyncClient for testing.
    """

    name = "trafilatura"
    source_type = SourceType.WEB_PAGE

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def probe(self) -> bool:
        """Return True iff trafilatura is importable."""
        try:
            _import_trafilatura()
            return True
        except ImportError:
            logger.warning("TrafilaturaBackend: trafilatura is not installed; backend unavailable")
            return False

    async def fetch(self, request: ContentRequest) -> ContentResult:
        """GET request.url, extract text via trafilatura; raise BackendError on failure."""
        try:
            _import_trafilatura()
        except ImportError:
            raise BackendError("trafilatura not installed")

        if self._client is not None:
            response = await self._client.get(request.url)
        else:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.get(request.url)

        html = response.text
        text = await asyncio.to_thread(_trafilatura_extract, html)

        if not text or not text.strip():
            logger.debug(
                "TrafilaturaBackend: empty extraction for %r (status=%s)",
                request.url,
                response.status_code,
            )
            raise BackendError(f"TrafilaturaBackend: no text extracted from {request.url!r}")

        return ContentResult(
            success=True,
            source_type=self.source_type,
            backend_used=self.name,
            text=text,
            structured={},
            url=request.url,
            reliability=SourceReliability.MEDIUM,
        )


class JinaReaderBackend(ContentBackend):
    """Web-page backend via the Jina AI reader endpoint (https://r.jina.ai/).

    probe() returns True — pure-HTTP backend, always capable.
    fetch() GETs https://r.jina.ai/<url> with Accept: text/plain and returns
    the response body. Non-200 or empty body → BackendError.

    Accepts an optional injected httpx.AsyncClient for testing.
    """

    name = "jina_reader"
    source_type = SourceType.WEB_PAGE

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def probe(self) -> bool:
        """Return True — Jina reader is a plain HTTP endpoint, always available."""
        return True

    async def fetch(self, request: ContentRequest) -> ContentResult:
        """GET https://r.jina.ai/<url>; raise BackendError on non-200 or empty body."""
        url = f"{_JINA_READER_BASE}{request.url}"
        headers = {"Accept": "text/plain"}

        if self._client is not None:
            response = await self._client.get(url, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.get(url, headers=headers)

        if response.status_code != 200:
            logger.debug(
                "JinaReaderBackend: HTTP %s for %r",
                response.status_code,
                request.url,
            )
            raise BackendError(f"JinaReaderBackend: HTTP {response.status_code} for {request.url!r}")

        text = response.text.strip()
        if not text:
            logger.debug("JinaReaderBackend: empty response for %r", request.url)
            raise BackendError(f"JinaReaderBackend: empty response for {request.url!r}")

        return ContentResult(
            success=True,
            source_type=self.source_type,
            backend_used=self.name,
            text=text,
            structured={},
            url=request.url,
            reliability=SourceReliability.MEDIUM,
        )


def build_web_page_chain() -> ContentSourceChain:
    """Build the web-page fallback chain: trafilatura → jina_reader → browser."""
    return ContentSourceChain(
        source="web_page",
        source_type=SourceType.WEB_PAGE,
        backends=[
            TrafilaturaBackend(),
            JinaReaderBackend(),
            BrowserBackend(SourceType.WEB_PAGE),
        ],
    )
