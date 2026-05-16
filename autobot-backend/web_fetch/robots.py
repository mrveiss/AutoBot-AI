# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
web_fetch.robots — robots.txt fetching and compliance check with Redis cache.

Issue #7400: Foundation package for unified web search/scrape/crawl.

Cache key: web_fetch:robots:<domain>
TTL: 1 hour (hardcoded per robots.txt staleness expectations).
"""

from __future__ import annotations

import asyncio
import urllib.robotparser
from urllib.parse import urlparse

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_ROBOTS_CACHE_TTL = 3600  # 1 hour, per robots.txt staleness expectations
_USER_AGENT = "AutoBot/1.0"


def _robots_cache_key(domain: str) -> str:
    """Return Redis key for the parsed robots.txt text of a domain."""
    return f"web_fetch:robots:{domain}"


def _extract_domain(url: str) -> str:
    """Return scheme + netloc for a URL (cache key granularity)."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _parse_robots(robots_text: str, domain: str) -> urllib.robotparser.RobotFileParser:
    """Parse robots.txt content into a RobotFileParser instance."""
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(f"{domain}/robots.txt")
    parser.parse(robots_text.splitlines())
    return parser


async def _fetch_robots_text(domain: str, timeout: float = 10.0) -> str:
    """Fetch robots.txt for domain, returning empty string on any error."""
    try:
        import aiohttp

        robots_url = f"{domain}/robots.txt"
        aio_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession() as session:
            async with session.get(robots_url, timeout=aio_timeout, allow_redirects=True) as resp:
                if resp.status == 200:
                    return await resp.text(encoding="utf-8", errors="replace")
        return ""
    except Exception as exc:
        logger.debug("robots.txt fetch failed for %s: %s", domain, exc)
        return ""


class RobotsCache:
    """Fetches, parses, and caches robots.txt per domain.

    Cache backend: Redis via get_async_redis_client().
    TTL: 1 hour.
    Fail-open: if robots.txt cannot be retrieved, all URLs are allowed.
    """

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client
        self._local: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, url: str, user_agent: str = _USER_AGENT) -> bool:
        """Return True if user_agent is allowed to fetch url per robots.txt.

        Fail-open: ``_fetch_robots_text`` returns ``""`` on any error and
        ``_parse_robots`` parses an empty string into a permissive
        ``RobotFileParser`` whose ``can_fetch`` returns True for every URL.
        ``_get_parser`` always returns a parser (Issue #7461).
        """
        domain = _extract_domain(url)
        parser = await self._get_parser(domain)
        assert parser is not None, "robots parser must be initialized"
        return parser.can_fetch(user_agent, url)

    async def _get_parser(self, domain: str) -> urllib.robotparser.RobotFileParser:
        """Return cached parser for domain, fetching and caching if needed."""
        async with self._lock:
            if domain in self._local:
                return self._local[domain]
            text = await self._load_from_redis(domain)
            if text is None:
                text = await _fetch_robots_text(domain)
                await self._save_to_redis(domain, text)
            parser = _parse_robots(text, domain)
            self._local[domain] = parser
            return parser

    async def _load_from_redis(self, domain: str) -> str | None:
        """Return cached robots.txt text from Redis, or None on miss."""
        if self._redis is None:
            return None
        key = _robots_cache_key(domain)
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw
        except Exception as exc:
            logger.warning("robots cache load failed for %s: %s", domain, exc)
            return None

    async def _save_to_redis(self, domain: str, text: str) -> None:
        """Store robots.txt text in Redis with 1h TTL."""
        if self._redis is None:
            return
        key = _robots_cache_key(domain)
        try:
            await self._redis.setex(key, _ROBOTS_CACHE_TTL, text.encode("utf-8"))
        except Exception as exc:
            logger.warning("robots cache save failed for %s: %s", domain, exc)
