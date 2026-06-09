# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for LLC health probe (GH#8259)."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Pre-stub modules involved in the circular-import chain that exists in the
# test environment (GH#8259-disc).  This is needed so direct imports of
# HeartbeatScheduler / LivenessMonitor do not trigger:
#   llc.scheduler.__init__ → budget_watchdog → llc.services.budget
#   → llc.services.__init__ → approval → from . import LLCServiceBase  (circular)
# Using setdefault so we don't clobber a module that was already imported fine.
for _stub_mod in (
    "llc.services",
    "llc.services.budget",
    "llc.services.approval",
    "llc.services.activity_log",
    "llc.services.work_item_service",
    "llc.scheduler.budget_watchdog",
):
    sys.modules.setdefault(_stub_mod, MagicMock())


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


def _base_metrics(**overrides) -> dict:
    base = {
        "heartbeat_scheduler_running": True,
        "liveness_monitor_running": True,
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
# _is_liveness_monitor_running
# ---------------------------------------------------------------------------


def test_monitor_running():
    from llc.health.probe import _is_liveness_monitor_running

    assert _is_liveness_monitor_running(_make_monitor(running=True, task_done=False)) is True


def test_monitor_not_running_when_none():
    from llc.health.probe import _is_liveness_monitor_running

    assert _is_liveness_monitor_running(None) is False


def test_monitor_not_running_when_stopped():
    from llc.health.probe import _is_liveness_monitor_running

    assert _is_liveness_monitor_running(_make_monitor(running=False)) is False


# ---------------------------------------------------------------------------
# HeartbeatScheduler.is_running property (CR-4)
# ---------------------------------------------------------------------------


def test_heartbeat_scheduler_is_running_when_task_alive():
    from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler

    s = HeartbeatScheduler()
    s._running = True
    mock_task = MagicMock(spec=asyncio.Task)
    mock_task.done.return_value = False
    s._task = mock_task
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
