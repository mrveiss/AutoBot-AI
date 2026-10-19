# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ResourceMonitor reads the CANONICAL Redis breaker, not a process-local one (#18553).

The old reader asked ``utils.redis_immediate_connection.redis_circuit_breaker``,
which nothing ever fed, so ``redis_available`` was always True. The fake below
is the canonical ``get_redis_health()`` payload shape.
"""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import patch

from autobot_shared.redis_management.connection_manager import RedisConnectionManager
from utils.async_cancellation import ResourceMonitor


def _with_manager(factory):
    """Patch the REAL redis_client's manager getter (the conftest stand-in delegates to it)."""
    from autobot_shared import redis_client as stand_in

    return patch.dict(stand_in.is_redis_circuit_open.__globals__, {"_get_connection_manager": factory})


def _manager(open_: bool, age_s: float) -> RedisConnectionManager:
    m = object.__new__(RedisConnectionManager)
    m._config_broken = set()
    m._circuit_open = {"main": open_}
    m._failure_counts = {"main": 5}
    m._last_failure_times = {"main": time.time() - age_s}
    m._pool_config = SimpleNamespace(circuit_breaker_timeout=60)
    return m


def _redis_available(manager) -> bool:
    with _with_manager(lambda: manager):
        return asyncio.run(ResourceMonitor().check_resources())["redis"]


def test_open_breaker_before_timeout_means_redis_unavailable():
    assert _redis_available(_manager(True, age_s=1)) is False


def test_open_breaker_past_timeout_with_no_traffic_means_available():
    m = _manager(True, age_s=120)
    assert _redis_available(m) is True
    assert m._circuit_open["main"] is True  # the read has no side effects


def test_closed_breaker_means_redis_available():
    assert _redis_available(_manager(False, age_s=1)) is True


def test_other_database_breaker_does_not_flip_main():
    m = _manager(False, age_s=1)
    m._circuit_open["knowledge"] = True
    assert _redis_available(m) is True


def test_unreadable_manager_keeps_the_prior_unavailable_fallback():
    def _down():
        raise RuntimeError("manager down")

    with _with_manager(_down):
        assert asyncio.run(ResourceMonitor().check_resources())["redis"] is False
