# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The reconciler's service-restart tracker persists across a backend restart
instead of resetting to zero attempts every time (#16712).

Before this fix `_service_remediation_tracker` was `self`-scoped process
memory: `self._service_remediation_tracker: Dict[tuple, Dict] = {}`. Every
SLM backend restart -- which every update-all deploy causes, in its first
play -- silently wiped it, giving a permanently-failing service three fresh
attempts after every deploy, forever. The count and exhausted flag now live
on `Service.extra_data["remediation"]`, the row already being read/written
every heartbeat, so a fresh `ReconcilerService()` instance (a restart, in
these tests) sees exactly what the row says.

The module is loaded from disk, not imported, because the package conftest
stubs `services.*` and a plain `import services.reconciler` yields a
MagicMock that would satisfy every check here while exercising nothing.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_reconciler():
    """Load reconciler.py with a REAL ServiceStatus bound onto the stubbed
    models.database (#16712).

    The package conftest stubs `sys.modules["models.database"]` to a
    MagicMock for the whole test session, so `ServiceStatus.FAILED.value`
    inside reconciler.py would otherwise resolve to a MagicMock attribute --
    never equal to the plain string status this test passes, silently
    making `status != ServiceStatus.FAILED.value` true unconditionally.
    `service_status` itself is a standalone module the conftest never
    touches, so the real enum is one import away.
    """
    import service_status  # noqa: PLC0415

    sys.modules.setdefault("models.database", MagicMock())
    sys.modules["models.database"].ServiceStatus = service_status.ServiceStatus

    spec = importlib.util.spec_from_file_location(
        "reconciler_under_service_remediation_16712_test", _SLM_ROOT / "services" / "reconciler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconciler_under_service_remediation_16712_test"] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()


class _FakeService:
    """A minimal Service-row stand-in: attribute access and extra_data only."""

    def __init__(self, *, service_name="autobot-backend", extra_data=None):
        self.node_id = "node-1"
        self.service_name = service_name
        self.extra_data = extra_data


def test_read_defaults_to_zero_when_never_attempted():
    service = _FakeService(extra_data=None)

    assert reconciler.read_service_remediation(service) == {
        "count": 0,
        "last_attempt": None,
        "exhausted": False,
        "last_cause": None,
    }


def test_write_then_read_round_trips_and_preserves_other_extra_data_keys():
    service = _FakeService(extra_data={"error_message": "boom"})
    now = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)

    reconciler.write_service_remediation(service, {"count": 2, "last_attempt": now, "exhausted": False})

    assert service.extra_data["error_message"] == "boom", "an unrelated extra_data key must survive the write"
    assert reconciler.read_service_remediation(service) == {
        "count": 2,
        "last_attempt": now,
        "exhausted": False,
        "last_cause": None,
    }


def test_the_tracker_survives_a_fresh_reconciler_instance():
    """Simulates a backend restart: a brand-new ReconcilerService, no carried
    process memory, still sees the count -- because it comes from the row.
    """
    service = _FakeService(extra_data={"remediation": {"count": 3, "last_attempt": None, "exhausted": True}})

    fresh = reconciler.ReconcilerService()
    tracker = reconciler.read_service_remediation(service)

    assert not hasattr(fresh, "_service_remediation_tracker"), "the old process-memory tracker must be gone"
    assert tracker["count"] == 3
    assert tracker["exhausted"] is True


def test_recovery_clears_the_tracker():
    """A service observed no longer FAILED resets its remediation entry on
    the very next heartbeat -- no separate manual step needed.
    """
    service = _FakeService(extra_data={"remediation": {"count": 3, "last_attempt": None, "exhausted": True}})
    svc = reconciler.ReconcilerService()

    svc._update_existing_service(service, {"status": "running"}, "running", "", datetime.now(timezone.utc))

    assert "remediation" not in service.extra_data


def test_an_in_progress_failure_keeps_its_tracker():
    """The control: a service still FAILED must not have its tracker wiped
    by the same heartbeat update that recovery clears it on.
    """
    service = _FakeService(extra_data={"remediation": {"count": 2, "last_attempt": None, "exhausted": False}})
    svc = reconciler.ReconcilerService()

    svc._update_existing_service(service, {"status": "failed"}, "failed", "still down", datetime.now(timezone.utc))

    assert service.extra_data["remediation"]["count"] == 2


