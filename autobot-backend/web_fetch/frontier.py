# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
web_fetch.frontier — BFS Frontier for crawling: queue, visited set, depth tracking.

Issue #7400: Foundation package for unified web search/scrape/crawl.
"""

from __future__ import annotations

import hashlib
from collections import deque
from typing import List, Tuple
from urllib.parse import urljoin, urlparse

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _url_key(url: str) -> str:
    """Normalised dedup key: scheme+host+path (strips query/fragment)."""
    parsed = urlparse(url)
    normalised = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _same_origin(url: str, base: str) -> bool:
    """Return True when url and base share scheme + netloc."""
    u = urlparse(url)
    b = urlparse(base)
    return u.scheme == b.scheme and u.netloc == b.netloc


def extract_links(html: str, base: str, same_origin_only: bool = False) -> List[str]:
    """Extract and resolve <a href> links from HTML.

    Args:
        html: Raw HTML string.
        base: Base URL for resolving relative hrefs.
        same_origin_only: When True, discard cross-origin links.

    Returns:
        List of absolute, deduplicated URLs (fragments stripped).
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("bs4 not available; extract_links returns empty list")
        return []

    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    result: List[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        resolved = urljoin(base, href)
        parsed = urlparse(resolved)
        if parsed.scheme not in ("http", "https"):
            continue
        clean = parsed._replace(fragment="").geturl()
        if same_origin_only and not _same_origin(clean, base):
            continue
        key = _url_key(clean)
        if key not in seen:
            seen.add(key)
            result.append(clean)
    return result


class Frontier:
    """BFS crawl frontier: deduplication, depth tracking, domain filter.

    Usage::

        frontier = Frontier(seed_url, max_pages=50, max_depth=3)
        while (item := frontier.next()) is not None:
            url, depth = item
            html = await fetch(url)
            links = extract_links(html, url, same_origin_only=True)
            frontier.add_links(links, depth + 1)
    """

    def __init__(
        self,
        seed_url: str,
        max_pages: int = 50,
        max_depth: int = 3,
        same_origin: bool = True,
    ) -> None:
        self._seed = seed_url
        self._max_pages = max_pages
        self._max_depth = max_depth
        self._same_origin = same_origin
        self._visited: set[str] = set()
        self._queue: deque[Tuple[str, int]] = deque()
        self._pages_emitted = 0
        self._enqueue(seed_url, 0)

    def _enqueue(self, url: str, depth: int) -> None:
        """Add url to queue if not already visited."""
        key = _url_key(url)
        if key not in self._visited:
            self._visited.add(key)
            self._queue.append((url, depth))

    def next(self) -> Tuple[str, int] | None:
        """Pop the next (url, depth) pair, or return None when frontier is empty."""
        if not self._queue or self._pages_emitted >= self._max_pages:
            return None
        url, depth = self._queue.popleft()
        self._pages_emitted += 1
        return url, depth

    def add_links(self, links: List[str], depth: int) -> None:
        """Enqueue links for crawling if within depth/page/origin limits."""
        if depth > self._max_depth:
            return
        for url in links:
            if self._same_origin and not _same_origin(url, self._seed):
                continue
            self._enqueue(url, depth)

    @property
    def pages_emitted(self) -> int:
        """Total pages handed to callers so far."""
        return self._pages_emitted

    @property
    def visited_count(self) -> int:
        """Total unique URLs seen (queued or emitted)."""
        return len(self._visited)

    def exhausted(self) -> bool:
        """Return True when no more pages will be returned."""
        return len(self._queue) == 0 or self._pages_emitted >= self._max_pages
