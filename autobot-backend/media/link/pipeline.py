# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Link Processing Pipeline
# Issue #735: Organize media processing into dedicated pipelines
# Issue #932: Implement actual link/web processing
# Issue #7401: Scrape-consolidation — internals delegate to web_fetch.WebFetcher.

"""Link processing pipeline for web content and URLs.

The :class:`LinkPipeline` class is the canonical media-pipeline owner for
``MediaType.LINK`` inputs.  Its public interface (``process(MediaInput)``) is
unchanged and is used by the :class:`media.manager.MediaPipelineManager`.

A lightweight convenience entry-point ``process_url(url)`` is exposed for
callers that only have a raw URL string and do not need a full
``MediaInput``/``ProcessingResult`` round-trip.  Internally both paths now
delegate all fetching to :class:`web_fetch.WebFetcher` so there is a single
implementation of Jina/BS4/Playwright logic.

This module retains ownership of:

* SSRF guards (``_is_public_url``/``_is_public_url_async``) — reused by
  ``web_fetch.fetcher`` via a reverse import.
* Jina Reader circuit-breaker helpers (``_record_jina_failure`` etc.) — also
  reused by ``web_fetch.fetcher``.
* ``_parse_jina_output`` — shared parsing helper.

None of these helpers are removed; they are kept here to preserve all call
sites intact (see issue #7401 caller audit).
"""

import asyncio
import ipaddress
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import urljoin

from autobot_shared.logging_manager import get_logger
from knowledge.query_sanitizer import sanitize_document as _sanitize_document
from media.core.pipeline import BasePipeline
from media.core.types import MediaInput, MediaType, ProcessingResult

# aiohttp for async HTTP
try:
    import aiohttp

    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

# BeautifulSoup for HTML parsing
try:
    from bs4 import BeautifulSoup

    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False

logger = get_logger(__name__)

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15) if _AIOHTTP_AVAILABLE else None
_JINA_TIMEOUT = aiohttp.ClientTimeout(total=5) if _AIOHTTP_AVAILABLE else None
_MAX_CONTENT_LENGTH = 1_000_000  # 1 MB cap on HTML download
_USER_AGENT = "AutoBot/1.0 (media-pipeline)"
_JINA_BASE_URL = "https://r.jina.ai/"

# SSRF guard constants moved with the implementation to
# ``autobot_shared.url_safety`` (#7477): _PRIVATE_TLDS, _IPV6_ULA,
# _DNS_TIMEOUT_SECONDS.

# Jina Reader circuit breaker: open after N failures in a rolling window,
# stay open for _JINA_COOLDOWN_SECONDS, then retry. Prevents paying the
# full timeout cost on every URL during a Jina outage.
_JINA_COOLDOWN_SECONDS = 60.0
_JINA_FAILURE_THRESHOLD = 3
_JINA_FAILURE_WINDOW_SECONDS = 60.0
_jina_cooldown_until: float = 0.0
_jina_failures_in_window: List[float] = []

# Pooled aiohttp session for Jina Reader (reused across calls for connection
# pooling). Lazy-created under _jina_session_lock to serialize the first-
# creation race. Close via close_jina_session() during app shutdown.
_jina_session: "aiohttp.ClientSession" | None = None
_jina_session_lock: asyncio.Lock | None = None


