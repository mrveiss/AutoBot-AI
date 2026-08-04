# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared browser-backed content backend (#10932, #13236).

BrowserBackend asks the canonical browser interface for a browser that can
navigate *and* extract structured content, and maps the ``BrowserResult`` onto
``ContentResult``. It no longer names a stack: ``EXTRACT_STRUCTURED`` is what
selects the research browser, because that is the only stack producing the
``structured`` half of a ``ContentResult`` (ADR-009 step 3).

Everything stays lazy — the interface, the backends and Playwright itself are
imported inside the methods that need them, so importing this module never
loads the browser stack.

BrowserSearchBackend extends BrowserBackend for query→search: it builds a
DuckDuckGo HTML search URL from the request query, then delegates to the browser
for navigation and content extraction.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from autobot_shared.browser import (
    Capability,
    NavigateRequest,
    get_browser,
)
from autobot_shared.logging_manager import get_logger
from content_reach._url_guard import ensure_public_url, ensure_robots_allowed
from content_reach.base import BackendError, ContentBackend, ContentRequest, ContentResult
from source_attribution import SourceReliability, SourceType

logger = get_logger(__name__)

_DDG_SEARCH_URL = "https://duckduckgo.com/html/?q={}"


class BrowserBackend(ContentBackend):
    """Content backend that uses the Playwright-based research browser manager.

    probe() returns PLAYWRIGHT_AVAILABLE — imported lazily to avoid loading the
    playwright stack at module import time.
    """

    #: What this backend needs from a browser. EXTRACT_STRUCTURED because the
    #: ContentResult carries `structured` alongside `text`, and only the
    #: research stack produces it — so this both states the requirement and
    #: pins the routing (#13236).
    _REQUIRES = frozenset({Capability.NAVIGATE, Capability.EXTRACT_STRUCTURED})

    def __init__(
        self,
        source_type: SourceType,
        name: str = "browser",
    ) -> None:
        self.source_type = source_type
        self.name = name

    async def probe(self) -> bool:
        """True when a browser able to serve this backend is reachable.

        Previously this read ``research_browser_manager.PLAYWRIGHT_AVAILABLE``
        directly — a module-level flag on one stack. It now asks the same
        question the fetch will ask, so probe and fetch cannot disagree
        (#13236).
        """
        import browser_backends
        from autobot_shared.browser import NoCapableBackendError, resolve_backend

        browser_backends.register_all()
        try:
            await resolve_backend(self._REQUIRES)
            return True
        except NoCapableBackendError:
            return False

    async def fetch(self, request: ContentRequest) -> ContentResult:
        """Navigate to request.url and return extracted content.

        Raises BackendError if request.url is empty or the browser fetch fails.
        """
        if not request.url:
            raise BackendError("BrowserBackend requires a non-empty url on the request")

        await ensure_public_url(request.url)
        await ensure_robots_allowed(request.url)

        return await self._navigate(request)

    @staticmethod
    def _raise_for_failed_result(result, url: str) -> None:
        """Raise BackendError for a failed navigation, distinguishing an
        SSRF-guard rejection (#13018 -- research_browser_manager re-checks the
        guard immediately before Playwright resolves the host, and tags the
        result ``blocked_by_guard``) from any other failure, instead of one
        generic message for both.

        #13236: reads the canonical ``BrowserResult`` rather than
        ``research_url``'s dict. The guard flag survives the move because the
        in-process backend carries it through in ``details``.
        """
        if result.details.get("blocked_by_guard"):
            raise BackendError(f"BrowserBackend: blocked by SSRF guard at navigate time for {url!r}")
        error = result.error or "unknown error"
        raise BackendError(f"BrowserBackend: navigation failed for {url!r}: {error}")

    async def _navigate(self, request: ContentRequest) -> ContentResult:
        """Issue the browser navigation call and map result to ContentResult.

        Guards (SSRF/robots) are NOT re-checked here — callers must run them
        before calling _navigate (BrowserBackend.fetch does; BrowserSearchBackend
        runs SSRF-only before delegating here, skipping robots for search results).
        research_url's navigate_to re-validates the SSRF guard immediately
        before Playwright's own DNS resolution as a compensating control
        (#13018 -- narrows, does not close, that TOCTOU window).
        """
        import browser_backends

        browser_backends.register_all()  # idempotent

        browser = await get_browser(requires=self._REQUIRES, session_id=request.conversation_id)
        result = await browser.navigate(
            NavigateRequest(
                url=request.url,
                session_id=request.conversation_id,
                # research_url does navigation and extraction in one round
                # trip; asking here avoids navigating twice.
                extract=True,
            )
        )

        if not result.success:
            self._raise_for_failed_result(result, request.url)

        return ContentResult(
            success=True,
            source_type=self.source_type,
            backend_used=self.name,
            text=result.content or "",
            structured=result.structured,
            url=request.url,
            reliability=SourceReliability.MEDIUM,
            # The old code read a top-level "title" that research_url never
            # returned, so this was always "". The canonical result carries
            # the real page title (#13236).
            metadata={"title": result.title or ""},
        )


class BrowserSearchBackend(BrowserBackend):
    """Browser backend for query-to-search: builds a DDG HTML search URL then delegates.

    Encodes request.query into a DuckDuckGo HTML search URL and passes it to the
    parent BrowserBackend._navigate() so the browser navigates to the results page and
    extracts content. robots.txt is intentionally skipped for search-results pages.
    """

    def __init__(self, source_type: SourceType) -> None:
        super().__init__(source_type=source_type, name="browser_search")

    async def fetch(self, request: ContentRequest) -> ContentResult:
        """Build a DDG search URL from request.query and fetch via browser."""
        search_url = _DDG_SEARCH_URL.format(quote_plus(request.query))
        await ensure_public_url(search_url)
        search_request = ContentRequest(
            query=request.query,
            url=search_url,
            source=request.source,
            limit=request.limit,
            conversation_id=request.conversation_id,
            options=request.options,
        )
        return await self._navigate(search_request)
