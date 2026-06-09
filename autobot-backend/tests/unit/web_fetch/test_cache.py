# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for web_fetch.cache — TTL resolver, content cache hit/miss."""

import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from web_fetch.cache import (
    _WEB_FETCH_CACHE_TTL,
    _content_cache_key,
    _resolve_web_fetch_cache_ttl,
    get_cached_result,
    set_cached_result,
)


class TestTTLResolver:
    def test_default_is_24h(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            env = {k: v for k, v in os.environ.items() if k != "AUTOBOT_WEB_FETCH_CACHE_TTL"}
            with patch.dict(os.environ, env, clear=True):
                ttl = _resolve_web_fetch_cache_ttl()
        assert ttl == 86400

    def test_env_override(self) -> None:
        with patch.dict(os.environ, {"AUTOBOT_WEB_FETCH_CACHE_TTL": "3600"}):
            ttl = _resolve_web_fetch_cache_ttl()
        assert ttl == 3600

    def test_invalid_string_falls_back(self) -> None:
        with patch.dict(os.environ, {"AUTOBOT_WEB_FETCH_CACHE_TTL": "not_a_number"}):
            ttl = _resolve_web_fetch_cache_ttl()
        assert ttl == 86400

    def test_zero_falls_back(self) -> None:
        with patch.dict(os.environ, {"AUTOBOT_WEB_FETCH_CACHE_TTL": "0"}):
            ttl = _resolve_web_fetch_cache_ttl()
        assert ttl == 86400

    def test_negative_falls_back(self) -> None:
        with patch.dict(os.environ, {"AUTOBOT_WEB_FETCH_CACHE_TTL": "-100"}):
            ttl = _resolve_web_fetch_cache_ttl()
        assert ttl == 86400

    def test_module_level_constant_is_integer(self) -> None:
        assert isinstance(_WEB_FETCH_CACHE_TTL, int)
        assert _WEB_FETCH_CACHE_TTL > 0


class TestCacheKey:
    def test_deterministic(self) -> None:
        k1 = _content_cache_key("https://example.com", "auto")
        k2 = _content_cache_key("https://example.com", "auto")
        assert k1 == k2

    def test_differs_by_url(self) -> None:
        k1 = _content_cache_key("https://a.com", "auto")
        k2 = _content_cache_key("https://b.com", "auto")
        assert k1 != k2

    def test_differs_by_mode(self) -> None:
        k1 = _content_cache_key("https://example.com", "auto")
        k2 = _content_cache_key("https://example.com", "playwright")
        assert k1 != k2

    def test_prefix(self) -> None:
        key = _content_cache_key("https://example.com", "fast")
        assert key.startswith("web_fetch:content:")


class TestGetCachedResult:
    @pytest.mark.asyncio
    async def test_miss_returns_none(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        result = await get_cached_result("https://example.com", "auto", redis)
        assert result is None

    @pytest.mark.asyncio
    async def test_hit_returns_dict(self) -> None:
        payload = {"url": "https://example.com", "success": True, "markdown": "# Hello"}
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
        result = await get_cached_result("https://example.com", "auto", redis)
        assert result is not None
        assert result["success"] is True
        assert result["markdown"] == "# Hello"

    @pytest.mark.asyncio
    async def test_none_redis_returns_none(self) -> None:
        result = await get_cached_result("https://example.com", "auto", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_redis_exception_returns_none(self) -> None:
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=Exception("connection lost"))
        result = await get_cached_result("https://example.com", "auto", redis)
        assert result is None


class TestSetCachedResult:
    @pytest.mark.asyncio
    async def test_stores_with_ttl(self) -> None:
        redis = AsyncMock()
        redis.setex = AsyncMock()
        payload = {"url": "https://example.com", "success": True, "markdown": "text"}
        await set_cached_result("https://example.com", "auto", payload, redis)
        redis.setex.assert_called_once()
        call_args = redis.setex.call_args[0]
        assert call_args[1] == _WEB_FETCH_CACHE_TTL

    @pytest.mark.asyncio
    async def test_none_redis_is_noop(self) -> None:
        # Should not raise
        await set_cached_result("https://example.com", "auto", {"url": "x"}, None)

    @pytest.mark.asyncio
    async def test_redis_exception_swallowed(self) -> None:
        redis = AsyncMock()
        redis.setex = AsyncMock(side_effect=Exception("connection lost"))
        # Should not raise
        await set_cached_result("https://example.com", "auto", {"url": "x"}, redis)


class TestMaxBytesResolver:
    def test_default_max_bytes(self) -> None:
        from web_fetch.cache import _DEFAULT_MAX_BYTES, _resolve_max_bytes

        with patch.dict(os.environ, {}, clear=False):
            env = {k: v for k, v in os.environ.items() if k != "AUTOBOT_WEB_FETCH_MAX_BYTES"}
            with patch.dict(os.environ, env, clear=True):
                result = _resolve_max_bytes()
        assert result == _DEFAULT_MAX_BYTES

    def test_env_override(self) -> None:
        from web_fetch.cache import _resolve_max_bytes

        with patch.dict(os.environ, {"AUTOBOT_WEB_FETCH_MAX_BYTES": "5242880"}):
            result = _resolve_max_bytes()
        assert result == 5242880

    def test_invalid_falls_back(self) -> None:
        from web_fetch.cache import _DEFAULT_MAX_BYTES, _resolve_max_bytes

        with patch.dict(os.environ, {"AUTOBOT_WEB_FETCH_MAX_BYTES": "nope"}):
            result = _resolve_max_bytes()
        assert result == _DEFAULT_MAX_BYTES


class TestGetCachedResultStringValue:
    @pytest.mark.asyncio
    async def test_string_value_decoded(self) -> None:
        import json

        payload = {"url": "https://example.com", "success": True, "markdown": "# Test"}
        redis = AsyncMock()
        # Return string (not bytes) to exercise the non-bytes decode path
        redis.get = AsyncMock(return_value=json.dumps(payload))
        result = await get_cached_result("https://example.com", "auto", redis)
        assert result is not None
        assert result["markdown"] == "# Test"


class TestCacheRoundTrip:
    @pytest.mark.asyncio
    async def test_set_then_get(self) -> None:
        store: dict = {}

        async def mock_setex(key, ttl, value):
            store[key] = value

        async def mock_get(key):
            return store.get(key)

        redis = AsyncMock()
        redis.setex = mock_setex
        redis.get = mock_get

        payload = {"url": "https://example.com", "success": True, "markdown": "content"}
        await set_cached_result("https://example.com", "auto", payload, redis)
        result = await get_cached_result("https://example.com", "auto", redis)
        assert result is not None
        assert result["markdown"] == "content"
