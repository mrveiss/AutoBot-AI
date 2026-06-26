# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for services/oidc_token_cache.py — D1 (#10158).

Covers:
- cache miss returns None
- cache hit returns stored claims
- cache expires / is invalidated
- TTL=0 disables caching (returns None always)
- Redis unavailable → silently returns None (no crash)
- invalidate_token_cache deletes the key
- cache_key is derived from token hash (not raw token)
"""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).parent.parent.parent
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ROOT))

# Stub heavy deps that may be pulled in transitively
for _m in ["sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"]:
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()

# ---------------------------------------------------------------------------
# Load module under test
# ---------------------------------------------------------------------------
_CACHE_PY = _BACKEND / "services" / "oidc_token_cache.py"
_spec = importlib.util.spec_from_file_location("_oidc_token_cache", _CACHE_PY)
_cache_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_cache_mod)  # type: ignore[union-attr]

get_cached_claims = _cache_mod.get_cached_claims
cache_claims = _cache_mod.cache_claims
invalidate_token_cache = _cache_mod.invalidate_token_cache
_cache_key = _cache_mod._cache_key
OIDC_TOKEN_CACHE_TTL = _cache_mod.OIDC_TOKEN_CACHE_TTL

_SAMPLE_TOKEN = "eyJhbGciOiJSUzI1NiJ9.test-token-payload.signature"
_SAMPLE_CLAIMS = {"sub": "alice", "role": "admin", "authority_token": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock(get_return=None) -> AsyncMock:
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=get_return)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    return mock


# ---------------------------------------------------------------------------
# cache key
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_key_has_prefix(self):
        key = _cache_key(_SAMPLE_TOKEN)
        assert key.startswith("slm:oidc:token_cache:")

    def test_key_is_deterministic(self):
        assert _cache_key(_SAMPLE_TOKEN) == _cache_key(_SAMPLE_TOKEN)

    def test_different_tokens_different_keys(self):
        key_a = _cache_key("token-a")
        key_b = _cache_key("token-b")
        assert key_a != key_b

    def test_key_does_not_contain_raw_token(self):
        # Raw token must NOT appear in the key (no secret-material leakage)
        key = _cache_key(_SAMPLE_TOKEN)
        assert _SAMPLE_TOKEN not in key


# ---------------------------------------------------------------------------
# get_cached_claims — cache miss
# ---------------------------------------------------------------------------


class TestGetCachedClaimsMiss:
    @pytest.mark.asyncio
    async def test_miss_returns_none(self):
        redis_mock = _make_redis_mock(get_return=None)
        with patch.object(_cache_mod, "get_async_redis_client", AsyncMock(return_value=redis_mock)):
            result = await get_cached_claims(_SAMPLE_TOKEN)
        assert result is None

    @pytest.mark.asyncio
    async def test_redis_unavailable_returns_none(self):
        with patch.object(_cache_mod, "get_async_redis_client", AsyncMock(return_value=None)):
            result = await get_cached_claims(_SAMPLE_TOKEN)
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_zero_always_returns_none(self):
        # Patch module-level TTL to 0 (caching disabled)
        with patch.object(_cache_mod, "OIDC_TOKEN_CACHE_TTL", 0):
            result = await get_cached_claims(_SAMPLE_TOKEN)
        assert result is None


# ---------------------------------------------------------------------------
# get_cached_claims — cache hit
# ---------------------------------------------------------------------------


class TestGetCachedClaimsHit:
    @pytest.mark.asyncio
    async def test_hit_returns_claims(self):
        serialized = json.dumps(_SAMPLE_CLAIMS)
        redis_mock = _make_redis_mock(get_return=serialized)
        with patch.object(_cache_mod, "get_async_redis_client", AsyncMock(return_value=redis_mock)):
            result = await get_cached_claims(_SAMPLE_TOKEN)
        assert result == _SAMPLE_CLAIMS

    @pytest.mark.asyncio
    async def test_hit_calls_correct_key(self):
        serialized = json.dumps(_SAMPLE_CLAIMS)
        redis_mock = _make_redis_mock(get_return=serialized)
        with patch.object(_cache_mod, "get_async_redis_client", AsyncMock(return_value=redis_mock)):
            await get_cached_claims(_SAMPLE_TOKEN)
        redis_mock.get.assert_awaited_once_with(_cache_key(_SAMPLE_TOKEN))


# ---------------------------------------------------------------------------
# cache_claims
# ---------------------------------------------------------------------------


class TestCacheClaims:
    @pytest.mark.asyncio
    async def test_stores_serialized_claims_with_ttl(self):
        redis_mock = _make_redis_mock()
        with patch.object(_cache_mod, "get_async_redis_client", AsyncMock(return_value=redis_mock)):
            with patch.object(_cache_mod, "OIDC_TOKEN_CACHE_TTL", 300):
                await cache_claims(_SAMPLE_TOKEN, _SAMPLE_CLAIMS)
        redis_mock.set.assert_awaited_once()
        call_args = redis_mock.set.call_args
        assert call_args[0][0] == _cache_key(_SAMPLE_TOKEN)
        stored = json.loads(call_args[0][1])
        assert stored == _SAMPLE_CLAIMS
        assert call_args[1]["ex"] == 300

    @pytest.mark.asyncio
    async def test_noop_when_ttl_zero(self):
        redis_mock = _make_redis_mock()
        with patch.object(_cache_mod, "get_async_redis_client", AsyncMock(return_value=redis_mock)):
            with patch.object(_cache_mod, "OIDC_TOKEN_CACHE_TTL", 0):
                await cache_claims(_SAMPLE_TOKEN, _SAMPLE_CLAIMS)
        redis_mock.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_noop_when_redis_unavailable(self):
        with patch.object(_cache_mod, "get_async_redis_client", AsyncMock(return_value=None)):
            # Must not raise
            await cache_claims(_SAMPLE_TOKEN, _SAMPLE_CLAIMS)


# ---------------------------------------------------------------------------
# invalidate_token_cache
# ---------------------------------------------------------------------------


class TestInvalidateTokenCache:
    @pytest.mark.asyncio
    async def test_deletes_key(self):
        redis_mock = _make_redis_mock()
        with patch.object(_cache_mod, "get_async_redis_client", AsyncMock(return_value=redis_mock)):
            await invalidate_token_cache(_SAMPLE_TOKEN)
        redis_mock.delete.assert_awaited_once_with(_cache_key(_SAMPLE_TOKEN))

    @pytest.mark.asyncio
    async def test_noop_when_redis_unavailable(self):
        with patch.object(_cache_mod, "get_async_redis_client", AsyncMock(return_value=None)):
            # Must not raise
            await invalidate_token_cache(_SAMPLE_TOKEN)
