# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#7570: Verify chat:recent sorted set is bounded after N insertions.

The sorted set must not grow past _CHAT_RECENT_MAX_ENTRIES regardless of how
many sessions are saved. The trim is done via ZREMRANGEBYRANK immediately after
each ZADD in _update_redis_cache_on_save.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeSortedSet:
    """Minimal in-memory sorted set implementing the Redis subset we use."""

    def __init__(self):
        self._data: dict = {}  # member -> score

    def zadd(self, key, mapping):
        self._data.update(mapping)

    def zremrangebyrank(self, key, start, stop):
        ordered = sorted(self._data.items(), key=lambda kv: kv[1])
        n = len(ordered)
        if n == 0:
            return 0
        # Resolve negative indices (Redis convention)
        if start < 0:
            start = max(0, n + start)
        if stop < 0:
            stop = n + stop
        if start > stop or start >= n:
            return 0
        stop = min(stop, n - 1)
        victims = [m for m, _ in ordered[start : stop + 1]]
        for m in victims:
            del self._data[m]
        return len(victims)

    def zrem(self, key, member):
        self._data.pop(member, None)

    def zcard(self):
        return len(self._data)


@pytest.fixture()
def _fake_set():
    return _FakeSortedSet()


@pytest.fixture(autouse=True)
def _patch_executor():
    """Make run_in_chat_io_executor call the function synchronously in tests."""

    async def _run(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("chat_history.session.run_in_chat_io_executor", side_effect=_run):
        yield


def _make_mixin(fake_set: _FakeSortedSet):
    """Return a bare SessionMixin instance wired to fake_set."""
    from chat_history.session import SessionMixin

    mixin = SessionMixin.__new__(SessionMixin)
    redis = MagicMock()
    redis.zadd.side_effect = lambda key, mapping: fake_set.zadd(key, mapping)
    redis.zremrangebyrank.side_effect = lambda key, start, stop: fake_set.zremrangebyrank(key, start, stop)
    mixin.redis_client = redis
    mixin._async_cache_session = AsyncMock()
    return mixin


@pytest.mark.asyncio
async def test_sorted_set_does_not_exceed_max_entries(_fake_set):
    """Inserting MAX+5 sessions must leave exactly MAX entries in the set."""
    from chat_history.cache import _CHAT_RECENT_MAX_ENTRIES

    mixin = _make_mixin(_fake_set)

    for i in range(_CHAT_RECENT_MAX_ENTRIES + 5):
        await mixin._update_redis_cache_on_save(f"session-{i}", {})

    assert _fake_set.zcard() == _CHAT_RECENT_MAX_ENTRIES


@pytest.mark.asyncio
async def test_sorted_set_below_limit_retains_all_entries(_fake_set):
    """Fewer than MAX inserts must not over-trim — all entries stay."""
    from chat_history.cache import _CHAT_RECENT_MAX_ENTRIES

    insert_count = _CHAT_RECENT_MAX_ENTRIES - 10
    mixin = _make_mixin(_fake_set)

    for i in range(insert_count):
        await mixin._update_redis_cache_on_save(f"session-{i}", {})

    assert _fake_set.zcard() == insert_count


@pytest.mark.asyncio
async def test_sorted_set_exactly_at_limit_is_not_trimmed(_fake_set):
    """Exactly MAX inserts must leave exactly MAX entries (no off-by-one)."""
    from chat_history.cache import _CHAT_RECENT_MAX_ENTRIES

    mixin = _make_mixin(_fake_set)

    for i in range(_CHAT_RECENT_MAX_ENTRIES):
        await mixin._update_redis_cache_on_save(f"session-{i}", {})

    assert _fake_set.zcard() == _CHAT_RECENT_MAX_ENTRIES


@pytest.mark.asyncio
async def test_no_redis_client_skips_zadd_safely():
    """When redis_client is None, _update_redis_cache_on_save must be a no-op."""
    from chat_history.session import SessionMixin

    mixin = SessionMixin.__new__(SessionMixin)
    mixin.redis_client = None

    # Should not raise
    await mixin._update_redis_cache_on_save("session-x", {})
