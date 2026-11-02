# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
web_fetch.fetcher — Core WebFetcher with auto-detect render decision tree.

Issue #7400: Foundation package for unified web search/scrape/crawl.

Render decision tree (RenderMode.AUTO):
  1. Jina Reader fast-path (~200ms).  Success: HTTP 200 + >=500 chars + no SPA markers.
  2. BS4 raw HTML fetch (~300ms).    Same success criteria.
  3. Playwright fallback.             Always renders JS, waits for networkidle.

SSRF guards delegate to ``autobot_shared.url_safety.is_public_url_async``
(extracted in #7477 to break the ``pipeline.py`` ↔ ``fetcher.py`` cycle).
Jina circuit breaker from media.link.pipeline is reused via _try_jina / _record_*.

SSRF TOCTOU (#13019): ``_fetch_bs4`` connects directly to the caller-supplied
``url`` and previously did so via the shared pooled ``get_http_client()``
session after only a check-then-forget ``_is_public_url`` validation — DNS
could re-resolve to a private address between the check and the real
connect. It now routes through
``autobot_shared.security.ssrf_guard.pinned_request_with_redirects``, which
independently resolves + pins EVERY hop (including redirects) so validation
and connection can never diverge. ``_fetch_jina_impl`` and
``_fetch_playwright`` are NOT affected: the actual TCP connection they make
is always to a fixed, trusted proxy (``r.jina.ai`` — the caller's ``url`` is
only embedded in the *request path*, never the connect target) or to our own
in-cluster Playwright service, so pinning ``url`` there would be a no-op —
the ``_is_public_url`` check on those paths remains a defense-in-depth guard
against asking a third party to fetch on our behalf, not a TOCTOU fix.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from web_fetch.cache import WEB_FETCH_MAX_BYTES, get_cached_result, set_cached_result
from web_fetch.content_types import BodyKind, UnsupportedContentType, decode_body, page_from_body
from web_fetch.extractors import _MIN_CONTENT_CHARS, is_spa_content
from web_fetch.profile import IngestProfile, require_implemented


def _parse_jina_markdown(jina_text: str) -> tuple:
    """Extract (title, markdown) from Jina Reader response.

    Delegates to ``autobot_shared.jina_parser.parse_jina_output``. #7460
    extracted the parser from ``media.link.pipeline`` so it imports
    cleanly without the prior try/except fallback (which masked real
    import errors and silently returned ``("", jina_text)``).
    """
    from autobot_shared.jina_parser import parse_jina_output

    return parse_jina_output(jina_text)


from web_fetch.types import (
    ERR_CIRCUIT_OPEN,
    ERR_CONNECTION,
    ERR_HTTP_ERROR,
    ERR_ROBOTS_BLOCKED,
    ERR_SSRF_BLOCKED,
    ERR_TIMEOUT,
    ERR_UNKNOWN,
    ERR_UNSUPPORTED_CONTENT_TYPE,
    FetchResult,
    RenderMode,
)

logger = get_logger(__name__)

# Concurrency limits
_SEM_PER_DOMAIN: int = 4
_SEM_PLAYWRIGHT: int = 8
_SEM_FAST: int = 50

# Per-domain semaphores (lazy, keyed by netloc)
_domain_sems: dict[str, asyncio.Semaphore] = {}
_playwright_sem: asyncio.Semaphore | None = None
_fast_sem: asyncio.Semaphore | None = None

# Per-domain circuit breakers: {netloc: (failure_times_list, cooldown_until)}
_domain_circuit: dict[str, dict] = {}
_CIRCUIT_WINDOW = 60.0
_CIRCUIT_THRESHOLD = 3
_CIRCUIT_COOLDOWN = 60.0

_JINA_BASE_URL = "https://r.jina.ai/"
_USER_AGENT = "AutoBot/1.0 (web-fetch)"


def _resolve_max_redirects() -> int:
    """Return max redirect hops for the pinned BS4 fetch from env var (default 5)."""
    raw = config.misc.web_fetch_max_redirects
    return raw if raw else 5


_MAX_REDIRECTS: int = _resolve_max_redirects()


def _get_domain_sem(netloc: str) -> asyncio.Semaphore:
    if netloc not in _domain_sems:
        _domain_sems[netloc] = asyncio.Semaphore(_SEM_PER_DOMAIN)
    return _domain_sems[netloc]


def _get_playwright_sem() -> asyncio.Semaphore:
    global _playwright_sem
    if _playwright_sem is None:
        _playwright_sem = asyncio.Semaphore(_SEM_PLAYWRIGHT)
    return _playwright_sem


def _get_fast_sem() -> asyncio.Semaphore:
    global _fast_sem
    if _fast_sem is None:
        _fast_sem = asyncio.Semaphore(_SEM_FAST)
    return _fast_sem


def _circuit_is_open(netloc: str) -> bool:
    """Return True when the per-domain circuit breaker is open."""
    state = _domain_circuit.get(netloc)
    if state is None:
        return False
    return time.monotonic() < state.get("cooldown_until", 0.0)


def _record_domain_failure(netloc: str) -> None:
    """Record a failure; open circuit if threshold reached."""
    state = _domain_circuit.setdefault(netloc, {"failures": [], "cooldown_until": 0.0})
    now = time.monotonic()
    cutoff = now - _CIRCUIT_WINDOW
    state["failures"] = [t for t in state["failures"] if t > cutoff]
    state["failures"].append(now)
    if len(state["failures"]) >= _CIRCUIT_THRESHOLD:
        state["cooldown_until"] = now + _CIRCUIT_COOLDOWN
        logger.info("web_fetch circuit opened for %s (%.0fs cooldown)", netloc, _CIRCUIT_COOLDOWN)
        state["failures"].clear()


def _record_domain_success(netloc: str) -> None:
    """Clear failure window on success."""
    if netloc in _domain_circuit:
        _domain_circuit[netloc]["failures"].clear()


def _fail(url: str, code: str, retryable: bool = False, status: int | None = None) -> FetchResult:
    return FetchResult(url=url, success=False, error_code=code, retryable=retryable, status_code=status)


async def _fetch_jina(url: str, timeout: float) -> str | None:
    """Fetch markdown via Jina Reader fast-path. SSRF guard enforced inline."""
    if not await _is_public_url(url):
        return None
    return await _fetch_jina_impl(url, timeout)


async def _fetch_jina_impl(url: str, timeout: float) -> str | None:
    """Fetch via Jina Reader. Returns raw text or None on failure."""
    import aiohttp

    jina_url = f"{_JINA_BASE_URL}{url}"
    try:
        aio_timeout = aiohttp.ClientTimeout(total=timeout)
        async with get_http_client().tracked_request(
            "GET",
            jina_url,
            timeout=aio_timeout,
            allow_redirects=True,
            suppress_error_log=True,
        ) as resp:
            if resp.status == 200:
                return await resp.text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.debug("Jina fetch failed for %s: %s", url, exc)
    return None


async def _fetch_bs4(url: str, timeout: float) -> tuple[str | None, int | None, str | None]:
    """Fetch a raw body. Returns ``(body, status_code, content_type)`` or ``(None, None, None)``.

    ``content_type`` is the response's Content-Type header, ``None`` when absent, so
    the caller dispatches on what the server said the body is (#18826).
    The body is decoded in its declared charset (:func:`decode_body`), not always UTF-8.

    Single round-trip (#7459): streams the response body in 64 KiB chunks,
    enforces ``WEB_FETCH_MAX_BYTES``, and returns ``("", status, content_type)`` for empty
    bodies — the prior implementation issued a 1-byte probe request and
    then re-fetched the full URL, doubling HTTP load on every fast-path
    attempt.

    SSRF guard is enforced inline (defense in depth) so any caller —
    including ``WebFetcher.fetch_raw_html`` which intentionally bypasses
    the public ``fetch()`` pipeline — cannot reach private IPs. The actual
    connect goes through ``ssrf_guard.pinned_request_with_redirects`` (#13019)
    instead of the shared pooled client, so the resolved address validated is
    the address connected to on every hop, including redirects.
    """
    import aiohttp

    from autobot_shared.security.ssrf_guard import SSRFError, pinned_request_with_redirects

    if not await _is_public_url(url):
        return None, None, None

    headers = {"User-Agent": _USER_AGENT}
    aio_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with pinned_request_with_redirects(
            "GET", url, headers=headers, timeout=aio_timeout, max_redirects=_MAX_REDIRECTS
        ) as resp:
            content_type = resp.headers.get("Content-Type")
            content = b""
            async for chunk in resp.content.iter_chunked(65536):
                content += chunk
                if len(content) > WEB_FETCH_MAX_BYTES:
                    return None, None, None  # too large
            if not content:
                return "", resp.status, content_type
            return decode_body(content, content_type), resp.status, content_type
    except SSRFError as exc:
        logger.warning("web_fetch BS4 fetch blocked by SSRF guard for %s: %s", url, exc)
        return None, None, None
    except Exception as exc:
        logger.debug("BS4 fetch failed for %s: %s", url, exc)
        return None, None, None


async def _fetch_playwright(url: str, timeout: float) -> str | None:
    """Render *url* through the canonical browser interface (#13236, ADR-009).

    First caller migrated off a directly-named stack. The requirements express
    what this fallback has always actually needed:

    - ``EXTRACT_HTML`` — the result feeds a parser, so text will not do. Under
      the earlier single ``EXTRACT`` capability the worker (registered first)
      would have matched and returned ``get_text`` output, which is a valid
      result shape and would have failed silently.
    - ``OUT_OF_PROCESS`` — the whole point of this fallback is that Playwright
      does not run inside the backend's own process.

    Together those resolve to the container backend, which is exactly the
    stack this function called directly before, with the same ``render``
    endpoint and the caller's timeout preserved.

    The inline SSRF check is **kept** even though the interface now enforces
    the same DNS-resolving guard before dispatch. It is deliberate defence in
    depth: the Playwright container has network reach to private IPs, and this
    function is reachable from the render cascade, so the cost of one extra
    resolution is worth not depending on a single chokepoint.
    """
    if not await _is_public_url(url):
        return None
    try:
        import browser_backends
        from autobot_shared.browser import (
            BrowserCapability,
            ContentFormat,
            ExtractRequest,
            get_browser,
        )

        browser_backends.register_all()  # idempotent

        browser = await get_browser(
            requires={BrowserCapability.EXTRACT_HTML, BrowserCapability.OUT_OF_PROCESS},
        )
        result = await browser.extract(ExtractRequest(url=url, format=ContentFormat.HTML, timeout_seconds=timeout))
        return result.content if result.success else None
    except Exception as exc:
        logger.debug("Playwright fetch failed for %s: %s", url, exc)
        return None


async def _is_public_url(url: str) -> bool:
    """SSRF guard — delegates to ``autobot_shared.url_safety.is_public_url_async``.

    Direct import (no ``LinkPipeline.__new__`` hack, no try/except fallback)
    after #7477 extracted the guard out of ``media/link/pipeline.py`` into
    a neutral shared module that doesn't depend on ``web_fetch.fetcher``.
    """
    from autobot_shared.url_safety import is_public_url_async

    return await is_public_url_async(url)


class WebFetcher:
    """Unified web content fetcher with auto-detect render mode.

    All methods are async.  Concurrency is controlled by asyncio.Semaphore.
    Results are cached in Redis using content-hash dedup (SHA-256).

    Usage::

        result = await WebFetcher.fetch("https://example.com")
        if result.success:
            logger.info("fetched markdown: %s", result.markdown)
    """

    def __init__(self, redis_client=None, robots_cache=None, profile: IngestProfile = IngestProfile.DOCUMENT) -> None:
        self._redis = redis_client
        self._robots = robots_cache
        # #18826: validated here, before any cache lookup or network call, so an
        # unimplemented profile can never be answered from a document-profile cache.
        self.profile = require_implemented(profile)

    def page_text(self, body: str, url: str, content_type: str | None = None) -> tuple[str, str]:
        """Return ``(title, text)`` of a fetched *body*, dispatched on *content_type* (#18826).

        HTML goes through the one HTML extractor; text and JSON pass through; an
        undeclared type is sniffed. Raises :class:`UnsupportedContentType` for
        anything else, which is never extracted as a page.
        """
        _kind, title, text = page_from_body(body, content_type, self.profile, url)
        return title, text

    def _bs4_page(
        self, url: str, body: str, status: int, content_type: str | None, mode: RenderMode
    ) -> tuple[FetchResult, BodyKind | None]:
        """Build the result for a 2xx direct fetch; an unsupported body is a failed result."""
        try:
            kind, title, text = page_from_body(body, content_type, self.profile, url)
        except UnsupportedContentType as exc:
            logger.info("web_fetch refused %s: %s", url, exc)
            return _fail(url, ERR_UNSUPPORTED_CONTENT_TYPE, status=status), None
        result = FetchResult(
            url=url, success=True, markdown=text, title=title, render_mode=mode, source="bs4", status_code=status
        )
        return result, kind

    @classmethod
    async def fetch(
        cls,
        url: str,
        render: RenderMode = RenderMode.AUTO,
        timeout: float = 30.0,
        redis_client=None,
        robots_cache=None,
        profile: IngestProfile = IngestProfile.DOCUMENT,
    ) -> FetchResult:
        """Fetch url and return FetchResult with the page's extracted text.

        Args:
            url: Absolute URL to fetch.
            render: Render mode (AUTO/FAST/PLAYWRIGHT).
            timeout: Per-request timeout in seconds.
            redis_client: Optional async Redis client for caching.
            robots_cache: Optional RobotsCache instance.
            profile: What to keep from an HTML page (#18826); ``document`` is the only implemented value.
        """
        instance = cls(redis_client=redis_client, robots_cache=robots_cache, profile=profile)
        return await instance._fetch(url, render, timeout)

    @classmethod
    async def fetch_raw_html(cls, url: str, timeout: float = 30.0) -> tuple[str | None, int | None]:
        """Fetch raw HTML + status code via aiohttp (no markdown extraction).

        Public API for callers that need the HTML body itself — link
        extraction (Frontier in sitemap crawl), HTML format pass-through
        (``POST /knowledge/scrape format=html``), or content-type detection
        before deciding render mode. Closes the #7476 gap where 3 production
        modules reached into the private ``_fetch_bs4`` to get raw HTML.

        Bypasses cache, robots, semaphores, and the AUTO render cascade —
        this is a low-level "give me the bytes" primitive. Callers that need
        the full FetchResult pipeline should use ``fetch()``.

        SSRF guard IS still enforced (inline in ``_fetch_bs4`` since the
        critical alert from CodeQL on PR #7514) so callers cannot reach
        private IPs even though the public pipeline is bypassed.

        Args:
            url: Absolute URL to fetch.
            timeout: Per-request timeout in seconds.

        Returns:
            ``(html, status_code)`` on success. ``(None, None)`` on any error
            (connection, redirect-limit, non-utf8 body, etc.). ``("", status)``
            on empty body with a successful status — same shape as ``fetch()``
            for empty content.
        """
        html, status, _content_type = await cls.fetch_raw_page(url, timeout)
        return html, status

    @classmethod
    async def fetch_raw_page(cls, url: str, timeout: float = 30.0) -> tuple[str | None, int | None, str | None]:
        """Like :meth:`fetch_raw_html`, plus the response Content-Type (``None`` when absent).

        Callers that turn the body into stored text pass the header on to
        :meth:`page_text`, so the page type is declared, not sniffed (#18826).
        """
        return await _fetch_bs4(url, timeout)

    async def _fetch(self, url: str, render: RenderMode, timeout: float) -> FetchResult:
        """Internal fetch dispatcher."""
        # Cache lookup
        cached = await get_cached_result(url, render.value, self.profile.value, self._redis)
        if cached is not None:
            logger.debug("web_fetch cache hit for %s", url)
            return FetchResult(**cached)

        netloc = urlparse(url).netloc

        # SSRF guard
        if not await _is_public_url(url):
            return _fail(url, ERR_SSRF_BLOCKED)

        # Circuit breaker
        if _circuit_is_open(netloc):
            return _fail(url, ERR_CIRCUIT_OPEN, retryable=True)

        # Robots check
        if self._robots is not None:
            if not await self._robots.is_allowed(url):
                return _fail(url, ERR_ROBOTS_BLOCKED)

        result = await self._dispatch(url, render, timeout, netloc)

        if result.success:
            _record_domain_success(netloc)
            await self._cache(url, render, result)
        else:
            # A refused body type says nothing about the host's health, so it never trips the circuit.
            _not_host_failures = (ERR_SSRF_BLOCKED, ERR_ROBOTS_BLOCKED, ERR_CIRCUIT_OPEN, ERR_UNSUPPORTED_CONTENT_TYPE)
            if result.error_code not in _not_host_failures:
                _record_domain_failure(netloc)

        return result

    async def _dispatch(self, url: str, render: RenderMode, timeout: float, netloc: str) -> FetchResult:
        """Route to correct render strategy."""
        dom_sem = _get_domain_sem(netloc)
        async with dom_sem:
            if render == RenderMode.PLAYWRIGHT:
                return await self._run_playwright(url, timeout)
            if render == RenderMode.FAST:
                return await self._run_fast(url, timeout)
            return await self._run_auto(url, timeout)

    async def _run_auto(self, url: str, timeout: float) -> FetchResult:
        """AUTO mode: Jina -> BS4 -> Playwright."""
        # Step 1: Jina — success requires >=500 chars and no SPA markers.
        async with _get_fast_sem():
            jina_text = await _fetch_jina(url, min(timeout, 10.0))
        if jina_text:
            title, md = _parse_jina_markdown(jina_text)
            if len(md.strip()) >= _MIN_CONTENT_CHARS and not is_spa_content(md):
                return FetchResult(
                    url=url, success=True, markdown=md, title=title, render_mode=RenderMode.AUTO, source="jina"
                )

        # Step 2: BS4 — success requires HTTP 2xx and no SPA markers (any length).
        async with _get_fast_sem():
            body, status, content_type = await _fetch_bs4(url, min(timeout, 15.0))
        if body is None and status is None:
            pass  # fall through to Playwright
        elif body is not None and status is not None and status < 400:
            result, kind = self._bs4_page(url, body, status, content_type, RenderMode.AUTO)
            # Only an HTML shell can need JS rendering; text, JSON and refusals are final.
            if kind is not BodyKind.HTML or not is_spa_content(result.markdown, body):
                return result
        elif status is not None and status >= 400:
            return _fail(url, ERR_HTTP_ERROR, status=status)

        # Step 3: Playwright
        return await self._run_playwright(url, timeout)

    async def _run_fast(self, url: str, timeout: float) -> FetchResult:
        """FAST mode: Jina -> BS4, no Playwright."""
        async with _get_fast_sem():
            jina_text = await _fetch_jina(url, min(timeout, 10.0))
        if jina_text:
            title, md = _parse_jina_markdown(jina_text)
            if len(md.strip()) >= _MIN_CONTENT_CHARS and not is_spa_content(md):
                return FetchResult(
                    url=url, success=True, markdown=md, title=title, render_mode=RenderMode.FAST, source="jina"
                )

        async with _get_fast_sem():
            body, status, content_type = await _fetch_bs4(url, min(timeout, 15.0))
        if body is not None and status is not None and status < 400:
            return self._bs4_page(url, body, status, content_type, RenderMode.FAST)[0]
        if status is not None and status >= 400:
            return _fail(url, ERR_HTTP_ERROR, retryable=False, status=status)
        return _fail(url, ERR_CONNECTION, retryable=True)

    async def _run_playwright(self, url: str, timeout: float) -> FetchResult:
        """PLAYWRIGHT mode: fetch via Playwright bridge."""
        async with _get_playwright_sem():
            try:
                html = await _fetch_playwright(url, timeout)
            except asyncio.TimeoutError:
                return _fail(url, ERR_TIMEOUT, retryable=True)
        if html is None:
            return _fail(url, ERR_UNKNOWN, retryable=True)
        # The browser returns its rendered DOM, so the body is HTML whatever the URL served.
        title, md = self.page_text(html, url, "text/html")
        return FetchResult(
            url=url, success=True, markdown=md, title=title, render_mode=RenderMode.PLAYWRIGHT, source="playwright"
        )

    async def _cache(self, url: str, render: RenderMode, result: FetchResult) -> None:
        """Persist successful result to Redis cache."""
        payload = {
            "url": result.url,
            "success": result.success,
            "markdown": result.markdown,
            "title": result.title,
            "render_mode": result.render_mode.value if result.render_mode else None,
            "source": result.source,
            "error_code": result.error_code,
            "retryable": result.retryable,
            "status_code": result.status_code,
        }
        await set_cached_result(url, render.value, self.profile.value, payload, self._redis)
