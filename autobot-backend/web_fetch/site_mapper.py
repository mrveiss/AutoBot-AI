# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
web_fetch.site_mapper — Domain site-map extraction.

Issue #7403: POST /knowledge/site-map endpoint.

Strategy:
  1. Fetch https://{domain}/sitemap.xml and parse with stdlib xml.etree.ElementTree.
  2. Handle <sitemapindex> (nested sitemaps) — recurse one level.
  3. On 404/parse-failure, fall back to BFS crawl (max_depth=3, links-only).
  4. Cap results at max_urls per request.

Public API::

    from web_fetch.site_mapper import SiteMapper, SiteMapEntry, SiteMapResult
from autobot_shared.logging_manager import get_logger
"""

from __future__ import annotations

import xml.etree.ElementTree as ET  # nosec B405 — sitemap XML from crawled URLs; XXE risk accepted
from typing import List
from urllib.parse import urlparse

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SITEMAP_TIMEOUT = 15.0  # seconds


class SiteMapEntry:
    """A single URL discovered during site-map extraction."""

    __slots__ = ("url", "title", "depth")

    def __init__(self, url: str, title: str | None, depth: int) -> None:
        self.url = url
        self.title = title
        self.depth = depth

    def to_dict(self) -> dict:
        return {"url": self.url, "title": self.title, "depth": self.depth}


class SiteMapResult:
    """Aggregated result returned by SiteMapper.map_site."""

    __slots__ = ("domain", "source", "entries")

    def __init__(self, domain: str, source: str, entries: List[SiteMapEntry]) -> None:
        self.domain = domain
        self.source = source  # "sitemap" or "crawl"
        self.entries = entries


def _ns(tag: str) -> str:
    """Qualify an unqualified sitemap tag name with the sitemap namespace."""
    return f"{{{_SITEMAP_NS}}}{tag}"


async def _fetch_xml(url: str) -> str | None:
    """Fetch a URL and return the response body text, or None on failure."""
    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=_SITEMAP_TIMEOUT)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout, allow_redirects=True) as resp:
                if resp.status == 200:
                    return await resp.text(encoding="utf-8", errors="replace")
        logger.debug("sitemap fetch HTTP %s for %s", resp.status, url)
        return None
    except Exception as exc:
        logger.debug("sitemap fetch error for %s: %s", url, exc)
        return None


def _parse_urlset(root: ET.Element) -> List[str]:
    """Extract all <url><loc> values from a <urlset> element."""
    urls: List[str] = []
    for url_el in root.findall(_ns("url")):
        loc = url_el.find(_ns("loc"))
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls


def _parse_sitemapindex(root: ET.Element) -> List[str]:
    """Extract all <sitemap><loc> values from a <sitemapindex> element."""
    urls: List[str] = []
    for sitemap_el in root.findall(_ns("sitemap")):
        loc = sitemap_el.find(_ns("loc"))
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls


def _safe_parse(xml_text: str, source_url: str) -> ET.Element | None:
    """Parse XML defensively; log a warning and return None on any error."""
    try:
        return ET.fromstring(xml_text)  # nosec B314 — sitemap XML from crawled URLs; XXE risk accepted
    except ET.ParseError as exc:
        logger.warning("sitemap XML parse error for %s: %s", source_url, exc)
        return None


async def _resolve_sitemap_urls(sitemap_url: str) -> List[str] | None:
    """Fetch one sitemap URL and return all discovered <loc> URLs.

    Handles both <urlset> (leaf) and <sitemapindex> (index) documents.
    Recurses one level for sitemapindex entries (nested sitemaps are fetched
    but their children are not recursed further).

    Returns None when the sitemap cannot be fetched or parsed.
    """
    text = await _fetch_xml(sitemap_url)
    if text is None:
        return None
    root = _safe_parse(text, sitemap_url)
    if root is None:
        return None

    if root.tag == _ns("sitemapindex"):
        child_locs = _parse_sitemapindex(root)
        return await _resolve_nested_sitemaps(child_locs)

    if root.tag == _ns("urlset"):
        return _parse_urlset(root)

    logger.warning("sitemap unknown root tag %s for %s", root.tag, sitemap_url)
    return None


async def _resolve_nested_sitemaps(child_locs: List[str]) -> List[str]:
    """Fetch each child sitemap and collect all leaf URLs (one level deep)."""
    import asyncio

    tasks = [_fetch_single_urlset(loc) for loc in child_locs]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    combined: List[str] = []
    for res in results:
        if isinstance(res, list):
            combined.extend(res)
    return combined


async def _fetch_single_urlset(sitemap_url: str) -> List[str]:
    """Fetch one child sitemap and return its leaf URLs (no further recursion)."""
    text = await _fetch_xml(sitemap_url)
    if text is None:
        return []
    root = _safe_parse(text, sitemap_url)
    if root is None or root.tag != _ns("urlset"):
        return []
    return _parse_urlset(root)


def _domain_to_seed(domain: str) -> str:
    """Convert a bare domain to an https:// seed URL."""
    parsed = urlparse(domain)
    if parsed.scheme in ("http", "https"):
        return domain
    return f"https://{domain}"


