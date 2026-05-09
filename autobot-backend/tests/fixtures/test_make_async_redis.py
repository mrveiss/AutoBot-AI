# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Contract tests for ``tests.fixtures.mocks.make_async_redis`` and
``patch_async_redis`` (#7264).

Pins the canonical async-redis fixture's behavior so the 11+ ad-hoc
``_make_redis*()`` helpers across the test tree can migrate onto it
with confidence.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from tests.fixtures import make_async_redis, patch_async_redis


# ---------------------------------------------------------------------------
# make_async_redis — defaults + override + extras
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_get_returns_none() -> None:
    """Empty/healthy default — production reads of unset keys see None."""
    redis = make_async_redis()
    assert await redis.get("anything") is None


@pytest.mark.asyncio
async def test_default_set_setex_expire_succeed() -> None:
    """Write defaults assume success — most callers don't gate on the
    return value, but those that do expect truthy on success."""
    redis = make_async_redis()
    assert await redis.set("k", "v") is True
    assert await redis.setex("k", 60, "v") is True
    assert await redis.expire("k", 60) is True


@pytest.mark.asyncio
async def test_default_sadd_srem_return_one() -> None:
    """1 = one element added/removed — matches what redis-py returns."""
    redis = make_async_redis()
    assert await redis.sadd("set", "x") == 1
    assert await redis.srem("set", "x") == 1


@pytest.mark.asyncio
async def test_default_smembers_returns_empty_set() -> None:
    redis = make_async_redis()
    assert await redis.smembers("set") == set()


@pytest.mark.asyncio
async def test_default_sismember_returns_false() -> None:
    redis = make_async_redis()
    assert await redis.sismember("set", "x") is False


@pytest.mark.asyncio
async def test_default_hash_ops_empty() -> None:
    redis = make_async_redis()
    assert await redis.hget("h", "k") is None
    assert await redis.hgetall("h") == {}
    assert await redis.hkeys("h") == []
    assert await redis.hvals("h") == []
    assert await redis.hexists("h", "k") == 0


@pytest.mark.asyncio
async def test_default_list_ops_empty() -> None:
    redis = make_async_redis()
    assert await redis.lrange("list", 0, -1) == []
    assert await redis.llen("list") == 0


@pytest.mark.asyncio
async def test_default_sorted_set_ops_empty() -> None:
    redis = make_async_redis()
    assert await redis.zrange("z", 0, -1) == []
    assert await redis.zrangebyscore("z", 0, 100) == []
    assert await redis.zrevrange("z", 0, -1) == []
    assert await redis.zcard("z") == 0


# ---------------------------------------------------------------------------
# Per-method overrides
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_override() -> None:
    redis = make_async_redis(get_returns=b"hello")
    assert await redis.get("any-key") == b"hello"


@pytest.mark.asyncio
async def test_smembers_returns_override() -> None:
    redis = make_async_redis(smembers_returns={b"a", b"b"})
    assert await redis.smembers("any-set") == {b"a", b"b"}


@pytest.mark.asyncio
async def test_zrange_returns_override() -> None:
    redis = make_async_redis(zrange_returns=[b"first", b"second"])
    assert await redis.zrange("z", 0, -1) == [b"first", b"second"]


# ---------------------------------------------------------------------------
# extra_methods — arbitrary additions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extra_methods_become_async_mocks() -> None:
    """Methods not in the predefined set (e.g. xadd for streams) can be
    passed via kwargs and become ``AsyncMock(return_value=value)``."""
    redis = make_async_redis(xadd=b"1-0", scan_iter=[b"k1", b"k2"])
    assert await redis.xadd("stream", {"f": "v"}) == b"1-0"
    assert await redis.scan_iter() == [b"k1", b"k2"]


@pytest.mark.asyncio
async def test_extra_method_takes_precedence_over_default() -> None:
    """If a caller passes ``get`` via extras (unusual), it overrides the
    typed parameter. This is a niche case but worth documenting."""
    redis = make_async_redis(get_returns=b"default", **{"get": b"override"})
    # **extras runs after the typed args, so it wins.
    assert await redis.get("k") == b"override"


# ---------------------------------------------------------------------------
# patch_async_redis — context manager
# ---------------------------------------------------------------------------


# Simulate production code that imports + awaits get_async_redis_client.
async def _fake_production_function():
    """Replicates the production pattern: ``await get_async_redis_client(...)``"""
    from autobot_shared.redis_client import get_async_redis_client

    redis = await get_async_redis_client(database="main")
    return await redis.get("test-key")


@pytest.mark.asyncio
async def test_patch_async_redis_basic_use() -> None:
    """The patched callable returns the mock when awaited — the #7216
    bug class (``patch(..., return_value=mock)`` returns default
    AsyncMock when awaited) cannot recur with this helper."""
    with patch_async_redis(
        "autobot_shared.redis_client.get_async_redis_client"
    ) as redis:
        redis.get = AsyncMock(return_value=b"hit")
        result = await _fake_production_function()
        assert result == b"hit"


@pytest.mark.asyncio
async def test_patch_async_redis_with_preconfigured() -> None:
    """Passing a pre-configured redis lets callers set up state
    declaratively and reuse the same mock across multiple patches."""
    redis = make_async_redis(get_returns=b"shared")
    with patch_async_redis(
        "autobot_shared.redis_client.get_async_redis_client", redis=redis
    ):
        assert await _fake_production_function() == b"shared"


@pytest.mark.asyncio
async def test_patch_async_redis_returns_async_callable() -> None:
    """Regression pin for #7216 — the patched object MUST be itself
    awaitable so production's ``await get_async_redis_client(...)`` returns
    the redis mock (NOT the default AsyncMock that bare ``return_value=``
    would have given).
    """
    from autobot_shared.redis_client import get_async_redis_client as orig

    with patch_async_redis(
        "autobot_shared.redis_client.get_async_redis_client"
    ) as redis:
        # The patched function is now an AsyncMock; awaiting it returns redis.
        from autobot_shared.redis_client import get_async_redis_client
        awaited = await get_async_redis_client(database="main")
        assert awaited is redis  # ← THE pin: not just truthy, the same object


def test_factory_re_exported_from_fixtures_package() -> None:
    """Documented import path: ``from tests.fixtures import make_async_redis``."""
    import tests.fixtures as fixtures

    assert "make_async_redis" in fixtures.__all__
    assert "patch_async_redis" in fixtures.__all__
    assert callable(fixtures.make_async_redis)
    assert callable(fixtures.patch_async_redis)
