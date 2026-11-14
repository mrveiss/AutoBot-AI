# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
web_fetch.types — Public type definitions for the web_fetch package.

Issue #7400: Foundation package for unified web search/scrape/crawl.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RenderMode(str, Enum):
    """How to render the page when fetching.

    AUTO  — Try Jina fast-path, then BS4 raw HTML, then Playwright.
    FAST  — Jina fast-path + BS4 only; never invokes Playwright.
    PLAYWRIGHT — Skip fast-path, go straight to Playwright JS render.
    """

    AUTO = "auto"
    FAST = "fast"
    PLAYWRIGHT = "playwright"


# Error code constants — returned in FetchResult.error_code.
ERR_SSRF_BLOCKED = "ssrf_blocked"
ERR_ROBOTS_BLOCKED = "robots_blocked"
ERR_CIRCUIT_OPEN = "circuit_open"
ERR_HTTP_ERROR = "http_error"
ERR_TIMEOUT = "timeout"
ERR_CONNECTION = "connection"
ERR_TOO_LARGE = "too_large"
ERR_REDIRECT_LIMIT = "redirect_limit"
ERR_UNKNOWN = "unknown"
# #18826: the body is not HTML, text or JSON (binary, image, PDF); it is never extracted as a page.
ERR_UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"


@dataclass
class FetchResult:
    """Outcome of a single URL fetch.

    Attributes:
        url:        The URL that was fetched (after redirects).
        success:    True when usable markdown content was obtained.
        markdown:   Extracted markdown text (empty string on failure).
        title:      Page title, if parseable.
        render_mode: Which render mode actually produced the result.
        source:     Which backend produced the result (jina/bs4/playwright).
        error_code: One of the ERR_* constants (None on success).
        retryable:  True when a retry after a delay may succeed.
        status_code: HTTP status code from the final response (None if N/A).
    """

    url: str
    success: bool
    markdown: str = ""
    title: str = ""
    render_mode: RenderMode | None = None
    source: str = ""
    error_code: str | None = None
    retryable: bool = False
    status_code: int | None = None

    def cache_key(self, mode: RenderMode, profile: str) -> str:
        """Return this result's web_fetch cache key -- the one key builder, in web_fetch.cache (#18826)."""
        # Deferred: web_fetch.cache loads config and the extractor; this module stays dependency-free.
        from web_fetch.cache import _content_cache_key

        return _content_cache_key(self.url, mode.value, profile)