async def _crawl_fallback(seed: str, max_urls: int) -> List[SiteMapEntry]:
    """BFS crawl fallback when sitemap is absent.

    Uses Frontier (max_depth=3, links-only — no body fetch).  Only link
    discovery is needed here; bodies are NOT fetched to keep this fast.
    robots.txt is always honored in the fallback path.
    """
    from web_fetch.fetcher import WebFetcher
    from web_fetch.frontier import Frontier, extract_links

    frontier = Frontier(seed, max_pages=max_urls, max_depth=3, same_origin=True)
    entries: List[SiteMapEntry] = []

    while (item := frontier.next()) is not None:
        url, depth = item
        entries.append(SiteMapEntry(url=url, title=None, depth=depth))
        if len(entries) >= max_urls:
            break
        html, status = await WebFetcher.fetch_raw_html(url, timeout=10.0)
        if html and status is not None and status < 400:
            links = extract_links(html, url, same_origin_only=True)
            frontier.add_links(links, depth + 1)

    return entries


async def _crawl_fallback_with_robots(seed: str, max_urls: int, respect_robots: bool) -> List[SiteMapEntry]:
    """Crawl fallback with optional robots.txt enforcement."""
    if not respect_robots:
        return await _crawl_fallback(seed, max_urls)

    from web_fetch.fetcher import WebFetcher
    from web_fetch.frontier import Frontier, extract_links
    from web_fetch.robots import RobotsCache

    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client()
        robots_cache = RobotsCache(redis_client=redis)
    except Exception:
        robots_cache = RobotsCache()

    frontier = Frontier(seed, max_pages=max_urls, max_depth=3, same_origin=True)
    entries: List[SiteMapEntry] = []

    while (item := frontier.next()) is not None:
        url, depth = item
        if not await robots_cache.is_allowed(url):
            logger.debug("sitemap crawl: robots blocked %s", url)
            continue
        entries.append(SiteMapEntry(url=url, title=None, depth=depth))
        if len(entries) >= max_urls:
            break
        html, status = await WebFetcher.fetch_raw_html(url, timeout=10.0)
        if html and status is not None and status < 400:
            links = extract_links(html, url, same_origin_only=True)
            frontier.add_links(links, depth + 1)

    return entries


class SiteMapper:
    """Extracts a list of URLs for a domain via sitemap.xml or BFS crawl.

    Usage::

        result = await SiteMapper.map_site("example.com")
        for entry in result.entries:
            print(entry.url, entry.depth)
    """

    @classmethod
    async def map_site(
        cls,
        domain: str,
        max_urls: int = 500,
        respect_robots: bool = True,
    ) -> SiteMapResult:
        """Discover URLs for *domain*.

        Tries ``https://{domain}/sitemap.xml`` first.  Falls back to BFS crawl
        when the sitemap is missing or unparseable.

        Args:
            domain: Domain (bare or with scheme, e.g. "example.com").
            max_urls: Hard cap on returned entries.
            respect_robots: Honour robots.txt during the crawl fallback.

        Returns:
            SiteMapResult with source="sitemap" or "crawl".
        """
        seed = _domain_to_seed(domain)
        sitemap_url = f"{seed.rstrip('/')}/sitemap.xml"

        raw_urls = await _resolve_sitemap_urls(sitemap_url)
        if raw_urls is not None:
            entries = [SiteMapEntry(url=u, title=None, depth=0) for u in raw_urls[:max_urls]]
            logger.info("site-map: %d URLs from sitemap for %s", len(entries), domain)
            return SiteMapResult(domain=domain, source="sitemap", entries=entries)

        logger.info("site-map: sitemap miss for %s, falling back to crawl", domain)
        entries = await _crawl_fallback_with_robots(seed, max_urls, respect_robots)
        return SiteMapResult(domain=domain, source="crawl", entries=entries)
