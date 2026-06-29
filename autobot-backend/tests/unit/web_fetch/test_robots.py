# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for web_fetch.robots — parser, cache hit/miss, override behavior."""

from unittest.mock import AsyncMock, patch

import pytest

from tests.fixtures import make_async_redis
from web_fetch.robots import (
    RobotsCache,
    _extract_domain,
    _parse_robots,
    _robots_cache_key,
)

_ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /"
_ROBOTS_DISALLOW_ALL = "User-agent: *\nDisallow: /"
_ROBOTS_SELECTIVE = "User-agent: *\nDisallow: /private/\nAllow: /"


class TestHelpers:
    def test_extract_domain(self) -> None:
        assert _extract_domain("https://example.com/path?q=1") == "https://example.com"

    def test_extract_domain_preserves_port(self) -> None:
        assert _extract_domain("http://localhost:8080/path") == "http://localhost:8080"  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default

    def test_robots_cache_key_format(self) -> None:
        key = _robots_cache_key("https://example.com")
        assert key == "web_fetch:robots:https://example.com"

    def test_parse_robots_allow_all(self) -> None:
        parser = _parse_robots(_ROBOTS_ALLOW_ALL, "https://example.com")
        assert parser.can_fetch("AutoBot/1.0", "https://example.com/page") is True

    def test_parse_robots_disallow_all(self) -> None:
        parser = _parse_robots(_ROBOTS_DISALLOW_ALL, "https://example.com")
        assert parser.can_fetch("AutoBot/1.0", "https://example.com/page") is False

    def test_parse_robots_selective(self) -> None:
        parser = _parse_robots(_ROBOTS_SELECTIVE, "https://example.com")
        assert parser.can_fetch("AutoBot/1.0", "https://example.com/public") is True
        assert parser.can_fetch("AutoBot/1.0", "https://example.com/private/data") is False


class TestRobotsCacheAllowed:
    """RobotsCache.is_allowed() returns True for robots.txt that allows all."""

    @pytest.mark.asyncio
    async def test_allow_all_positive(self) -> None:
        redis = make_async_redis()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch("web_fetch.robots._fetch_robots_text", return_value=_ROBOTS_ALLOW_ALL):
            cache = RobotsCache(redis_client=redis)
            allowed = await cache.is_allowed("https://example.com/page")

        assert allowed is True

    @pytest.mark.asyncio
    async def test_disallow_all_negative(self) -> None:
        redis = make_async_redis()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch("web_fetch.robots._fetch_robots_text", return_value=_ROBOTS_DISALLOW_ALL):
            cache = RobotsCache(redis_client=redis)
            allowed = await cache.is_allowed("https://example.com/page")

        assert allowed is False


class TestRobotsCacheHitMiss:
    """Cache hit avoids re-fetching robots.txt from network."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetch(self) -> None:
        redis = make_async_redis()
        cached_text = _ROBOTS_ALLOW_ALL.encode("utf-8")
        redis.get = AsyncMock(return_value=cached_text)
        redis.setex = AsyncMock()

        fetch_called = False

        async def mock_fetch(domain, timeout=10.0):
            nonlocal fetch_called
            fetch_called = True
            return ""

        with patch("web_fetch.robots._fetch_robots_text", side_effect=mock_fetch):
            cache = RobotsCache(redis_client=redis)
            allowed = await cache.is_allowed("https://cached.com/page")

        assert not fetch_called
        assert allowed is True

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_fetch_and_stores(self) -> None:
        redis = make_async_redis()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch("web_fetch.robots._fetch_robots_text", return_value=_ROBOTS_ALLOW_ALL) as mock_f:
            cache = RobotsCache(redis_client=redis)
            await cache.is_allowed("https://miss.com/page")

        mock_f.assert_called_once()
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_in_memory_cache_prevents_second_redis_lookup(self) -> None:
        redis = make_async_redis()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch("web_fetch.robots._fetch_robots_text", return_value=_ROBOTS_ALLOW_ALL):
            cache = RobotsCache(redis_client=redis)
            await cache.is_allowed("https://example.com/page1")
            redis.get.reset_mock()
            await cache.is_allowed("https://example.com/page2")

        redis.get.assert_not_called()


class TestRobotsCacheRedisErrors:
    """Redis load/save errors are swallowed — cache degrades gracefully."""

    @pytest.mark.asyncio
    async def test_load_redis_exception_triggers_network_fetch(self) -> None:
        redis = make_async_redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        redis.setex = AsyncMock()

        with patch("web_fetch.robots._fetch_robots_text", return_value=_ROBOTS_ALLOW_ALL):
            cache = RobotsCache(redis_client=redis)
            allowed = await cache.is_allowed("https://example.com/page")

        assert allowed is True

    @pytest.mark.asyncio
    async def test_save_redis_exception_swallowed(self) -> None:
        redis = make_async_redis()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(side_effect=Exception("write failed"))

        with patch("web_fetch.robots._fetch_robots_text", return_value=_ROBOTS_ALLOW_ALL):
            cache = RobotsCache(redis_client=redis)
            # Should not raise even when setex fails
            allowed = await cache.is_allowed("https://example.com/page")

        assert allowed is True

    @pytest.mark.asyncio
    async def test_string_cache_value_handled(self) -> None:
        """Redis may return str instead of bytes — both must work."""
        redis = make_async_redis()
        # Return plain string (not bytes)
        redis.get = AsyncMock(return_value=_ROBOTS_ALLOW_ALL)
        redis.setex = AsyncMock()

        cache = RobotsCache(redis_client=redis)
        allowed = await cache.is_allowed("https://example.com/page")
        assert allowed is True


class TestRobotsCacheFailOpen:
    """On fetch failure, robots check is fail-open (returns True)."""

    @pytest.mark.asyncio
    async def test_network_failure_allows_fetch(self) -> None:
        redis = make_async_redis()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        with patch("web_fetch.robots._fetch_robots_text", return_value=""):
            cache = RobotsCache(redis_client=None)
            allowed = await cache.is_allowed("https://down.com/page")

        assert allowed is True

    @pytest.mark.asyncio
    async def test_no_redis_still_works(self) -> None:
        with patch("web_fetch.robots._fetch_robots_text", return_value=_ROBOTS_ALLOW_ALL):
            cache = RobotsCache(redis_client=None)
            allowed = await cache.is_allowed("https://example.com/page")

        assert allowed is True
