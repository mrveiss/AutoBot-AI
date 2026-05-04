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
    probe_app_state,
    probe_singleton,
    register_app_state_probe,
    register_health_probe,
    register_singleton_probe,
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


def test_aggregator_status_when_probe_returns_down():
    @register_health_probe("ok_probe")
    async def _probe_ok(_request=None):
        return ComponentHealth(name="ok_probe", status="ok")

    @register_health_probe("dead_probe")
    async def _probe_dead(_request=None):
        return ComponentHealth(name="dead_probe", status="down", detail="gone")

    result = asyncio.run(collect_system_health())
    # Worst-of rollup must surface "down", not silently soften it to "degraded".
    assert result.status == "down"
    statuses = {c.name: c.status for c in result.components}
    assert statuses["ok_probe"] == "ok"
    assert statuses["dead_probe"] == "down"


def test_probe_singleton_ok_when_getter_returns_non_none():
    probe = probe_singleton("toy", lambda: object())
    result = asyncio.run(probe(None))
    assert result.name == "toy"
    assert result.status == "ok"


def test_probe_singleton_down_when_getter_returns_none():
    probe = probe_singleton("toy", lambda: None)
    result = asyncio.run(probe(None))
    assert result.status == "down"
    assert "None" in (result.detail or "")


def test_probe_singleton_down_when_getter_raises():
    def boom():
        raise RuntimeError("boom")

    probe = probe_singleton("toy", boom)
    result = asyncio.run(probe(None))
    assert result.status == "down"
    assert "RuntimeError" in (result.detail or "")


def test_probe_singleton_supports_async_getter():
    async def get_async():
        return object()

    probe = probe_singleton("toy", get_async, async_getter=True)
    result = asyncio.run(probe(None))
    assert result.status == "ok"


def test_probe_app_state_degraded_when_request_missing():
    probe = probe_app_state("toy", "missing_attr")
    result = asyncio.run(probe(None))
    assert result.status == "degraded"
    assert "missing_attr" in (result.detail or "")


def test_probe_app_state_degraded_when_attr_missing():
    class _State: ...

    class _App:
        state = _State()

    class _Request:
        app = _App()

    probe = probe_app_state("toy", "missing_attr")
    result = asyncio.run(probe(_Request()))
    assert result.status == "degraded"


def test_probe_app_state_down_when_attr_is_none():
    class _State:
        configured = None

    class _App:
        state = _State()

    class _Request:
        app = _App()

    probe = probe_app_state("toy", "configured")
    result = asyncio.run(probe(_Request()))
    assert result.status == "down"
    assert "is None" in (result.detail or "")


def test_probe_app_state_ok_when_attr_set():
    class _State:
        configured = "ready"

    class _App:
        state = _State()

    class _Request:
        app = _App()

    probe = probe_app_state("toy", "configured")
    result = asyncio.run(probe(_Request()))
    assert result.status == "ok"


def test_register_singleton_probe_one_liner_registers_under_name():
    register_singleton_probe("toy_singleton", lambda: object())
    assert "toy_singleton" in list_registered_probes()
    result = asyncio.run(collect_system_health())
    statuses = {c.name: c.status for c in result.components}
    assert statuses["toy_singleton"] == "ok"


def test_register_app_state_probe_one_liner_registers_under_name():
    register_app_state_probe("toy_state", "anything")
    assert "toy_state" in list_registered_probes()
    result = asyncio.run(collect_system_health())
    names = {c.name for c in result.components}
    assert "toy_state" in names


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
