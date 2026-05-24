# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for LLC health probe (GH#8259)."""

from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scheduler(*, running: bool = True, task_done: bool = False) -> MagicMock:
    s = MagicMock()
    s._running = running
    task = MagicMock()
    task.done.return_value = task_done
    s._task = task if running else None
    return s


def _make_monitor(*, running: bool = True, task_done: bool = False) -> MagicMock:
    m = MagicMock()
    m._running = running
    task = MagicMock()
    task.done.return_value = task_done
    m._task = task if running else None
    return m


def _base_metrics(**overrides) -> dict:
    base = {
        "heartbeat_scheduler_running": True,
        "liveness_monitor_running": True,
        "scheduler_last_tick_age_seconds": 2.5,
        "agents_overdue_heartbeat": 0,
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

    s = _make_scheduler(running=True, task_done=True)
    assert _is_scheduler_running(s) is False


def test_scheduler_not_running_when_no_task():
    from llc.health.probe import _is_scheduler_running

    s = _make_scheduler(running=True)
    s._task = None
    assert _is_scheduler_running(s) is False


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
# _compute_status
# ---------------------------------------------------------------------------


def test_status_ok_all_nominal():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics()) == "ok"


def test_status_down_scheduler_stopped():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics(heartbeat_scheduler_running=False)) == "down"


def test_status_down_agents_overdue():
    from llc.health.probe import _compute_status

    assert _compute_status(_base_metrics(agents_overdue_heartbeat=1)) == "down"


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
        assert result.data["agents_overdue_heartbeat"] == 0


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
