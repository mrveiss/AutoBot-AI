# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Web-page content source: TrafilaturaBackend → JinaReaderBackend → BrowserContentBackend (#10932).

Chain priority:
  1. TrafilaturaBackend — HTML fetch via httpx + text extraction via trafilatura (sync, in asyncio.to_thread)
  2. JinaReaderBackend  — GET <third-party reader base>/<url> (pure httpx; opt-in only, #21850)
  3. BrowserContentBackend     — Playwright-backed page fetch (browser required)
"""

from __future__ import annotations

import asyncio

import httpx

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.ssrf_guard import SSRFError
from autobot_shared.ssot_config import config
from content_reach._http import http_get
from content_reach._url_guard import ensure_public_url, ensure_robots_allowed
from content_reach.backends.browser import BrowserContentBackend
from content_reach.base import BackendError, ContentBackend, ContentReachResult, ContentRequest
from content_reach.chain import ContentSourceChain
from services import web_research_config
from source_attribution import SourceKind, SourceReliability

logger = get_logger(__name__)

# Third-party reader base URL (SSOT).
_JINA_READER_BASE = config.feature.third_party_reader_base_url


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
    source_type = SourceKind.WEB_PAGE

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

    async def fetch(self, request: ContentRequest) -> ContentReachResult:
        """GET request.url, extract text via trafilatura; raise BackendError on failure."""
        await ensure_public_url(request.url)
        await ensure_robots_allowed(request.url)

        try:
            _import_trafilatura()
        except ImportError:
            raise BackendError("trafilatura not installed")

        try:
            response = await http_get(request.url, client=self._client)
        except httpx.HTTPError as exc:
            raise BackendError(f"TrafilaturaBackend: HTTP error fetching {request.url!r}: {exc}") from exc
        except SSRFError as exc:
            raise BackendError(f"TrafilaturaBackend: blocked by SSRF guard at connect time: {exc}") from exc

        html = response.text
        text = await asyncio.to_thread(_trafilatura_extract, html)

        if not text or not text.strip():
            logger.debug(
                "TrafilaturaBackend: empty extraction for %r (status=%s)",
                request.url,
                response.status_code,
            )
            raise BackendError(f"TrafilaturaBackend: no text extracted from {request.url!r}")

        return ContentReachResult(
            success=True,
            source_type=self.source_type,
            backend_used=self.name,
            text=text,
            structured={},
            url=request.url,
            reliability=SourceReliability.MEDIUM,
        )


class JinaReaderBackend(ContentBackend):
    """Web-page backend via the third-party reader endpoint (SSOT base URL). Opt-in only (#21850).

    probe() returns True — pure-HTTP backend, always capable.
    fetch() GETs <reader base><url> with Accept: text/plain and returns
    the response body. Non-200 or empty body → BackendError.

    Accepts an optional injected httpx.AsyncClient for testing.
    """

    name = "jina_reader"
    source_type = SourceKind.WEB_PAGE

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def probe(self) -> bool:
        """True only when a user opted in to the third-party fast paths (#21850)."""
        return web_research_config.third_party_fast_paths_enabled()

    async def fetch(self, request: ContentRequest) -> ContentReachResult:
        """GET <reader base><url>; raise BackendError when not opted in, on non-200 or on empty body."""
        if not web_research_config.third_party_fast_paths_enabled():
            raise BackendError("JinaReaderBackend: third-party fast paths are off (opt-in setting)")
        await ensure_public_url(request.url)
        await ensure_robots_allowed(request.url)

        url = f"{_JINA_READER_BASE}{request.url}"
        headers = {"Accept": "text/plain"}

        try:
            response = await http_get(url, client=self._client, headers=headers)
        except httpx.HTTPError as exc:
            raise BackendError(f"JinaReaderBackend: HTTP error fetching {request.url!r}: {exc}") from exc
        except SSRFError as exc:
            raise BackendError(f"JinaReaderBackend: blocked by SSRF guard at connect time: {exc}") from exc

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

        return ContentReachResult(
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
        source_type=SourceKind.WEB_PAGE,
        backends=[
            TrafilaturaBackend(),
            JinaReaderBackend(),
            BrowserContentBackend(SourceKind.WEB_PAGE),
        ],
    )
