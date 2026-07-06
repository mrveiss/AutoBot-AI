# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""content_reach._url_guard — SSRF + robots.txt guards for URL-fetching backends (#10932, #11095).

Public API
----------
- :func:`ensure_public_url` — raises BackendError if url is falsy or non-public (SSRF guard).
- :func:`ensure_robots_allowed` — raises BackendError if robots.txt disallows fetching url.
  No-op when ``AUTOBOT_CONTENT_REACH_RESPECT_ROBOTS`` is ``0``, ``false``, or ``no``.
  Fail-open on robots-fetch errors (log warning + allow).

Both functions must be awaited BEFORE any httpx/browser/caption call.
"""

from __future__ import annotations

import asyncio
import logging
import os
import urllib.robotparser
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Module-level constant: read once at import time.
_RESPECT_ROBOTS: bool = os.environ.get("AUTOBOT_CONTENT_REACH_RESPECT_ROBOTS", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)

# User-agent used when checking robots.txt.
_ROBOTS_UA = "autobot-content-reach/1.0"

# robots.txt per-domain cache (in-process, no Redis dependency).
_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
_robots_cache_lock = asyncio.Lock()

# Robots fetch timeout in seconds.
_ROBOTS_FETCH_TIMEOUT = 10.0


def _extract_domain(url: str) -> str:
    """Return scheme + netloc for a URL (robots cache granularity)."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def _fetch_robots_text(domain: str) -> str:
    """Fetch robots.txt for domain; return empty string on any error (fail-open)."""
    import aiohttp

    robots_url = f"{domain}/robots.txt"
    try:
        timeout = aiohttp.ClientTimeout(total=_ROBOTS_FETCH_TIMEOUT)
        async with aiohttp.ClientSession() as session:
            async with session.get(robots_url, timeout=timeout, allow_redirects=True) as resp:
                if resp.status == 200:
                    return await resp.text(encoding="utf-8", errors="replace")
        return ""
    except Exception as exc:
        logger.debug("content_reach robots.txt fetch failed for %s: %s", domain, exc)
        return ""


def _parse_robots(text: str, domain: str) -> urllib.robotparser.RobotFileParser:
    """Parse robots.txt content into a RobotFileParser."""
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(f"{domain}/robots.txt")
    parser.parse(text.splitlines())
    return parser


async def _get_robots_parser(domain: str) -> urllib.robotparser.RobotFileParser:
    """Return cached RobotFileParser for domain, fetching if needed."""
    async with _robots_cache_lock:
        if domain not in _robots_cache:
            text = await _fetch_robots_text(domain)
            _robots_cache[domain] = _parse_robots(text, domain)
        return _robots_cache[domain]


async def _robots_is_allowed(url: str, ua: str) -> bool:
    """Return True if robots.txt allows ua to fetch url.

    Module-level so tests can monkeypatch without deep import surgery.
    Fail-open: returns True on any parsing error.
    """
    domain = _extract_domain(url)
    parser = await _get_robots_parser(domain)
    return parser.can_fetch(ua, url)


async def _is_public_url_async(url: str) -> bool:
    """SSRF guard delegate — module-level so tests can monkeypatch."""
    from autobot_shared.url_safety import is_public_url_async

    return await is_public_url_async(url)


async def ensure_public_url(url: str) -> None:
    """Raise BackendError if url is falsy or resolves to a non-public address (SSRF guard).

    Guards must run BEFORE any network call so a blocked url makes ZERO fetch calls.
    """
    from content_reach.base import BackendError

    if not url or not await _is_public_url_async(url):
        raise BackendError(f"blocked non-public or invalid url: {url!r}")


async def ensure_robots_allowed(url: str) -> None:
    """Raise BackendError if robots.txt disallows fetching url.

    No-op when AUTOBOT_CONTENT_REACH_RESPECT_ROBOTS is 0/false/no.
    Fail-open on robots-fetch errors (log warning, allow) — a broken robots endpoint
    must not block content, matching web_fetch behavior.
    """
    if not _RESPECT_ROBOTS:
        return
    from content_reach.base import BackendError

    try:
        allowed = await _robots_is_allowed(url, _ROBOTS_UA)
    except Exception as exc:
        logger.warning("content_reach robots check failed for %r (fail-open): %s", url, exc)
        return
    if not allowed:
        raise BackendError(f"robots.txt disallows fetching {url!r}")
