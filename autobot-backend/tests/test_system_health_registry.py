# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #3333: registry behavior for the canonical health-probe aggregator."""

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# autobot_shared.redis_client imports autobot_shared.redis_management.config which is
# absent in the test environment. Pre-stub the module so patch() can target it without
# triggering the real import chain. We also set it as a direct attribute on the package
# because autobot_shared's custom __getattr__ rejects unknown submodule names.
if "autobot_shared.redis_client" not in sys.modules:
    import autobot_shared as _autobot_shared_pkg

    _redis_client_stub = types.ModuleType("autobot_shared.redis_client")
    _redis_client_stub.get_async_redis_client = AsyncMock()
    sys.modules["autobot_shared.redis_client"] = _redis_client_stub
    _autobot_shared_pkg.redis_client = _redis_client_stub  # type: ignore[attr-defined]

from api.system_health import (
    _PROBE_TIMEOUT_S,
    ComponentHealth,
    _reset_probes_for_testing,
    collect_system_health,
    list_registered_probes,
    probe_app_state,
    probe_redis_db,
    probe_singleton,
    register_app_state_probe,
    register_health_probe,
    register_redis_probe,
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
    async def _probe_overwrite(_request=None):
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
    class _State:
        pass

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


# ---------------------------------------------------------------------------
# Issue #6914: data_callback extension for composable probe helpers
# ---------------------------------------------------------------------------


class TestProbeSingletonDataCallback:
    """data_callback on probe_singleton (#6914)."""

    def test_ok_path_callback_receives_instance(self):
        sentinel = object()
        received = []

        def cb(inst):
            received.append(inst)
            return {"found": True}

        probe = probe_singleton("toy", lambda: sentinel, data_callback=cb)
        result = asyncio.run(probe())
        assert result.status == "ok"
        assert result.data == {"found": True}
        assert received == [sentinel]

    def test_down_path_none_instance_callback_receives_none(self):
        received = []

        def cb(inst):
            received.append(inst)
            return {"found": False}

        probe = probe_singleton("toy", lambda: None, data_callback=cb)
        result = asyncio.run(probe())
        assert result.status == "down"
        assert result.data == {"found": False}
        assert received == [None]

    def test_error_path_callback_receives_none(self):
        received = []

        def cb(inst):
            received.append(inst)
            return {"found": False, "error": True}

        def boom():
            raise RuntimeError("getter exploded")

        probe = probe_singleton("toy", boom, data_callback=cb)
        result = asyncio.run(probe())
        assert result.status == "down"
        assert result.data == {"found": False, "error": True}
        assert received == [None]

    def test_without_callback_data_is_none(self):
        probe = probe_singleton("toy", lambda: object())
        result = asyncio.run(probe())
        assert result.status == "ok"
        assert result.data is None


class TestProbeRedisDdDataCallback:
    """data_callback on probe_redis_db (#6914)."""

    def _make_client(self, *, ping_ok: bool = True):
        client = MagicMock()
        if ping_ok:
            client.ping = AsyncMock(return_value=True)
        else:
            client.ping = AsyncMock(side_effect=ConnectionError("ping failed"))
        return client

    def test_ok_callback_receives_true(self):
        received = []
        client = self._make_client(ping_ok=True)

        def cb(ok):
            received.append(ok)
            return {"redis_connected": ok, "service": "test"}

        probe = probe_redis_db("toy", data_callback=cb)
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=client),
        ):
            result = asyncio.run(probe())
        assert result.status == "ok"
        assert result.data == {"redis_connected": True, "service": "test"}
        assert received == [True]

    def test_ping_fail_callback_receives_false(self):
        received = []
        client = self._make_client(ping_ok=False)

        def cb(ok):
            received.append(ok)
            return {"redis_connected": ok}

        probe = probe_redis_db("toy", data_callback=cb)
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=client),
        ):
            result = asyncio.run(probe())
        assert result.status == "down"
        assert result.data == {"redis_connected": False}
        assert received == [False]

    def test_client_unavailable_callback_receives_false(self):
        received = []

        def cb(ok):
            received.append(ok)
            return {"redis_connected": ok}

        probe = probe_redis_db("toy", data_callback=cb)
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            result = asyncio.run(probe())
        assert result.status == "down"
        assert result.data == {"redis_connected": False}
        assert received == [False]

    def test_without_callback_data_is_none(self):
        client = self._make_client(ping_ok=True)
        probe = probe_redis_db("toy")
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=client),
        ):
            result = asyncio.run(probe())
        assert result.status == "ok"
        assert result.data is None


class TestProbeAppStateDataCallback:
    """data_callback on probe_app_state (#6914)."""

    def _make_request(self, **attrs):
        class _State:
            pass

        state = _State()
        for k, v in attrs.items():
            setattr(state, k, v)

        class _App:
            pass

        app = _App()
        app.state = state

        class _Request:
            pass

        req = _Request()
        req.app = app
        return req

    def test_ok_callback_receives_value(self):
        received = []

        def cb(val):
            received.append(val)
            return {"initialized": val is not None}

        probe = probe_app_state("toy", "svc", data_callback=cb)
        result = asyncio.run(probe(self._make_request(svc="ready")))
        assert result.status == "ok"
        assert result.data == {"initialized": True}
        assert received == ["ready"]

    def test_none_attr_callback_receives_none(self):
        received = []

        def cb(val):
            received.append(val)
            return {"initialized": False}

        probe = probe_app_state("toy", "svc", data_callback=cb)
        result = asyncio.run(probe(self._make_request(svc=None)))
        assert result.status == "down"
        assert result.data == {"initialized": False}
        assert received == [None]

    def test_missing_attr_callback_receives_none(self):
        received = []

        def cb(val):
            received.append(val)
            return {"initialized": False}

        probe = probe_app_state("toy", "missing", data_callback=cb)
        result = asyncio.run(probe(self._make_request()))
        assert result.status == "degraded"
        assert result.data == {"initialized": False}
        assert received == [None]

    def test_without_callback_data_is_none(self):
        probe = probe_app_state("toy", "svc")
        result = asyncio.run(probe(self._make_request(svc="ready")))
        assert result.status == "ok"
        assert result.data is None


def test_register_redis_probe_one_liner_with_callback():
    """register_redis_probe with data_callback registers and emits data (#6914)."""
    client = MagicMock()
    client.ping = AsyncMock(return_value=True)
    register_redis_probe(
        "toy_redis_cb",
        database="main",
        data_callback=lambda ok: {"redis_connected": ok, "service": "test"},
    )
    assert "toy_redis_cb" in list_registered_probes()
    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new=AsyncMock(return_value=client),
    ):
        result = asyncio.run(collect_system_health())
    component = next(c for c in result.components if c.name == "toy_redis_cb")
    assert component.status == "ok"
    assert component.data == {"redis_connected": True, "service": "test"}