class LinkPipeline(BasePipeline):
    """Pipeline for processing web links and URLs."""

    PIPELINE_NAME = "link"
    SUPPORTED_TYPES = [MediaType.LINK]

    async def _process_impl(self, media_input: MediaInput) -> ProcessingResult:
        """Process link content."""
        result_data = await self._process_link(media_input)
        confidence = self._calculate_confidence(result_data)

        return ProcessingResult(
            result_id=f"link_{media_input.media_id}",
            media_id=media_input.media_id,
            media_type=media_input.media_type,
            intent=media_input.intent,
            success=True,
            confidence=confidence,
            result_data=result_data,
            processing_time=0.0,  # Set by BasePipeline
        )

    async def _process_link(self, media_input: MediaInput) -> Dict[str, Any]:
        """Fetch and parse the URL from media_input.data."""
        url = media_input.data if isinstance(media_input.data, str) else ""
        if not url:
            return self._error_result("", "No URL provided", media_input.metadata)

        if not _AIOHTTP_AVAILABLE or not _BS4_AVAILABLE:
            missing = []
            if not _AIOHTTP_AVAILABLE:
                missing.append("aiohttp")
            if not _BS4_AVAILABLE:
                missing.append("beautifulsoup4")
            return self._unavailable_result(url, missing, media_input.metadata)

        return await self._fetch_and_parse(url, media_input.metadata)

    # ------------------------------------------------------------------
    # HTTP fetch
    # ------------------------------------------------------------------

    # SSRF guard moved to ``autobot_shared.url_safety`` (#7477) so
    # ``web_fetch.fetcher`` can call it directly instead of reaching into
    # ``LinkPipeline`` via a ``__new__`` hack + lazy import (which was
    # the last leg of the ``pipeline.py`` ↔ ``fetcher.py`` cycle). The
    # methods below are preserved as thin wrappers so existing callers
    # (this class + ``pipeline_test.py``) keep working unchanged.

    @staticmethod
    def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
        from autobot_shared.url_safety import _ip_is_public as _shared

        return _shared(ip)

    def _is_public_url(self, url: str) -> bool:
        from autobot_shared.url_safety import is_public_url

        return is_public_url(url)

    async def _is_public_url_async(self, url: str) -> bool:
        from autobot_shared.url_safety import is_public_url_async

        return await is_public_url_async(url)

    async def _try_jina(self, url: str) -> str | None:
        """Attempt to fetch URL via Jina Reader. Returns text content or None on failure.

        Uses a pooled ClientSession and a circuit breaker: after
        _JINA_FAILURE_THRESHOLD failures within _JINA_FAILURE_WINDOW_SECONDS,
        the circuit opens for _JINA_COOLDOWN_SECONDS and all calls short-
        circuit to None immediately.
        """
        # Circuit open? Skip the call entirely.
        if time.monotonic() < _jina_cooldown_until:
            return None

        jina_url = f"{_JINA_BASE_URL}{url}"
        try:
            session = await _get_jina_session()
            async with session.get(jina_url, allow_redirects=True, timeout=_JINA_TIMEOUT) as response:
                if response.status == 200:
                    text = await response.text(encoding="utf-8", errors="replace")
                    _record_jina_success()
                    return text
                # Non-200 counts as a failure for circuit-breaker purposes.
                _record_jina_failure()
        except Exception as exc:
            logger.debug("Jina Reader fast-path failed for %s: %s", url, exc)
            _record_jina_failure()
        return None

    def _jina_result(self, url: str, content: str, metadata: Dict) -> Dict[str, Any]:
        """Build a result dict from Jina Reader plain-text response.

        Jina Reader prepends metadata lines like ``Title: ...`` and
        ``URL Source: ...`` before a blank line and the markdown body. We
        parse the title from the ``Title:`` prefix and strip the metadata
        header from the body returned to callers.
        """
        title, body = _parse_jina_output(content)
        # Issue #5064: strip prompt-injection tokens from scraped body
        # before it reaches the KB or the LLM context.
        body = _sanitize_document(body, source="jina").sanitized_text
        word_count = len(body.split()) if body else 0
        return {
            "type": "link_fetch",
            "url": url,
            "title": title,
            "description": "",
            "content": body,
            "word_count": word_count,
            "links": [],
            "open_graph": {},
            "content_type": "text/plain",
            "confidence": 0.9 if word_count > 0 else 0.5,
            "source": "jina",
            "metadata": metadata,
        }

    async def _fetch_and_parse(self, url: str, metadata: Dict) -> Dict[str, Any]:
        """Fetch URL — tries Jina Reader fast-path first, falls back to BeautifulSoup."""
        # Fast-path: Jina Reader (public URLs only, 5-second timeout).
        # DNS resolution runs in a thread to avoid blocking the event loop.
        if await self._is_public_url_async(url):
            content = await self._try_jina(url)
            if content is not None:
                logger.debug("Jina Reader fast-path succeeded for %s", url)
                return self._jina_result(url, content, metadata)

        # Fallback: direct fetch + BeautifulSoup parse
        headers = {"User-Agent": _USER_AGENT}
        # ssl=None uses the default aiohttp SSL context (cert verification enabled).
        # Callers may pass metadata={"allow_self_signed": True} to opt-in to skipping
        # cert verification for known-safe internal URLs.
        ssl_context = False if metadata.get("allow_self_signed") else None
        try:
            async with aiohttp.ClientSession(headers=headers, timeout=_DEFAULT_TIMEOUT) as session:
                async with session.get(url, allow_redirects=True, ssl=ssl_context) as response:
                    final_url = str(response.url)
                    content_type = response.headers.get("Content-Type", "")
                    raw_html = await response.text(encoding="utf-8", errors="replace")
                    status = response.status

            if status >= 400:
                return self._error_result(
                    url,
                    f"HTTP {status} for {url}",
                    metadata,
                )
            return self._parse_html(raw_html, final_url, content_type, metadata)

        except aiohttp.ClientConnectorError as exc:
            logger.warning("Link pipeline connection error: %s", exc)
            return self._error_result(url, f"Connection error: {exc}", metadata)
        except aiohttp.ClientError as exc:
            logger.warning("Link pipeline HTTP error: %s", exc)
            return self._error_result(url, str(exc), metadata)

    # ------------------------------------------------------------------
    # HTML parsing
    # ------------------------------------------------------------------

    def _parse_html(
        self,
        html: str,
        url: str,
        content_type: str,
        metadata: Dict,
    ) -> Dict[str, Any]:
        """Parse HTML with BeautifulSoup and extract structured content."""
        soup = BeautifulSoup(html, "html.parser")

        title = self._extract_title(soup)
        description = self._extract_description(soup)
        main_text = self._extract_main_text(soup)
        links = self._extract_links(soup, url)
        og_data = self._extract_open_graph(soup)

        # Issue #5064: strip prompt-injection tokens from extracted page text
        # before it reaches the KB or the LLM context.
        main_text = _sanitize_document(main_text, source="web_html").sanitized_text

        word_count = len(main_text.split()) if main_text else 0
        confidence = 0.9 if main_text else 0.5

        return {
            "type": "link_fetch",
            "url": url,
            "title": title,
            "description": description,
            "content": main_text,
            "word_count": word_count,
            "links": links[:50],  # Cap at 50 outbound links
            "open_graph": og_data,
            "content_type": content_type,
            "confidence": confidence,
            "metadata": metadata,
        }

    def _extract_title(self, soup: Any) -> str:
        """Extract page title from <title> or og:title."""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()
        title_tag = soup.find("title")
        return title_tag.get_text(strip=True) if title_tag else ""

    def _extract_description(self, soup: Any) -> str:
        """Extract meta description or og:description."""
        for attrs in [
            {"property": "og:description"},
            {"name": "description"},
        ]:
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return tag["content"].strip()
        return ""

    def _extract_main_text(self, soup: Any) -> str:
        """Extract readable main text, removing boilerplate tags."""
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Prefer <article> or <main> content if present
        main = soup.find("article") or soup.find("main") or soup.find("body")
        if main is None:
            return ""

        text = main.get_text(separator=" ", strip=True)
        # Collapse whitespace
        return re.sub(r"\s{2,}", " ", text).strip()

    def _extract_links(self, soup: Any, base_url: str) -> List[Dict[str, str]]:
        """Extract and resolve all <a href> links on the page."""
        links = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            resolved = urljoin(base_url, href)
            text = anchor.get_text(strip=True)
            links.append({"url": resolved, "text": text[:200]})
        return links

    def _extract_open_graph(self, soup: Any) -> Dict[str, str]:
        """Extract Open Graph metadata tags."""
        og: Dict[str, str] = {}
        for tag in soup.find_all("meta", property=re.compile(r"^og:")):
            key = tag.get("property", "")[3:]  # strip "og:"
            content = tag.get("content", "")
            if key and content:
                og[key] = content
        return og

    # ------------------------------------------------------------------
    # Error/fallback helpers
    # ------------------------------------------------------------------

    def _unavailable_result(self, url: str, missing_libs: List[str], metadata: Dict) -> Dict[str, Any]:
        """Return structured result when dependencies are missing."""
        reason = f"Missing libraries: {', '.join(missing_libs)}"
        logger.warning("Link pipeline unavailable: %s", reason)
        return {
            "type": "link_fetch",
            "url": url,
            "title": "",
            "content": "",
            "links": [],
            "processing_status": "unavailable",
            "unavailability_reason": reason,
            "confidence": 0.0,
            "metadata": metadata,
        }

    def _error_result(self, url: str, error: str, metadata: Dict) -> Dict[str, Any]:
        """Return structured result on fetch/parse error."""
        return {
            "type": "link_fetch",
            "url": url,
            "title": "",
            "content": "",
            "links": [],
            "processing_status": "error",
            "error": error,
            "confidence": 0.0,
            "metadata": metadata,
        }

    def _calculate_confidence(self, result_data: Dict[str, Any]) -> float:
        """Calculate confidence score from result data."""
        return result_data.get("confidence", 0.5)


