# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for LLC health probe (GH#8259)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

# GH#9995/GH#10140: the scheduler circular-import that once required pre-stubbing
# llc.services here is resolved — HeartbeatScheduler / LivenessMonitor / the
# health probe all import cleanly in the test environment. The old module-level
# ``sys.modules.setdefault("llc.services", MagicMock())`` block leaked MagicMock
# stubs into every test module collected after this one, masking regressions.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scheduler(*, running: bool = True, task_done: bool = False) -> MagicMock:
    s = MagicMock()
    # Probe uses is_running property (CR-4); set it directly on the mock.
    s.is_running = running and not task_done
    return s


def _make_monitor(*, running: bool = True, task_done: bool = False) -> MagicMock:
    m = MagicMock()
    m.is_running = running and not task_done
    return m


def _make_request(app_state: object | None) -> MagicMock:
    """Build a minimal fastapi.Request-like double exposing .app.state."""
    request = MagicMock()
    request.app.state = app_state
    return request


def _base_metrics(**overrides) -> dict:
    base = {
        "heartbeat_scheduler_running": True,
        "liveness_monitor_wired": True,
        "liveness_monitor_running": True,
        "session_checkpointer_wired": True,
        "session_checkpointer_running": True,
        "scheduler_last_tick_age_seconds": 2.5,
        "agents_overdue_degraded": 0,
        "agents_overdue_critical": 0,
        "budget_warning_companies": 0,
        "budget_exhausted_companies": 0,
        "pending_approvals_critical": 0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _is_scheduler_running
# ---------------------------------------------------------------------------


def test_scheduler_running_when_task_alive():
    from llc.health.probe import _is_scheduler_running

    assert _is_scheduler_running(_make_scheduler(running=True, task_done=False)) is True


def test_scheduler_not_running_when_stopped():
    from llc.health.probe import _is_scheduler_running

    assert _is_scheduler_running(_make_scheduler(running=False)) is False


def test_scheduler_not_running_when_task_done():
    from llc.health.probe import _is_scheduler_running

    assert _is_scheduler_running(_make_scheduler(running=True, task_done=True)) is False


def test_scheduler_not_running_falls_back_for_missing_property():
    from llc.health.probe import _is_scheduler_running

    # Object with no is_running attribute → defaults to False
    assert _is_scheduler_running(object()) is False


# ---------------------------------------------------------------------------
# _app_state_scheduler_state — GH#13331: wired-vs-running distinction
# ---------------------------------------------------------------------------


def test_wired_and_running_when_app_state_has_a_running_instance():
    from types import SimpleNamespace

    from llc.health.probe import _app_state_scheduler_state

    request = _make_request(SimpleNamespace(llc_liveness_monitor=_make_monitor(running=True)))
    wired, running = _app_state_scheduler_state(request, "llc_liveness_monitor")
    assert (wired, running) == (True, True)


def test_wired_but_not_running_when_app_state_instance_is_stopped():
    from types import SimpleNamespace

    from llc.health.probe import _app_state_scheduler_state

    request = _make_request(SimpleNamespace(llc_liveness_monitor=_make_monitor(running=False)))
    wired, running = _app_state_scheduler_state(request, "llc_liveness_monitor")
    assert (wired, running) == (True, False)


def test_wired_but_not_running_when_app_state_attr_is_none():
    """Lifespan caught a startup failure and recorded None -- attribute IS
    present, so this must read as wired, not unwired (GH#13331)."""
    from types import SimpleNamespace

    from llc.health.probe import _app_state_scheduler_state

    request = _make_request(SimpleNamespace(llc_liveness_monitor=None))
    wired, running = _app_state_scheduler_state(request, "llc_liveness_monitor")
    assert (wired, running) == (True, False)


def test_unwired_when_app_state_never_got_the_attribute():
    """The core #13331 regression: an attribute lifespan never set must
    report distinctly (unwired) from a wired-but-stopped component -- both
    used to collapse into a single not-running bool."""
    from types import SimpleNamespace

    from llc.health.probe import _app_state_scheduler_state

    request = _make_request(SimpleNamespace())  # no llc_liveness_monitor at all
    wired, running = _app_state_scheduler_state(request, "llc_liveness_monitor")
    assert (wired, running) == (False, False)


def test_unwired_when_request_is_none():
    """No request context (e.g. an internal caller) cannot verify wiring --
    must report unwired, not fabricate a running/not-running verdict."""
    from llc.health.probe import _app_state_scheduler_state

    wired, running = _app_state_scheduler_state(None, "llc_liveness_monitor")
    assert (wired, running) == (False, False)


def test_app_state_scheduler_state_works_for_session_checkpointer_attr():
    from types import SimpleNamespace

    from llc.health.probe import _app_state_scheduler_state

    request = _make_request(SimpleNamespace(llc_session_checkpointer=_make_monitor(running=True)))
    wired, running = _app_state_scheduler_state(request, "llc_session_checkpointer")
    assert (wired, running) == (True, True)


# ---------------------------------------------------------------------------
# HeartbeatScheduler.is_running property (CR-4)
# ---------------------------------------------------------------------------


def test_heartbeat_scheduler_is_running_when_task_alive():
    from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler

    s = HeartbeatScheduler()
    s._running = True
    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.done.return_value = False
    # HeartbeatScheduler.is_running checks _poll_task (not the base _task).
    s._poll_task = mock_task
    assert s.is_running is True


def test_heartbeat_scheduler_not_running_when_flag_false():
    from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler

    s = HeartbeatScheduler()
    s._running = False
    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.done.return_value = False
    s._task = mock_task
    assert s.is_running is False


def test_heartbeat_scheduler_not_running_when_task_none():
    from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler

    s = HeartbeatScheduler()
    s._running = True
    s._task = None
    assert s.is_running is False


def test_heartbeat_scheduler_not_running_when_task_done():
    from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler

    s = HeartbeatScheduler()
    s._running = True
    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.done.return_value = True
    s._task = mock_task
    assert s.is_running is False


# ---------------------------------------------------------------------------
# LivenessMonitor.is_running property (CR-4)
# ---------------------------------------------------------------------------


def test_liveness_monitor_is_running_when_task_alive():
    from llc.scheduler.liveness_monitor import LivenessMonitor

    m = LivenessMonitor()
    m._running = True
    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.done.return_value = False
    m._task = mock_task
    assert m.is_running is True


def test_liveness_monitor_not_running_when_flag_false():
    from llc.scheduler.liveness_monitor import LivenessMonitor

    m = LivenessMonitor()
    m._running = False
    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.done.return_value = False
    m._task = mock_task
    assert m.is_running is False


def test_liveness_monitor_not_running_when_task_none():
    from llc.scheduler.liveness_monitor import LivenessMonitor

    m = LivenessMonitor()
    m._running = True
    m._task = None
    assert m.is_running is False


# ---------------------------------------------------------------------------
# _compute_status — two-level overdue logic (CR-2)
# ---------------------------------------------------------------------------


def test_status_ok_all_nominal():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics()) == "ok"


