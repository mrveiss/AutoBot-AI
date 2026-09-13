# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ServiceAuthManager's key generation and storage are two separate steps
(#16348): ``generate_key_material`` is pure (no Redis I/O) and
``store_service_key`` is the only method that writes to Redis.
``generate_service_key`` keeps composing the two, unchanged, for its other
callers (export_service_keys.py, verify-service-auth.py).

The split exists so a caller that must not put a key in Redis before an
export of it is durable on disk
(autobot-infrastructure/shared/scripts/generate_service_keys.py) can
generate in memory first and store only once the export write has
succeeded and been fsynced.
"""

from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional, Tuple

from constants.ttl_constants import TTL_90_DAYS
from security.service_auth import ServiceAuthManager


class _FakeAsyncRedis:
    """Minimal in-memory async Redis stand-in that records every set() call."""

    def __init__(self) -> None:
        self.store: Dict[str, Any] = {}
        self.set_calls: List[Tuple[str, Any, Optional[int]]] = []

    async def set(self, key, value, ex=None):
        self.store[key] = value
        self.set_calls.append((key, value, ex))

    async def get(self, key):
        return self.store.get(key)


def test_generate_key_material_is_pure_and_hex_encoded():
    """redis_client=None must not raise: generate_key_material touches no I/O."""
    manager = ServiceAuthManager(redis_client=None)

    key = manager.generate_key_material()

    assert len(key) == 64  # 256 bits, hex-encoded
    assert all(c in "0123456789abcdef" for c in key)


def test_generate_key_material_returns_distinct_keys():
    manager = ServiceAuthManager(redis_client=None)

    assert manager.generate_key_material() != manager.generate_key_material()


async def test_store_service_key_writes_with_the_90_day_ttl():
    fake_redis = _FakeAsyncRedis()
    manager = ServiceAuthManager(redis_client=fake_redis)
    generated = secrets.token_hex(32)

    await manager.store_service_key("main-backend", generated)

    assert fake_redis.store["service:key:main-backend"] == generated
    assert fake_redis.set_calls == [("service:key:main-backend", generated, TTL_90_DAYS)]


async def test_generate_service_key_still_generates_and_stores_for_other_callers():
    """Back-compat: export_service_keys.py and verify-service-auth.py still
    get a key that is both generated and already live in Redis (#16348)."""
    fake_redis = _FakeAsyncRedis()
    manager = ServiceAuthManager(redis_client=fake_redis)

    key = await manager.generate_service_key("npu-worker")

    assert fake_redis.store["service:key:npu-worker"] == key
    assert len(key) == 64