# ----------------------------------------------------------------------
# LinkResult — lightweight result type for process_url() callers.
# ----------------------------------------------------------------------


@dataclass
class LinkResult:
    """Structured result returned by :func:`process_url`.

    Attributes:
        url:        The fetched URL (after redirects).
        success:    True when usable content was obtained.
        markdown:   Extracted markdown text (empty on failure).
        title:      Page title, if parsed.
        source:     Which backend produced the result (jina/bs4/playwright).
        error_code: ``web_fetch`` error constant on failure, else ``None``.
        retryable:  True when a retry may succeed.
    """

    url: str
    success: bool
    markdown: str = ""
    title: str = ""
    source: str = ""
    error_code: str | None = None
    retryable: bool = False


async def process_url(url: str, render: str = "auto", timeout: float = 30.0) -> LinkResult:
    """Fetch *url* and return a :class:`LinkResult`.

    This is the thin public convenience entry-point for callers that hold a
    raw URL string.  Internally it delegates to :class:`web_fetch.WebFetcher`
    so all Jina/BS4/Playwright logic, caching, and SSRF guards are exercised
    through the canonical implementation.

    The function is intentionally <= 30 lines (CLAUDE.md constraint).

    Args:
        url:     Absolute URL to fetch.
        render:  ``"auto"`` | ``"fast"`` | ``"playwright"``.
        timeout: Per-request timeout in seconds.

    Returns:
        :class:`LinkResult` with ``success=True`` and populated ``markdown``
        on success; ``success=False`` and ``error_code`` on failure.
    """
    from web_fetch import FetchResult, RenderMode, WebFetcher

    render_mode = RenderMode(render) if render in {m.value for m in RenderMode} else RenderMode.AUTO
    fetch_result: FetchResult = await WebFetcher.fetch(url, render=render_mode, timeout=timeout)
    return LinkResult(
        url=fetch_result.url,
        success=fetch_result.success,
        markdown=fetch_result.markdown,
        title=fetch_result.title,
        source=fetch_result.source,
        error_code=fetch_result.error_code,
        retryable=fetch_result.retryable,
    )