def test_status_down_scheduler_stopped():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics(heartbeat_scheduler_running=False)) == "down"


def test_status_down_agents_overdue_critical():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics(agents_overdue_critical=1)) == "down"


def test_status_degraded_agents_overdue_degraded():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics(agents_overdue_degraded=1)) == "degraded"


def test_status_degraded_budget_exhausted():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics(budget_exhausted_companies=1)) == "degraded"


def test_status_degraded_budget_warning():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics(budget_warning_companies=2)) == "degraded"


def test_status_degraded_monitor_down():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics(liveness_monitor_running=False)) == "degraded"


def test_status_down_when_liveness_monitor_unwired():
    """GH#13331: unwired must be worse than degraded, and distinct from the
    wired-but-stopped case above."""
    from llc.health.probe import _compute_status

    m = _base_metrics(liveness_monitor_wired=False, liveness_monitor_running=False)
    assert _compute_status(m) == "down"


def test_status_down_when_session_checkpointer_unwired():
    from llc.health.probe import _compute_status

    m = _base_metrics(session_checkpointer_wired=False, session_checkpointer_running=False)
    assert _compute_status(m) == "down"


def test_status_backward_compat_missing_wired_keys_defaults_ok():
    """A metrics dict built before GH#13331 (no *_wired keys) must not be
    newly downgraded to "down" -- absence of the key means "assume wired"."""
    from llc.health.probe import _compute_status

    m = _base_metrics()
    del m["liveness_monitor_wired"]
    del m["session_checkpointer_wired"]
    assert _compute_status(m) == "ok"


def test_status_degraded_pending_approvals():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics(pending_approvals_critical=3)) == "degraded"


def test_down_overrides_degraded():
    from llc.health.probe import _compute_status

    m = _base_metrics(heartbeat_scheduler_running=False, budget_warning_companies=1)
    assert _compute_status(m) == "down"


