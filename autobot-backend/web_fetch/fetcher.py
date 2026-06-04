# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from autobot_shared.logging_manager import get_logger
from web_fetch.cache import WEB_FETCH_MAX_BYTES, get_cached_result, set_cached_result
from web_fetch.extractors import _MIN_CONTENT_CHARS, extract_markdown, is_spa_content


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
_MAX_REDIRECTS = 5


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
        async with aiohttp.ClientSession() as session:
            async with session.get(jina_url, timeout=aio_timeout, allow_redirects=True) as resp:
                if resp.status == 200:
                    return await resp.text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.debug("Jina fetch failed for %s: %s", url, exc)
    return None


async def _fetch_bs4(url: str, timeout: float) -> tuple[str | None, int | None]:
    """Fetch raw HTML via aiohttp. Returns (html, status_code) or (None, None).

    Single round-trip (#7459): streams the response body in 64 KiB chunks,
    enforces ``WEB_FETCH_MAX_BYTES``, and returns ``("", status)`` for empty
    bodies — the prior implementation issued a 1-byte probe request and
    then re-fetched the full URL, doubling HTTP load on every fast-path
    attempt.

    SSRF guard is enforced inline (defense in depth) so any caller —
    including ``WebFetcher.fetch_raw_html`` which intentionally bypasses
    the public ``fetch()`` pipeline — cannot reach private IPs.
    """
    import aiohttp

    if not await _is_public_url(url):
        return None, None

    headers = {"User-Agent": _USER_AGENT}
    try:
        aio_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                url,
                timeout=aio_timeout,
                allow_redirects=True,
                max_redirects=_MAX_REDIRECTS,
            ) as resp:
                content = b""
                async for chunk in resp.content.iter_chunked(65536):
                    content += chunk
                    if len(content) > WEB_FETCH_MAX_BYTES:
                        return None, None  # too large
                if not content:
                    return "", resp.status
                html = content.decode("utf-8", errors="replace")
                return html, resp.status
    except aiohttp.TooManyRedirects:
        logger.debug("Too many redirects for %s", url)
        return None, None
    except Exception as exc:
        logger.debug("BS4 fetch failed for %s: %s", url, exc)
        return None, None


async def _fetch_playwright(url: str, timeout: float) -> str | None:
    """Fetch via Playwright bridge (services/playwright_service.py).

    SSRF guard enforced inline (defense in depth) — the Playwright service
    runs in a separate container with potential network reach to private IPs,
    so the URL must be validated even though the public ``WebFetcher.fetch``
    pipeline already checks.
    """
    if not await _is_public_url(url):
        return None
    try:
        from services.playwright_service import get_playwright_service

        svc = await get_playwright_service()
        result = await svc._post_and_parse(
            "render", {"url": url, "wait": "networkidle", "timeout": int(timeout * 1000)}
        )
        return result.get("html") or result.get("content")
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
            print(result.markdown)
    """

    def __init__(self, redis_client=None, robots_cache=None) -> None:
        self._redis = redis_client
        self._robots = robots_cache

    @classmethod
    async def fetch(
        cls,
        url: str,
        render: RenderMode = RenderMode.AUTO,
        timeout: float = 30.0,
        redis_client=None,
        robots_cache=None,
    ) -> FetchResult:
        """Fetch url and return FetchResult with markdown content.

        Args:
            url: Absolute URL to fetch.
            render: Render mode (AUTO/FAST/PLAYWRIGHT).
            timeout: Per-request timeout in seconds.
            redis_client: Optional async Redis client for caching.
            robots_cache: Optional RobotsCache instance.
        """
        instance = cls(redis_client=redis_client, robots_cache=robots_cache)
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
        return await _fetch_bs4(url, timeout)

    async def _fetch(self, url: str, render: RenderMode, timeout: float) -> FetchResult:
        """Internal fetch dispatcher."""
        # Cache lookup
        cached = await get_cached_result(url, render.value, self._redis)
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
            if result.error_code not in (ERR_SSRF_BLOCKED, ERR_ROBOTS_BLOCKED, ERR_CIRCUIT_OPEN):
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
            html, status = await _fetch_bs4(url, min(timeout, 15.0))
        if html is None and status is None:
            pass  # fall through to Playwright
        elif html is not None and status is not None and status < 400:
            title, md = extract_markdown(html)
            if not is_spa_content(md, html):
                return FetchResult(
                    url=url,
                    success=True,
                    markdown=md,
                    title=title,
                    render_mode=RenderMode.AUTO,
                    source="bs4",
                    status_code=status,
                )
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
            html, status = await _fetch_bs4(url, min(timeout, 15.0))
        if html is not None and status is not None and status < 400:
            title, md = extract_markdown(html)
            return FetchResult(
                url=url,
                success=True,
                markdown=md,
                title=title,
                render_mode=RenderMode.FAST,
                source="bs4",
                status_code=status,
            )
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
        title, md = extract_markdown(html)
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
        await set_cached_result(url, render.value, payload, self._redis)
