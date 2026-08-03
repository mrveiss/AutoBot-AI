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


def test_status_degraded_when_liveness_monitor_unwired():
    """GH#13331: unwired (never set on app.state) must land at "degraded",
    matching api/system_health.py's probe_app_state() precedent for a
    missing attribute -- NOT "down". A request-less internal caller, or the
    background lifespan window before this init step runs, must not drag
    the whole system-health aggregate to "down" (#13336 review A1/A2)."""
    from llc.health.probe import _compute_status

    m = _base_metrics(liveness_monitor_wired=False, liveness_monitor_running=False)
    assert _compute_status(m) == "degraded"


def test_status_degraded_when_session_checkpointer_unwired():
    from llc.health.probe import _compute_status

    m = _base_metrics(session_checkpointer_wired=False, session_checkpointer_running=False)
    assert _compute_status(m) == "degraded"


def test_status_wired_key_is_diagnostic_only_not_a_severity_input():
    """The *_wired keys exist purely so callers can distinguish "never wired"
    from "wired but stopped" in `data` -- _compute_status must derive
    severity from `running` alone, so wired=True with the same running value
    produces an identical status to wired=False (#13336 review A1)."""
    from llc.health.probe import _compute_status

    wired = _base_metrics(liveness_monitor_wired=True, liveness_monitor_running=False)
    unwired = _base_metrics(liveness_monitor_wired=False, liveness_monitor_running=False)
    assert _compute_status(wired) == _compute_status(unwired) == "degraded"


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
async def test_probe_returns_unwired_degraded_with_no_request_context():
    """GH#13331 (review A1/A2): without a request, the probe cannot reach
    app.state at all and must report the components unwired -- but that is
    "degraded", not "down". A missing request context (an internal caller,
    or the background lifespan window before this init step has run) must
    not drag the whole /api/health aggregate to "down"."""
    from unittest.mock import patch

    async_pair = AsyncMock(return_value=(0, 0))
    async_zero = AsyncMock(return_value=0)
    async_none = AsyncMock(return_value=None)
    async_false = AsyncMock(return_value=False)

    with (
        # Isolate the wired/unwired behaviour under test from the unrelated
        # HeartbeatScheduler-not-started case, which would independently
        # force "down" via the very first _compute_status check.
        patch("llc.health.probe._is_scheduler_running", return_value=True),
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
    assert result.status == "degraded"


# NOTE on why the real-lifespan-objects test for this fix lives in
# initialization/lifespan_test.py instead of here: it is a plain locality
# choice -- that test drives the real lifespan objects, which belong to that
# module.
#
# It used to be a load-bearing workaround. llc/tests/conftest.py installed a
# `sys.modules["agents"]` stub at import time (to dodge the chromadb import
# chain) and only restored it at package teardown, so the stub was live for
# the whole collect-plus-run window. Nothing importing
# `initialization.lifespan` -> `api.overseer_handlers` -> `agents.overseer`
# could be collected inside it. A one-run sweep survived only because
# `initialization` sorts before `llc` alphabetically AND
# lifespan_test.py:19 imports at MODULE level, so the chain was already
# cached before the stub landed -- an invariant that broke the moment either
# changed, and that was already broken for
# `pytest autobot-backend/llc/tests autobot-backend/initialization`.
#
# #13337 removed the workaround's reason to exist: the stubs are now bound to
# this package's own collect and run windows (see conftest.py's
# `_ScopedStubs`), so either ordering passes. The repo-wide detector that
# would catch a future conftest letting a stub escape is tracked separately
# in #13361.
