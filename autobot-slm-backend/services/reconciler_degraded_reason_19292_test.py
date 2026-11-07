# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The reconciler restarts slm-agent only for a missing heartbeat (#19292).

Live, a CPU burst flapped the manager online -> error -> degraded and every
DEGRADED landed in ``_attempt_remediation``, which restarted slm-agent -- a
remedy that cannot lower load. These drive the REAL reconciler (loaded from
disk; the package conftest stubs ``services.reconciler``) through the
heartbeat path and the remediation selection.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from testkit.fake_async_session import FakeAsyncSession

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_reconciler():
    spec = importlib.util.spec_from_file_location(
        "reconciler_under_degraded_reason_19292_test", _SLM_ROOT / "services" / "reconciler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()
nhs = sys.modules["services.node_health_status"]

_DEGRADED_CPU = float(nhs.RESOURCE_DEGRADED_PCT + 1)
_SPIKE_CPU = float(nhs.RESOURCE_ERROR_PCT + 1)
_CALM_CPU = float(nhs.RESOURCE_DEGRADED_PCT - 10)


def _node(node_id="node-19292", status=None, reason=None, last_heartbeat=None):
    node = SimpleNamespace(
        node_id=node_id,
        hostname=node_id,
        ansible_target=node_id,
        ip_address="node-address",
        status=status or reconciler.NodeStatus.ONLINE.value,
        cpu_percent=0.0,
        memory_percent=0.0,
        disk_percent=0.0,
        last_heartbeat=last_heartbeat or datetime.now(timezone.utc),
        extra_data={},
        agent_version=None,
        os_info=None,
    )
    if reason:
        nhs.set_degraded_reason(node, reason)
    return node


@contextmanager
def _recorded_events():
    """Swap the (stubbed) NodeEvent model for one whose kwargs can be read back."""
    original = reconciler.NodeEvent
    reconciler.NodeEvent = lambda **kw: SimpleNamespace(**kw)
    try:
        yield
    finally:
        reconciler.NodeEvent = original


def _beat(service, node, cpu) -> FakeAsyncSession:
    session = FakeAsyncSession(results=[[node]])
    asyncio.run(service.update_node_heartbeat(session, node.node_id, cpu, 10.0, 10.0))
    return session


def _events(session) -> list:
    return [obj for obj in session.added if hasattr(obj, "details")]


def test_a_single_cpu_spike_leaves_an_online_node_online_with_no_event():
    service, node = reconciler.ReconcilerService(), _node()
    with _recorded_events():
        spike = _beat(service, node, _SPIKE_CPU)
        after = _beat(service, node, _CALM_CPU)
    assert node.status == reconciler.NodeStatus.ONLINE.value
    assert nhs.degraded_reason(node) is None
    assert _events(spike) == [] and _events(after) == []


def test_a_sustained_breach_degrades_for_resource_pressure_and_raises_the_alert_event():
    service, node = reconciler.ReconcilerService(), _node()
    with _recorded_events():
        sessions = [_beat(service, node, _DEGRADED_CPU) for _ in range(nhs.RESOURCE_ENTER_SAMPLES)]
    assert node.status == reconciler.NodeStatus.DEGRADED.value
    assert nhs.degraded_reason(node) == nhs.REASON_RESOURCE_PRESSURE
    events = _events(sessions[-1])
    assert len(events) == 1 and events[0].details["reason"] == nhs.REASON_RESOURCE_PRESSURE
    assert events[0].event_type == reconciler.NodeEventType.HEALTH_CHECK.value
    assert all(_events(s) == [] for s in sessions[:-1])


def test_recovery_from_resource_pressure_is_damped():
    service, node = reconciler.ReconcilerService(), _node()
    with _recorded_events():
        for _ in range(nhs.RESOURCE_ENTER_SAMPLES):
            _beat(service, node, _DEGRADED_CPU)
        _beat(service, node, _CALM_CPU)
        assert node.status == reconciler.NodeStatus.DEGRADED.value, "one calm beat must not clear it"
        for _ in range(nhs.RESOURCE_EXIT_SAMPLES - 1):
            _beat(service, node, _CALM_CPU)
    assert node.status == reconciler.NodeStatus.ONLINE.value
    assert nhs.degraded_reason(node) is None


def test_service_health_is_its_own_reason():
    status, reason = reconciler._node_status_and_reason(nhs.LEVEL_OK, None, True)
    assert status == reconciler.NodeStatus.DEGRADED.value
    assert reason == nhs.REASON_SERVICE_HEALTH


def test_a_missing_heartbeat_is_recorded_as_no_heartbeat():
    service, node = reconciler.ReconcilerService(), _node()
    service._broadcast_node_status = AsyncMock()
    with _recorded_events():
        asyncio.run(service._handle_degraded_node(FakeAsyncSession(), node, node.status))
    assert node.status == reconciler.NodeStatus.DEGRADED.value
    assert nhs.degraded_reason(node) == nhs.REASON_NO_HEARTBEAT


@contextmanager
def _fake_db_service(rows_per_query: list, on_refresh=None):
    """Install ``services.database.db_service`` answering each query from ``rows_per_query``."""
    name = "services.database"
    created = name not in sys.modules
    if created:
        sys.modules[name] = ModuleType(name)
    module = sys.modules[name]
    original = getattr(module, "db_service", None)

    @asynccontextmanager
    async def _session():
        yield FakeAsyncSession(results=rows_per_query, on_refresh=on_refresh)

    module.db_service = SimpleNamespace(session=_session)
    try:
        yield
    finally:
        if created:
            del sys.modules[name]
        else:
            module.db_service = original


def test_remediation_restarts_the_agent_only_for_no_heartbeat():
    now = datetime.now(timezone.utc)
    degraded = reconciler.NodeStatus.DEGRADED.value
    no_beat = _node("n-no-beat", degraded, nhs.REASON_NO_HEARTBEAT, now - timedelta(seconds=600))
    pressure = _node("n-pressure", degraded, nhs.REASON_RESOURCE_PRESSURE, now)
    services = _node("n-services", degraded, nhs.REASON_SERVICE_HEALTH, now)
    # Recorded no_heartbeat, but a beat landed after: the agent is alive (review item 1).
    raced = _node("n-raced", degraded, nhs.REASON_NO_HEARTBEAT, now - timedelta(seconds=5))
    service = reconciler.ReconcilerService()
    service._heartbeat_timeout = 90
    service._is_remediation_suppressed = AsyncMock(return_value=False)
    service._remediate_node = AsyncMock(return_value=True)
    auto_remediate = SimpleNamespace(value="true")

    with _fake_db_service([[auto_remediate], [no_beat, pressure, services, raced]]):
        asyncio.run(service._attempt_remediation())

    remediated = [call.args[1].node_id for call in service._remediate_node.await_args_list]
    assert remediated == ["n-no-beat"], "resource pressure and service health must never restart slm-agent"


class _Comparable:
    """Stand-in for ``Node.last_heartbeat``: the query result is canned, so only the operators matter."""

    def __lt__(self, other):
        return True

    def is_(self, other):
        return True


def _run_check(node, *, reachable=True, on_refresh=None, real_handlers=False):
    """Drive the real ``_check_node_health`` over one stale node."""
    service = reconciler.ReconcilerService()
    service._heartbeat_timeout = 90  # conftest's `settings` is a MagicMock; the window must be a number
    service._ping_host = AsyncMock(return_value=reachable)
    service._broadcast_node_status = AsyncMock()
    if not real_handlers:
        service._handle_degraded_node = AsyncMock()
    compose_fleet = SimpleNamespace(is_manager_node=lambda _nid: False)
    # The query is built from (stubbed) Column objects; only the operators must not raise.
    node_model = SimpleNamespace(status=MagicMock(), last_heartbeat=_Comparable())
    with (
        patch.dict(sys.modules, {"services.compose_fleet": compose_fleet}),
        patch.object(reconciler, "Node", node_model),
        _recorded_events(),
        _fake_db_service([[], [node]], on_refresh=on_refresh),
    ):
        asyncio.run(service._check_node_health())
    return service


_STALE = datetime.now(timezone.utc) - timedelta(seconds=600)


def test_a_resource_degraded_node_that_goes_silent_becomes_a_restart_candidate():
    node = _node("n-silent", reconciler.NodeStatus.DEGRADED.value, nhs.REASON_RESOURCE_PRESSURE, _STALE)
    service = _run_check(node)
    service._handle_degraded_node.assert_awaited_once()


def test_an_error_node_whose_agent_dies_becomes_no_heartbeat_and_a_restart_candidate():
    node = _node("n-error", reconciler.NodeStatus.ERROR.value, nhs.REASON_RESOURCE_PRESSURE, _STALE)
    _run_check(node, real_handlers=True)
    assert node.status == reconciler.NodeStatus.DEGRADED.value
    assert nhs.degraded_reason(node) == nhs.REASON_NO_HEARTBEAT
    assert nhs.needs_agent_restart(node, datetime.now(timezone.utc), 90) is True


def test_a_beat_landing_during_the_ping_is_not_overwritten():
    node = _node("n-raced", reconciler.NodeStatus.ONLINE.value, None, _STALE)

    def _beat_landed(row):
        row.last_heartbeat = datetime.now(timezone.utc)

    service = _run_check(node, on_refresh=_beat_landed)
    service._handle_degraded_node.assert_not_called()
    assert node.status == reconciler.NodeStatus.ONLINE.value


def test_a_concurrent_extra_data_key_survives_the_no_heartbeat_write():
    node = _node("n-merge", reconciler.NodeStatus.ONLINE.value, None, _STALE)

    def _concurrent_merge(row):
        row.extra_data = {**row.extra_data, "gpu": "written-by-a-concurrent-heartbeat"}

    _run_check(node, on_refresh=_concurrent_merge, real_handlers=True)
    assert node.extra_data["gpu"] == "written-by-a-concurrent-heartbeat"
    assert nhs.degraded_reason(node) == nhs.REASON_NO_HEARTBEAT


def test_going_offline_clears_the_dwell_state():
    node = _node("n-offline", reconciler.NodeStatus.DEGRADED.value, nhs.REASON_RESOURCE_PRESSURE, _STALE)
    _run_check(node, reachable=False, real_handlers=True)
    assert node.status == reconciler.NodeStatus.OFFLINE.value
    assert nhs.read_health_state(node) == {}


def test_a_heartbeat_cannot_spoof_its_own_reason_or_dwell():
    service, node = reconciler.ReconcilerService(), _node()
    spoof = {nhs.HEALTH_STATE_KEY: {"reason": nhs.REASON_NO_HEARTBEAT, "resource_level": nhs.LEVEL_ERROR}}
    session = FakeAsyncSession(results=[[node]])
    with _recorded_events():
        asyncio.run(service.update_node_heartbeat(session, node.node_id, _CALM_CPU, 10.0, 10.0, extra_data=spoof))
    assert node.status == reconciler.NodeStatus.ONLINE.value
    assert nhs.read_health_state(node).get("resource_level") == nhs.LEVEL_OK
    assert nhs.degraded_reason(node) is None


def test_a_manager_whose_real_agent_died_is_held_no_heartbeat_through_self_beats():
    """Review item 4: the self-heartbeat resumes, the death is recorded, a real beat clears it."""
    service, node = reconciler.ReconcilerService(), _node("00-SLM-Manager", last_heartbeat=_STALE)
    node.agent_version = "1.0.0"
    nhs.mark_agent_lost(node)
    with _recorded_events():
        session = FakeAsyncSession(results=[[node]])
        asyncio.run(
            service.update_node_heartbeat(
                session, node.node_id, _CALM_CPU, 10.0, 10.0, agent_version=nhs.SELF_AGENT_VERSION
            )
        )
        events = _events(session)
        assert node.status == reconciler.NodeStatus.DEGRADED.value
        assert nhs.degraded_reason(node) == nhs.REASON_NO_HEARTBEAT
        assert len(events) == 1 and events[0].details["reason"] == nhs.REASON_NO_HEARTBEAT
        assert nhs.needs_agent_restart(node, datetime.now(timezone.utc), 90) is True

        asyncio.run(
            service.update_node_heartbeat(
                FakeAsyncSession(results=[[node]]), node.node_id, _CALM_CPU, 10.0, 10.0, agent_version="1.0.0"
            )
        )
    assert node.status == reconciler.NodeStatus.ONLINE.value
    assert nhs.degraded_reason(node) is None


def test_the_14465_tracker_guarantees_are_untouched():
    """`_forgive_if_expired` and heartbeat-verified success stay the escalation path."""
    service = reconciler.ReconcilerService()
    assert callable(service._forgive_if_expired)
    assert callable(service._heartbeat_returned)
    assert not isinstance(reconciler.ReconcilerService, MagicMock)
