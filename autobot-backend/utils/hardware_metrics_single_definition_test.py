# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One definition of the performance metrics dataclasses and monitor_performance (#18450)."""

import pytest

from utils import hardware_metrics
from utils.performance_monitoring import decorator, metrics

_NAMES = ("GPUMetrics", "NPUMetrics", "MultiModalMetrics", "SystemPerformanceMetrics", "ServicePerformanceMetrics")


@pytest.mark.parametrize("name", _NAMES)
def test_hardware_metrics_serves_the_canonical_dataclass(name):
    assert getattr(hardware_metrics, name) is getattr(metrics, name)


def test_monitor_performance_is_the_canonical_decorator():
    assert hardware_metrics.monitor_performance is decorator.monitor_performance


class _FakeRedis:
    def __init__(self):
        self.keys = []

    def zadd(self, key, mapping):
        self.keys.append(key)

    def expire(self, key, ttl):
        pass


def _decorated(provider, category):
    @decorator.monitor_performance(category, client_provider=provider)
    async def work():
        return 1

    return work


@pytest.mark.asyncio
async def test_two_monitors_write_to_their_own_redis_client():
    hw_db, perf_db = _FakeRedis(), _FakeRedis()
    hw = _decorated(lambda: hw_db, "hardware")
    perf = _decorated(lambda: perf_db, "perf")
    await hw()
    await perf()
    assert hw_db.keys == ["function_performance:hardware:work"]
    assert perf_db.keys == ["function_performance:perf:work"]


@pytest.mark.asyncio
async def test_no_provider_or_missing_client_stores_nothing():
    none_db = _FakeRedis()
    await _decorated(None, "x")()
    await _decorated(lambda: None, "x")()
    assert none_db.keys == []


def test_decorator_keeps_no_module_level_client():
    assert not hasattr(decorator, "_redis_client")
    assert not hasattr(decorator, "set_redis_client")
