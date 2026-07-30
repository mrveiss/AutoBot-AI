# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

SSRF (#13019): ``_fetch_and_parse``'s BeautifulSoup fallback previously had
no enforcement of its own — ``_is_public_url_async`` only gated the Jina
fast-path attempt, so a non-public URL simply skipped Jina and fell through
to an UNGUARDED direct connect. It now routes through
``autobot_shared.security.ssrf_guard.pinned_request_with_redirects``, which
independently resolves + pins every hop (including redirects) before
connecting, unconditionally — closing both the missing-gate bug and the
check-then-connect TOCTOU in one fix. ``_try_jina`` is unaffected: its
connect target is always the fixed, trusted ``r.jina.ai`` host (the caller's
``url`` is only embedded in the request path), so pinning it is a no-op.
"""

import ipaddress
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import urljoin

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
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
# #13021: 1 MB cap (env-overridable) on the fallback fetch's HTML download,
# now actually enforced by ``_read_bounded_content`` during the streamed
# read — previously declared but never applied, so an oversized/slow-drip
# response could be read unbounded into memory.
_MAX_CONTENT_LENGTH = config.link_pipeline_max_content_bytes
_READ_CHUNK_SIZE = 65536
_USER_AGENT = "AutoBot/1.0 (media-pipeline)"
_JINA_BASE_URL = "https://r.jina.ai/"


def _resolve_max_redirects() -> int:
    """Return max redirect hops for the pinned fallback fetch from env var (default 5)."""
    raw = config.misc.web_fetch_max_redirects
    return raw if raw else 5


_MAX_REDIRECTS: int = _resolve_max_redirects()

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

# Jina Reader requests go through the shared HTTPClientManager session
# (#11641) — no private session fork; see _get_jina_session().


async def _read_bounded_content(response: Any, url: str) -> bytes | None:
    """Stream *response*'s body in chunks, refusing it once it exceeds
    ``_MAX_CONTENT_LENGTH`` instead of reading it fully into memory (#13021).

    Mirrors ``web_fetch/fetcher.py._fetch_bs4``'s chunked-read guard. Returns
    ``None`` (never partial bytes) the moment the cap is crossed — the
    remaining chunks are never requested from the transport, so an oversized
    or slow-drip response is cut off mid-stream rather than read to
    completion and discarded after the fact.
    """
    content = b""
    async for chunk in response.content.iter_chunked(_READ_CHUNK_SIZE):
        content += chunk
        if len(content) > _MAX_CONTENT_LENGTH:
            logger.warning(
                "Link pipeline fallback fetch REJECTED %s: body exceeded max_content_length=%d bytes "
                "(distinct from a fetch/connection failure)",
                url,
                _MAX_CONTENT_LENGTH,
            )
            return None
    return content


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
            async with _get_jina_session() as session:
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
        """Fetch URL — tries Jina Reader fast-path first, falls back to BeautifulSoup.

        The fallback fetch is SSRF-guarded unconditionally (#13019): it no
        longer relies on the ``_is_public_url_async`` check above (which only
        ever gated the Jina attempt, not this path) — every real connection
        is resolved + pinned per hop by ``pinned_request_with_redirects``, so
        a non-public or DNS-rebound URL is rejected here even when Jina was
        skipped.
        """
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
        from autobot_shared.security.ssrf_guard import SSRFError, pinned_request_with_redirects

        try:
            async with pinned_request_with_redirects(
                "GET",
                url,
                headers=headers,
                timeout=_DEFAULT_TIMEOUT,
                max_redirects=_MAX_REDIRECTS,
                ssl=ssl_context,
            ) as response:
                final_url = str(response.url)
                content_type = response.headers.get("Content-Type", "")
                status = response.status
                raw_bytes = await _read_bounded_content(response, url)

            if status >= 400:
                return self._error_result(
                    url,
                    f"HTTP {status} for {url}",
                    metadata,
                )
            if raw_bytes is None:
                return self._error_result(url, "response body exceeded max content length", metadata)
            raw_html = raw_bytes.decode("utf-8", errors="replace")
            return self._parse_html(raw_html, final_url, content_type, metadata)

        except SSRFError as exc:
            logger.warning("Link pipeline fetch blocked by SSRF guard for %s: %s", url, exc)
            return self._error_result(url, "blocked by SSRF guard", metadata)
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


def _get_jina_session():
    """Return an async context manager yielding the shared pooled aiohttp session.

    Issue #11641: the private module-level Jina session forked the concept
    owned by ``autobot_shared.http_client.HTTPClientManager``. Delegates to
    the canonical singleton (lifecycle managed there); the Jina-specific
    timeout stays per-request via ``_JINA_TIMEOUT``. Kept as an indirection
    point — tests patch this seam.

    Issue #11656: delegates to ``HTTPClientManager.tracked_session()`` (not
    the raw ``get_session()``) so a Jina fetch is counted in the SAME
    ``_active_requests`` counter ``request()`` uses. Without this, a pool
    resize driven by concurrent ``request()`` traffic could close the
    shared session out from under an in-flight Jina fetch.
    """
    from autobot_shared.http_client import get_http_client

    return get_http_client().tracked_session()


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