def test_reset_service_remediation_tracker_clears_and_commits():
    """The operator-acknowledgement path (api/nodes.py's acknowledge-remediation)."""
    service = _FakeService(extra_data={"remediation": {"count": 3, "last_attempt": None, "exhausted": True}})
    result = MagicMock()
    result.scalars.return_value.all.return_value = [service]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    svc = reconciler.ReconcilerService()

    asyncio.run(svc.reset_service_remediation_tracker(db, "node-1"))

    assert "remediation" not in service.extra_data
    db.commit.assert_awaited_once()


def test_reset_service_remediation_tracker_is_a_noop_when_nothing_to_clear():
    """The control: no commit fires when there is nothing to clear."""
    service = _FakeService(extra_data=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [service]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    svc = reconciler.ReconcilerService()

    asyncio.run(svc.reset_service_remediation_tracker(db, "node-1"))

    db.commit.assert_not_awaited()


class _RaceSimulatingSession:
    """A `db` whose `refresh()` mutates `service.extra_data` mid-call (#17096 review).

    Models a heartbeat for the SAME service row landing on a DIFFERENT
    session while `_remediate_failed_service` awaits the (here, fake)
    ansible restart -- exactly what `refresh()` is meant to observe.
    """

    def __init__(self, *, extra_data_after_refresh):
        self._extra_data_after_refresh = extra_data_after_refresh
        self.refresh_called = False

    def add(self, _obj):
        pass

    async def commit(self):
        pass

    async def refresh(self, obj):
        self.refresh_called = True
        obj.extra_data = self._extra_data_after_refresh


def _node() -> object:
    return SimpleNamespace(node_id="node-1", hostname="node-1", ansible_target="node-1")


def test_write_after_restart_uses_the_row_refreshed_after_the_await_not_the_stale_pre_await_one():
    """#17096 review, finding 2: a concurrent heartbeat clearing the tracker
    (service recovered on its own) while the restart was still in flight must
    not be silently undone by the write that follows the restart's own await.
    """
    service = _FakeService(extra_data={"remediation": {"count": 2, "last_attempt": None, "exhausted": False}})
    # Simulates: the heartbeat path observed recovery and cleared the tracker,
    # AND wrote an unrelated key -- both must survive this write.
    db = _RaceSimulatingSession(extra_data_after_refresh={"error_message": "transient, cleared by heartbeat"})
    svc = reconciler.ReconcilerService()
    svc._restart_service_via_ansible = AsyncMock(
        return_value=(False, "simulated restart failure")
    )  # our own restart still failed

    result = asyncio.run(svc._remediate_failed_service(db, _node(), service))

    assert result is True
    assert db.refresh_called, "the fix must re-read the row after the restart await, or this test proves nothing"
    tracker = reconciler.read_service_remediation(service)
    assert (
        tracker["count"] == 1
    ), f"expected count=1 (incremented from the FRESH post-refresh 0, not the stale pre-await 2), got {tracker}"
    assert (
        service.extra_data["error_message"] == "transient, cleared by heartbeat"
    ), "a concurrent write to an unrelated extra_data key must survive this write too"


def test_write_after_restart_increments_normally_when_nothing_raced():
    """The control: without a concurrent write, refresh is a no-op and the
    count still increments the ordinary way.
    """
    service = _FakeService(extra_data={"remediation": {"count": 2, "last_attempt": None, "exhausted": False}})
    db = _RaceSimulatingSession(extra_data_after_refresh=dict(service.extra_data))
    svc = reconciler.ReconcilerService()
    svc._restart_service_via_ansible = AsyncMock(return_value=(False, "simulated restart failure"))

    asyncio.run(svc._remediate_failed_service(db, _node(), service))

    tracker = reconciler.read_service_remediation(service)
    assert tracker["count"] == 3, f"expected the ordinary 2 -> 3 incrementing to still work, got {tracker}"


def test_read_service_remediation_resets_and_logs_on_a_malformed_value():
    """#17096 review, finding 3: a non-dict `remediation` value (some other
    writer's mistake) must reset to never-attempted, not raise out of `.get()`.
    """
    service = _FakeService(extra_data={"remediation": "not-a-dict"})

    tracker = reconciler.read_service_remediation(service)

    assert tracker == {"count": 0, "last_attempt": None, "exhausted": False, "last_cause": None}


class _LoopSession:
    """`db_service.session()` stand-in for `_remediate_failed_services` (#17096
    review finding 3): the Setting check, then the Service list, then one Node
    lookup per service, in that exact call order -- no real SQLAlchemy query
    construction needed since this ignores the query object entirely.
    """

    def __init__(self, services, nodes_by_id):
        self._services = services
        self._nodes_by_id = nodes_by_id
        self._call = 0

    @asynccontextmanager
    async def session(self):
        yield self

    async def execute(self, _query):
        self._call += 1
        if self._call == 1:
            return SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(value="true"))
        if self._call == 2:
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self._services))
        service = self._services[self._call - 3]
        return SimpleNamespace(scalar_one_or_none=lambda: self._nodes_by_id[service.node_id])


