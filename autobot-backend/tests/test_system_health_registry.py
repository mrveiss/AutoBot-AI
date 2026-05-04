# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Issue #3333: registry behavior for the canonical health-probe aggregator."""

import asyncio

import pytest

from api.system_health import (
    ComponentHealth,
    _PROBE_TIMEOUT_S,
    _reset_probes_for_testing,
    collect_system_health,
    list_registered_probes,
    register_health_probe,
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    _reset_probes_for_testing()
    yield
    _reset_probes_for_testing()


def test_register_and_list_probes_returns_sorted_names():
    @register_health_probe("zeta")
    async def _probe_zeta(_request=None):
        return ComponentHealth(name="zeta", status="ok")

    @register_health_probe("alpha")
    async def _probe_alpha(_request=None):
        return ComponentHealth(name="alpha", status="ok")

    assert list_registered_probes() == ["alpha", "zeta"]


def test_collect_with_no_probes_returns_ok_and_empty_components():
    result = asyncio.run(collect_system_health())
    assert result.status == "ok"
    assert result.components == []
    assert result.timestamp is not None


def test_aggregated_status_is_worst_of_components():
    @register_health_probe("a")
    async def _probe_a(_request=None):
        return ComponentHealth(name="a", status="ok")

    @register_health_probe("b")
    async def _probe_b(_request=None):
        return ComponentHealth(name="b", status="degraded")

    @register_health_probe("c")
    async def _probe_c(_request=None):
        return ComponentHealth(name="c", status="ok")

    result = asyncio.run(collect_system_health())
    assert result.status == "degraded"

    @register_health_probe("d")
    async def _probe_d(_request=None):
        return ComponentHealth(name="d", status="down")

    result = asyncio.run(collect_system_health())
    assert result.status == "down"


def test_probe_that_raises_is_recorded_as_down_not_propagated():
    @register_health_probe("raiser")
    async def _probe_raiser(_request=None):
        raise RuntimeError("boom")

    result = asyncio.run(collect_system_health())
    assert result.status == "down"
    assert len(result.components) == 1
    component = result.components[0]
    assert component.name == "raiser"
    assert component.status == "down"
    assert "RuntimeError" in (component.detail or "")
    assert component.latency_ms is not None


def test_slow_probe_is_timed_out_as_down():
    @register_health_probe("slow")
    async def _probe_slow(_request=None):
        await asyncio.sleep(_PROBE_TIMEOUT_S + 1.0)
        return ComponentHealth(name="slow", status="ok")

    result = asyncio.run(collect_system_health())
    component = result.components[0]
    assert component.status == "down"
    assert "timed out" in (component.detail or "")


def test_latency_is_filled_in_when_probe_does_not_set_it():
    @register_health_probe("auto_latency")
    async def _probe(_request=None):
        return ComponentHealth(name="auto_latency", status="ok")

    result = asyncio.run(collect_system_health())
    component = result.components[0]
    assert component.latency_ms is not None
    assert component.latency_ms >= 0


def test_re_registering_overwrites_and_keeps_one_entry():
    @register_health_probe("dup")
    async def _probe_v1(_request=None):
        return ComponentHealth(name="dup", status="ok", detail="v1")

    @register_health_probe("dup")
    async def _probe_v2(_request=None):
        return ComponentHealth(name="dup", status="ok", detail="v2")

    assert list_registered_probes() == ["dup"]
    result = asyncio.run(collect_system_health())
    assert len(result.components) == 1
    assert result.components[0].detail == "v2"


def test_probes_run_concurrently_not_serially():
    sleeps = [0.5, 0.5, 0.5]

    for index, duration in enumerate(sleeps):
        @register_health_probe(f"sleeper_{index}")
        async def _probe(_request=None, _d=duration, _i=index):
            await asyncio.sleep(_d)
            return ComponentHealth(name=f"sleeper_{_i}", status="ok")

    import time
    started = time.perf_counter()
    asyncio.run(collect_system_health())
    elapsed = time.perf_counter() - started
    # Serial would be sum(sleeps) == 1.5s. Concurrent should be ~0.5s. Allow
    # generous slack for CI noise but reject the serial outcome.
    assert elapsed < 1.0, f"probes ran serially: elapsed={elapsed:.2f}s"
