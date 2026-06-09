# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Contract tests for ``tests.fixtures.mocks.make_async_redis`` and
``patch_async_redis`` (#7264).

Pins the canonical async-redis fixture's behavior so the 11+ ad-hoc
``_make_redis*()`` helpers across the test tree can migrate onto it
with confidence.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

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
    with patch_async_redis("autobot_shared.redis_client.get_async_redis_client") as redis:
        redis.get = AsyncMock(return_value=b"hit")
        result = await _fake_production_function()
        assert result == b"hit"


@pytest.mark.asyncio
async def test_patch_async_redis_with_preconfigured() -> None:
    """Passing a pre-configured redis lets callers set up state
    declaratively and reuse the same mock across multiple patches."""
    redis = make_async_redis(get_returns=b"shared")
    with patch_async_redis("autobot_shared.redis_client.get_async_redis_client", redis=redis):
        assert await _fake_production_function() == b"shared"


@pytest.mark.asyncio
async def test_patch_async_redis_returns_async_callable() -> None:
    """Regression pin for #7216 — the patched object MUST be itself
    awaitable so production's ``await get_async_redis_client(...)`` returns
    the redis mock (NOT the default AsyncMock that bare ``return_value=``
    would have given).
    """

    with patch_async_redis("autobot_shared.redis_client.get_async_redis_client") as redis:
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


# ---------------------------------------------------------------------------
# make_redis_pipeline + pipeline= kwarg (#7339)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_async_context_manager_pattern() -> None:
    """``async with redis.pipeline() as pipe: ... await pipe.execute()`` —
    the most common pipeline usage in production async-redis code."""
    from tests.fixtures import make_redis_pipeline

    pipe = make_redis_pipeline(execute_returns=[1, 1, 1])
    redis = make_async_redis(pipeline=pipe)

    # Production code shape: redis.pipeline() is SYNC, returns a context manager.
    p = redis.pipeline()
    assert p is pipe  # not an awaitable — sync call

    async with p as inner:
        assert inner is pipe  # __aenter__ returns the pipe itself
        # Buffered ops — pipe.X(...) is a coroutine; in real redis-py these
        # don't need await but AsyncMock auto-awaits via the parent's child-
        # spawning behavior. Both shapes (await/no-await) work for tests.
        await inner.xadd("stream", {"k": "v"})
        result = await inner.execute()

    assert result == [1, 1, 1]


@pytest.mark.asyncio
async def test_pipeline_direct_caller_pattern() -> None:
    """``pipe = redis.pipeline(); pipe.X(...); await pipe.execute()`` —
    no async-with, just direct call + await on execute."""
    from tests.fixtures import make_redis_pipeline

    pipe = make_redis_pipeline(execute_returns=["xadd-id-1", 1])
    redis = make_async_redis(pipeline=pipe)

    p = redis.pipeline()
    await p.xadd("rag:stream", {"data": "x"})
    await p.hset("rag:meta:1", mapping={"k": "v"})
    result = await p.execute()

    assert result == ["xadd-id-1", 1]


@pytest.mark.asyncio
async def test_pipeline_execute_default_empty_list() -> None:
    """Default ``execute_returns=None`` → empty list (matches the
    "no buffered writes / nothing to report" common case)."""
    from tests.fixtures import make_redis_pipeline

    pipe = make_redis_pipeline()
    redis = make_async_redis(pipeline=pipe)

    result = await redis.pipeline().execute()
    assert result == []


@pytest.mark.asyncio
async def test_redis_without_pipeline_kwarg_has_default_async_pipeline() -> None:
    """When no ``pipeline=`` is passed, ``redis.pipeline`` is the default
    AsyncMock-spawned attribute. Production that doesn't use pipeline
    won't trip; production that does use it gets a no-op AsyncMock that
    won't error on access patterns."""
    redis = make_async_redis()
    # No assertion that pipeline is callable — just that accessing it
    # doesn't raise. Real pipeline usage requires the explicit kwarg.
    assert redis.pipeline is not None


def test_make_redis_pipeline_re_exported() -> None:
    """Documented import path: ``from tests.fixtures import make_redis_pipeline``."""
    import tests.fixtures as fixtures

    assert "make_redis_pipeline" in fixtures.__all__
    assert callable(fixtures.make_redis_pipeline)


# ---------------------------------------------------------------------------
# scan_iter_keys (#7339)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_iter_yields_provided_keys() -> None:
    """``scan_iter_keys=[…]`` attaches a real async-generator returning
    those keys. Production: ``async for key in redis.scan_iter(match=…): ...``."""
    redis = make_async_redis(scan_iter_keys=[b"key:1", b"key:2", b"key:3"])

    collected = []
    async for k in redis.scan_iter(match="key:*"):
        collected.append(k)

    assert collected == [b"key:1", b"key:2", b"key:3"]


@pytest.mark.asyncio
async def test_scan_iter_accepts_arbitrary_kwargs() -> None:
    """Real ``redis.scan_iter`` takes ``match=``, ``count=``, ``_type=``.
    The fixture must accept any kwargs without TypeError."""
    redis = make_async_redis(scan_iter_keys=[b"a"])

    # Production may call with various kwarg combinations.
    async for _ in redis.scan_iter(match="a:*", count=100, _type="string"):
        pass


@pytest.mark.asyncio
async def test_scan_iter_empty_list_yields_nothing() -> None:
    """``scan_iter_keys=[]`` → empty stream (the no-keys-match case)."""
    redis = make_async_redis(scan_iter_keys=[])

    collected = []
    async for k in redis.scan_iter():
        collected.append(k)
    assert collected == []


@pytest.mark.asyncio
async def test_scan_iter_snapshot_is_independent_of_caller_mutation() -> None:
    """Mutating the input list after fixture creation must NOT affect the
    yielded keys — the fixture takes a snapshot."""
    keys = [b"a", b"b"]
    redis = make_async_redis(scan_iter_keys=keys)

    keys.append(b"c")  # mutate after fixture creation
    keys.clear()  # then clear

    collected = []
    async for k in redis.scan_iter():
        collected.append(k)
    assert collected == [b"a", b"b"]  # original snapshot, not mutated list
