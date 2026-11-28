# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Web-search content source: DdgsBackend → JinaSearchBackend → BrowserSearchBackend (#10932).

Chain priority:
  1. DdgsBackend   — keyless web search via the ddgs library (sync, wrapped in asyncio.to_thread)
  2. JinaSearchBackend — GET <third-party search base><query> (pure httpx; opt-in only, #21850)
  3. BrowserSearchBackend — Playwright-backed DuckDuckGo search (browser required)
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote_plus

import httpx

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from content_reach._http import assert_server_chosen_egress, http_get
from content_reach.backends.browser import BrowserSearchBackend
from content_reach.base import BackendError, ContentBackend, ContentReachResult, ContentRequest
from content_reach.chain import ContentSourceChain
from services import web_research_config
from source_attribution import SourceKind, SourceReliability

logger = get_logger(__name__)

# Module-level name so tests can monkeypatch: content_reach.sources.web_search.DDGS
DDGS = None  # populated lazily by _import_ddgs()

_JINA_SEARCH_BASE = config.feature.third_party_search_base_url


def _import_ddgs():
    """Lazy import of DDGS class; raises ImportError if ddgs is not installed."""
    from ddgs import DDGS as _DDGS

    return _DDGS


class DdgsBackend(ContentBackend):
    """Web-search backend using the ddgs library (keyless DuckDuckGo search).

    probe() returns True iff ddgs is importable.
    fetch() runs DDGS().text() in asyncio.to_thread (ddgs is sync).
    Empty results → BackendError so the chain falls through to JinaSearchBackend.
    """

    name = "ddgs"
    source_type = SourceKind.WEB_SEARCH

    async def probe(self) -> bool:
        """Return True iff ddgs is importable."""
        try:
            _import_ddgs()
            return True
        except ImportError:
            logger.warning("ddgs not installed; DdgsBackend unavailable")
            return False

    async def fetch(self, request: ContentRequest) -> ContentReachResult:
        """Fetch web-search results via DDGS.text(); raise BackendError when empty."""
        if DDGS is not None:
            ddgs_cls = DDGS
        else:
            try:
                ddgs_cls = _import_ddgs()
            except ImportError:
                raise BackendError("ddgs not installed")

        def _search():
            return ddgs_cls().text(request.query, max_results=request.limit)

        raw_results: list[dict] = await asyncio.to_thread(_search)

        if not raw_results:
            logger.debug("DdgsBackend: no results for %r", request.query)
            raise BackendError(f"DdgsBackend: no results for query {request.query!r}")

        text_lines = [f"{r.get('title', '')} — {r.get('href', '')}\n{r.get('body', '')}" for r in raw_results]
        text = "\n\n".join(text_lines)

        return ContentReachResult(
            success=True,
            source_type=self.source_type,
            backend_used=self.name,
            text=text,
            structured={"results": raw_results},
            reliability=SourceReliability.MEDIUM,
        )


class JinaSearchBackend(ContentBackend):
    """Web-search backend via the third-party search endpoint (SSOT base URL). Opt-in only (#21850).

    probe() returns True — pure-HTTP backend, always capable.
    fetch() GETs <search base><urlencoded query> and returns the response text.
    Non-200 or empty body → BackendError.

    Accepts an optional injected httpx.AsyncClient for testing.
    """

    name = "jina_search"
    source_type = SourceKind.WEB_SEARCH

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def probe(self) -> bool:
        """True only when a user opted in to the third-party fast paths (#21850)."""
        return web_research_config.third_party_fast_paths_enabled()

    async def fetch(self, request: ContentRequest) -> ContentReachResult:
        """GET <search base><query>; raise BackendError when not opted in, on non-200 or on empty body."""
        if not web_research_config.third_party_fast_paths_enabled():
            raise BackendError("JinaSearchBackend: third-party fast paths are off (opt-in setting)")
        encoded_query = quote_plus(request.query)
        url = f"{_JINA_SEARCH_BASE}{encoded_query}"
        headers = {"Accept": "application/json"}
        await assert_server_chosen_egress(url, client=self._client)

        try:
            response = await http_get(url, client=self._client, headers=headers)
        except httpx.HTTPError as exc:
            raise BackendError(f"JinaSearchBackend: HTTP error for query {request.query!r}: {exc}") from exc

        if response.status_code != 200:
            raise BackendError(f"JinaSearchBackend: HTTP {response.status_code} for query {request.query!r}")

        text = response.text.strip()
        if not text:
            raise BackendError(f"JinaSearchBackend: empty response for query {request.query!r}")

        return ContentReachResult(
            success=True,
            source_type=self.source_type,
            backend_used=self.name,
            text=text,
            structured={},
            url=url,
            reliability=SourceReliability.MEDIUM,
        )


def build_web_search_chain() -> ContentSourceChain:
    """Build the web-search fallback chain: ddgs → jina_search → browser_search."""
    return ContentSourceChain(
        source="web_search",
        source_type=SourceKind.WEB_SEARCH,
        backends=[
            DdgsBackend(),
            JinaSearchBackend(),
            BrowserSearchBackend(SourceKind.WEB_SEARCH),
        ],
    )
