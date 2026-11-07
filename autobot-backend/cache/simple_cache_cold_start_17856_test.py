# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cold-start cache stats stay "enabled" on the advanced manager (#17856).

The retired `utils.cache_manager.CacheManager.get_stats` awaited `_ensure_redis_client()` first, so
`GET /cache/stats` on a freshly started process reported the real key count. `SimpleCacheManager`
had a no-op `_ensure_redis_client`, which would have reported `disabled` until something else
initialised the client.
"""

import pytest

from utils.advanced_cache_manager import SimpleCacheManager


class _FakeRedis:
    async def info(self, section=None):
        return {"used_memory_human": "1M"}

    async def scan_iter(self, match=None):  # pragma: no cover - replaced below
        raise NotImplementedError


class _Advanced:
    """Stand-in whose client only exists after `_ensure_redis_client` runs."""

    def __init__(self):
        self.redis_client = None
        self.ensured = 0

    async def _ensure_redis_client(self):
        self.ensured += 1
        client = _FakeRedis()

        async def _scan(match=None):
            for key in ("cache:a", "cache:b"):
                yield key

        client.scan_iter = _scan
        self.redis_client = client


@pytest.mark.asyncio
async def test_get_stats_initialises_the_client_before_reading() -> None:
    mgr = SimpleCacheManager()
    mgr._cache = _Advanced()
    stats = await mgr.get_stats()
    assert stats == {"status": "enabled", "total_keys": 2, "memory_usage": "1M", "default_ttl": mgr.default_ttl}
    assert mgr._cache.ensured == 1


@pytest.mark.asyncio
async def test_ensure_redis_client_delegates_to_the_advanced_manager() -> None:
    mgr = SimpleCacheManager()
    mgr._cache = _Advanced()
    await mgr._ensure_redis_client()
    assert mgr._redis_client is mgr._cache.redis_client is not None