def test_critical_overdue_overrides_degraded_overdue():
    from llc.health.probe import _compute_status

    m = _base_metrics(agents_overdue_degraded=2, agents_overdue_critical=1)
    assert _compute_status(m) == "down"


# ---------------------------------------------------------------------------
# probe_llc integration — mock Redis + DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_returns_ok_when_all_healthy():
    from unittest.mock import patch

    metrics = _base_metrics(
        heartbeat_scheduler_running=True,
        liveness_monitor_running=True,
        scheduler_last_tick_age_seconds=3.0,
    )
    with patch("llc.health.probe._collect_metrics", new=AsyncMock(return_value=metrics)):
        from llc.health.probe import probe_llc

        result = await probe_llc(None)
        assert result.status == "ok"
        assert result.data["heartbeat_scheduler_running"] is True
        assert result.data["agents_overdue_critical"] == 0
        assert result.data["agents_overdue_degraded"] == 0


@pytest.mark.asyncio
async def test_probe_returns_critical_when_scheduler_stopped():
    from unittest.mock import patch

    metrics = _base_metrics(heartbeat_scheduler_running=False)
    with patch("llc.health.probe._collect_metrics", new=AsyncMock(return_value=metrics)):
        from llc.health.probe import probe_llc

        result = await probe_llc(None)
        assert result.status == "down"
        assert result.data["heartbeat_scheduler_running"] is False


@pytest.mark.asyncio
async def test_probe_returns_down_on_exception():
    from unittest.mock import patch

    with patch("llc.health.probe._collect_metrics", side_effect=RuntimeError("Redis down")):
        from llc.health.probe import probe_llc

        result = await probe_llc(None)
        assert result.status == "down"
        assert "RuntimeError" in result.detail


@pytest.mark.asyncio
async def test_probe_returns_degraded_budget_warning():
    from unittest.mock import patch

    metrics = _base_metrics(budget_warning_companies=3)
    with patch("llc.health.probe._collect_metrics", new=AsyncMock(return_value=metrics)):
        from llc.health.probe import probe_llc

        result = await probe_llc(None)
        assert result.status == "degraded"
        assert result.data["budget_warning_companies"] == 3


@pytest.mark.asyncio
async def test_probe_returns_degraded_when_agents_overdue_degraded():
    from unittest.mock import patch

    metrics = _base_metrics(agents_overdue_degraded=2)
    with patch("llc.health.probe._collect_metrics", new=AsyncMock(return_value=metrics)):
        from llc.health.probe import probe_llc

        result = await probe_llc(None)
        assert result.status == "degraded"
        assert result.data["agents_overdue_degraded"] == 2


@pytest.mark.asyncio
async def test_probe_returns_unwired_down_with_no_request_context():
    """GH#13331: without a request, the probe cannot reach app.state at all
    and must report the components unwired (down) rather than fabricate a
    running/not-running verdict from a disconnected shadow singleton."""
    from unittest.mock import patch

    async_pair = AsyncMock(return_value=(0, 0))
    async_zero = AsyncMock(return_value=0)
    async_none = AsyncMock(return_value=None)
    async_false = AsyncMock(return_value=False)

    with (
        patch("llc.health.probe._count_overdue_agents", new=async_pair),
        patch("llc.health.probe._budget_counts", new=async_pair),
        patch("llc.health.probe._pending_approvals_critical", new=async_zero),
        patch("llc.health.probe._count_agents_missing_instructions", new=async_zero),
        patch("llc.health.probe._scheduler_tick_age", new=async_none),
        patch("llc.health.probe._session_recovery_available", new=async_false),
    ):
        from llc.health.probe import probe_llc

        result = await probe_llc(None)

    assert result.data["liveness_monitor_wired"] is False
    assert result.data["session_checkpointer_wired"] is False
    assert result.status == "down"


# NOTE: the "real lifespan objects" regression test for this fix lives in
# initialization/lifespan_test.py, not here. llc/tests/conftest.py stubs
# sys.modules["agents"] at collection time (to dodge the chromadb import
# chain) so every test file under llc/tests/ can import cleanly -- but that
# stub also permanently breaks `initialization.lifespan`'s own import chain
# (api.overseer_handlers -> agents.overseer) for the rest of the pytest
# process once it has run. Exercising the real lifespan init functions from
# initialization/lifespan_test.py avoids that collision and matches the
# precedent already established there (test_init_liveness_monitor_actually_starts_it,
# #13085).