# ----------------------------------------------------------------------
# Module-level helpers: pooled session, circuit breaker, title parsing
# ----------------------------------------------------------------------


async def _get_jina_session() -> "aiohttp.ClientSession":
    """Return the shared Jina Reader aiohttp.ClientSession, creating on first call.

    Lazy-created under an asyncio.Lock so concurrent first calls don't each
    create their own session. Closed at app shutdown via close_jina_session().
    """
    global _jina_session, _jina_session_lock
    if _jina_session_lock is None:
        _jina_session_lock = asyncio.Lock()
    if _jina_session is None or _jina_session.closed:
        async with _jina_session_lock:
            if _jina_session is None or _jina_session.closed:
                _jina_session = aiohttp.ClientSession()
    return _jina_session


async def close_jina_session() -> None:
    """Close the pooled Jina Reader session. Call from app shutdown hook."""
    global _jina_session
    if _jina_session is not None and not _jina_session.closed:
        await _jina_session.close()
    _jina_session = None


def _record_jina_failure() -> None:
    """Record a Jina Reader failure and open the circuit if threshold reached."""
    global _jina_cooldown_until
    now = time.monotonic()
    cutoff = now - _JINA_FAILURE_WINDOW_SECONDS
    # Drop entries older than the window.
    _jina_failures_in_window[:] = [t for t in _jina_failures_in_window if t > cutoff]
    _jina_failures_in_window.append(now)
    if len(_jina_failures_in_window) >= _JINA_FAILURE_THRESHOLD:
        _jina_cooldown_until = now + _JINA_COOLDOWN_SECONDS
        logger.info(
            "Jina Reader circuit opened for %.0fs after %d failures",
            _JINA_COOLDOWN_SECONDS,
            len(_jina_failures_in_window),
        )
        _jina_failures_in_window.clear()


def _record_jina_success() -> None:
    """Record a Jina Reader success, clearing the failure window."""
    _jina_failures_in_window.clear()


# Extracted to ``autobot_shared.jina_parser.parse_jina_output`` (#7460) so
# that ``web_fetch/extractors.py`` and other consumers can import it
# without triggering this module's heavy import chain
# (``knowledge.query_sanitizer`` + further deps). Re-exported here under
# the original ``_parse_jina_output`` name to preserve the existing 4
# test imports in ``pipeline_test.py``.
from autobot_shared.jina_parser import parse_jina_output as _parse_jina_output
