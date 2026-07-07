# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared browser-backed content backend using research_browser_manager (#10932).

BrowserBackend wraps get_research_browser_manager().research_url() and maps its
dict return to ContentResult.  Playwright availability is checked lazily (inside
each method) so importing this module never loads the playwright stack.

BrowserSearchBackend extends BrowserBackend for query→search: it builds a
DuckDuckGo HTML search URL from the request query, then delegates to the browser
for navigation and content extraction.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from autobot_shared.logging_manager import get_logger
from content_reach._url_guard import ensure_public_url, ensure_robots_allowed
from content_reach.base import BackendError, ContentBackend, ContentRequest, ContentResult
from source_attribution import SourceReliability, SourceType

logger = get_logger(__name__)

_DDG_SEARCH_URL = "https://duckduckgo.com/html/?q={}"


def _get_manager():  # pragma: no cover — replaced by monkeypatch in tests
    """Lazy accessor for the research browser manager (avoids import at module load)."""
    from research_browser_manager import get_research_browser_manager

    return get_research_browser_manager()


class BrowserBackend(ContentBackend):
    """Content backend that uses the Playwright-based research browser manager.

    probe() returns PLAYWRIGHT_AVAILABLE — imported lazily to avoid loading the
    playwright stack at module import time.
    """

    def __init__(
        self,
        source_type: SourceType,
        name: str = "browser",
    ) -> None:
        self.source_type = source_type
        self.name = name

    async def probe(self) -> bool:
        """Return True iff Playwright is available in this environment."""
        import research_browser_manager as rbm

        return rbm.PLAYWRIGHT_AVAILABLE

    async def fetch(self, request: ContentRequest) -> ContentResult:
        """Navigate to request.url and return extracted content.

        Raises BackendError if request.url is empty or the browser fetch fails.
        """
        if not request.url:
            raise BackendError("BrowserBackend requires a non-empty url on the request")

        await ensure_public_url(request.url)
        await ensure_robots_allowed(request.url)

        return await self._navigate(request)

    async def _navigate(self, request: ContentRequest) -> ContentResult:
        """Issue the browser navigation call and map result to ContentResult.

        Guards (SSRF/robots) are NOT re-checked here — callers must run them
        before calling _navigate (BrowserBackend.fetch does; BrowserSearchBackend
        runs SSRF-only before delegating here, skipping robots for search results).
        """
        manager = _get_manager()
        result = await manager.research_url(
            request.conversation_id,
            request.url,
            extract_content=True,
        )

        if not result.get("success"):
            raise BackendError(f"BrowserBackend: research_url returned success=False for {request.url!r}")

        content = result.get("content") or {}
        text = content.get("text_content", "")
        structured = content.get("structured_data") or {}

        return ContentResult(
            success=True,
            source_type=self.source_type,
            backend_used=self.name,
            text=text,
            structured=structured,
            url=request.url,
            reliability=SourceReliability.MEDIUM,
            metadata={"title": result.get("title", "")},
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
