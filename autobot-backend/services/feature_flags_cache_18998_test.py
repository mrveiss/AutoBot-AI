# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The enforcement posture is cached for the TTL and invalidated by a local write (#18998).

Redis calls are counted on a fake client; time moves through the
``services.feature_flags_cache._monotonic`` seam, never a sleep.
"""

from unittest.mock import patch

import pytest

from services import feature_flags as ff
from services.feature_flags import ENFORCEMENT_MODE_KEY, EnforcementMode, EnforcementModeUnavailable, FeatureFlags
from testkit.fake_redis_pipeline import FakeAsyncPipeline

ENDPOINT = "/api/chat/{session_id}"
ENDPOINT_KEY = f"feature_flag:access_control:endpoint:{ENDPOINT}"


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.gets = 0
        self.fail = False

    async def get(self, key):
        self.gets += 1
        if self.fail:
            raise ConnectionError("down")
        return self.store.get(key)

    async def set(self, key, value, nx=False):
        self.store[key] = value
        return True

    async def lpush(self, *args):
        return 1

    async def ltrim(self, *args):
        return True

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    def pipeline(self, transaction=True):
        return FakeAsyncPipeline(self, transaction=transaction)


@pytest.fixture
def env():
    redis, clock = _FakeRedis(), [100.0]
    flags = FeatureFlags()

    async def _get_redis():
        return redis

    flags._get_redis = _get_redis
    with patch("services.feature_flags_cache._monotonic", lambda: clock[0]):
        yield flags, redis, clock


@pytest.mark.asyncio
async def test_mode_is_cached_within_the_ttl_and_refetched_after(env):
    """Reverting ``_cache_store`` in ``get_enforcement_mode`` makes the middle count 2;
    reverting the ``< self._cache_ttl`` bound in ``_cache_lookup`` keeps the last at 1."""
    flags, redis, clock = env
    redis.store[ENFORCEMENT_MODE_KEY] = "enforced"
    assert await flags.get_enforcement_mode() is EnforcementMode.ENFORCED
    assert await flags.get_enforcement_mode() is EnforcementMode.ENFORCED
    assert redis.gets == 1
    clock[0] += flags._cache_ttl + 1
    await flags.get_enforcement_mode()
    assert redis.gets == 2


@pytest.mark.asyncio
async def test_a_local_set_is_visible_at_once(env):
    """Reverting the ``finally: _cache_invalidate`` in ``set_enforcement_mode`` returns the stale mode."""
    flags, redis, _ = env
    redis.store[ENFORCEMENT_MODE_KEY] = "log_only"
    assert await flags.get_enforcement_mode() is EnforcementMode.LOG_ONLY
    assert await flags.set_enforcement_mode(EnforcementMode.ENFORCED) is True
    assert await flags.get_enforcement_mode() is EnforcementMode.ENFORCED


@pytest.mark.asyncio
async def test_a_failed_read_is_not_cached(env):
    """Reverting 'store only after the fetch succeeded' would remember a failure as a mode."""
    flags, redis, _ = env
    redis.fail = True
    with pytest.raises(EnforcementModeUnavailable):
        await flags.get_enforcement_mode()
    redis.fail = False
    redis.store[ENFORCEMENT_MODE_KEY] = "enforced"
    assert await flags.get_enforcement_mode() is EnforcementMode.ENFORCED


@pytest.mark.asyncio
async def test_endpoint_override_is_cached_including_none_and_set_invalidates(env):
    """Reverting ``_cache_store`` in ``get_endpoint_enforcement`` makes the first count 2;
    reverting the ``finally`` in ``set_endpoint_enforcement`` returns the stale None."""
    flags, redis, _ = env
    assert await flags.get_endpoint_enforcement(ENDPOINT) is None
    assert await flags.get_endpoint_enforcement(ENDPOINT) is None
    assert redis.gets == 1
    assert await flags.set_endpoint_enforcement(ENDPOINT, EnforcementMode.ENFORCED) is True
    assert await flags.get_endpoint_enforcement(ENDPOINT) is EnforcementMode.ENFORCED


@pytest.mark.asyncio
async def test_endpoint_override_refetched_after_ttl(env):
    flags, redis, clock = env
    await flags.get_endpoint_enforcement(ENDPOINT)
    clock[0] += flags._cache_ttl + 1
    redis.store[ENDPOINT_KEY] = "enforced"
    assert await flags.get_endpoint_enforcement(ENDPOINT) is EnforcementMode.ENFORCED
    assert redis.gets == 2


@pytest.mark.asyncio
async def test_get_feature_flags_fast_path_never_takes_the_lock():
    """Reverting the early ``return flags`` makes the held lock block this call forever (timeout)."""
    import asyncio

    ff._feature_flags = None
    first = await ff.get_feature_flags()
    async with ff._flags_lock:
        second = await asyncio.wait_for(ff.get_feature_flags(), timeout=1)
    assert second is first
    ff._feature_flags = None


@pytest.mark.asyncio
async def test_expired_entries_are_pruned_so_a_full_cache_accepts_a_new_key(env):
    """Reverting ``_prune_expired`` in ``_cache_store`` leaves the cache full of dead stamps, so the
    new key is refused forever and this reads Redis twice."""
    from services.feature_flags_cache import MAX_CACHED_KEYS

    flags, redis, clock = env
    for i in range(MAX_CACHED_KEYS):
        flags._cache_store(f"k{i}", i)
    clock[0] += flags._cache_ttl + 1
    flags._cache_store("new", "v")
    assert flags._cache_lookup("new") == (True, "v")
    assert len(flags._cache) == 1


@pytest.mark.asyncio
async def test_a_full_cache_of_live_entries_still_refuses_a_new_key(env):
    """Contrast: pruning only drops EXPIRED entries; live ones are never evicted."""
    from services.feature_flags_cache import MAX_CACHED_KEYS

    flags, _, _ = env
    for i in range(MAX_CACHED_KEYS):
        flags._cache_store(f"k{i}", i)
    flags._cache_store("new", "v")
    assert flags._cache_lookup("new") == (False, None)
    assert len(flags._cache) == MAX_CACHED_KEYS