def test_remediate_failed_services_continues_past_one_services_own_exception():
    """#17096 review, finding 3: one service raising (a malformed row, or any
    other unexpected failure) must not stop the OTHER failing services this
    cycle from being attempted.
    """
    good = _FakeService(service_name="good-service", extra_data=None)
    good.node_id = "node-good"
    bad = _FakeService(service_name="bad-service", extra_data=None)
    bad.node_id = "node-bad"
    services = [bad, good]  # the raiser first, so a stop-on-first-exception bug is caught
    nodes_by_id = {
        "node-good": SimpleNamespace(node_id="node-good", status="online"),
        "node-bad": SimpleNamespace(node_id="node-bad", status="online"),
    }

    svc = reconciler.ReconcilerService()
    svc._is_remediation_suppressed = AsyncMock(return_value=False)
    attempted: list[str] = []

    async def _fake_remediate_failed_service(_db, _node, service):
        attempted.append(service.service_name)
        if service.service_name == "bad-service":
            raise ValueError("simulated: a malformed row blew up mid-remediation")
        return True

    svc._remediate_failed_service = _fake_remediate_failed_service

    original_services_database = sys.modules.get("services.database")
    sys.modules["services.database"] = SimpleNamespace(db_service=_LoopSession(services, nodes_by_id))
    try:
        asyncio.run(svc._remediate_failed_services())
    finally:
        if original_services_database is not None:
            sys.modules["services.database"] = original_services_database
        else:
            sys.modules.pop("services.database", None)

    assert attempted == [
        "bad-service",
        "good-service",
    ], f"expected both services attempted despite bad-service raising, got {attempted}"


class _CapturingSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass


def test_restart_failure_cause_is_captured_end_to_end_through_to_the_exhaustion_event():
    """#16712 AC (#17096 review, finding 4): exhaustion must name "the node,
    the service AND the captured cause" -- not just node and service.

    Exercises the real path: a failing restart's `_log_restart_result` cause
    persists onto the tracker (`write_service_remediation`'s `last_cause`),
    survives to the NEXT cycle's read at `MAX_SERVICE_RESTART_ATTEMPTS`, and
    lands on the `NodeEvent` `_create_max_attempts_service_event` creates.
    """
    service = _FakeService(
        extra_data={
            "remediation": {
                "count": reconciler.MAX_SERVICE_RESTART_ATTEMPTS,
                "last_attempt": None,
                "exhausted": False,
                "last_cause": "connection timed out reaching node-1",
            }
        }
    )
    node = SimpleNamespace(node_id="node-1", hostname="node-1", ansible_target="node-1")
    db = _CapturingSession()
    svc = reconciler.ReconcilerService()

    # NodeEvent is a MagicMock (models.database is stubbed) -- its constructor
    # would not actually store `details` as a real, inspectable dict. A plain
    # SimpleNamespace stands in so the assertions below check the real kwargs
    # `_create_max_attempts_service_event` builds, not a mock's auto-attributes.
    original_node_event = reconciler.NodeEvent
    reconciler.NodeEvent = lambda **kwargs: SimpleNamespace(**kwargs)
    try:
        result = asyncio.run(svc._remediate_failed_service(db, node, service))
    finally:
        reconciler.NodeEvent = original_node_event

    assert result is False, "an already-exhausted service must not attempt a fresh restart"
    assert len(db.added) == 1, f"expected exactly one NodeEvent created, got {len(db.added)}"
    event = db.added[0]
    assert event.details["cause"] == "connection timed out reaching node-1"
    assert "connection timed out reaching node-1" in event.message
    assert event.details["service_name"] == service.service_name
    assert event.node_id == node.node_id
