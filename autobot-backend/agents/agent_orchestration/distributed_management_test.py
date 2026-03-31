# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for DistributedAgentManager work-stealing logic (Issue #2109).

All tests are pure in-memory; no Redis, no actual agents, no network I/O.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from .distributed_management import DistributedAgentManager
from .types import DistributedAgentInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(
    stale_task_timeout_seconds: int = 300,
    grace_period_seconds: int = 300,
    max_reassignments: int = 3,
    progress_ttl_seconds: int = 60,
) -> DistributedAgentManager:
    """Return a pre-configured manager with no builtin agents."""
    return DistributedAgentManager(
        builtin_agents={},
        health_check_interval=30.0,
        stale_task_timeout_seconds=stale_task_timeout_seconds,
        grace_period_seconds=grace_period_seconds,
        max_reassignments=max_reassignments,
        progress_ttl_seconds=progress_ttl_seconds,
    )


def _make_agent_info() -> DistributedAgentInfo:
    """Return a minimal stub DistributedAgentInfo."""
    health_stub = MagicMock()
    health_stub.status.value = "healthy"
    agent_stub = MagicMock()
    agent_stub.agent_type = "test_agent"
    return DistributedAgentInfo(
        agent=agent_stub,
        health=health_stub,
        last_health_check=datetime.now(timezone.utc),
        active_tasks=set(),
    )


def _register_agent(mgr: DistributedAgentManager, agent_id: str) -> DistributedAgentInfo:
    """Register a stub agent directly into the manager's dict."""
    info = _make_agent_info()
    mgr.distributed_agents[agent_id] = info
    return info


def _assign_task(
    mgr: DistributedAgentManager,
    agent_id: str,
    task_id: str,
    assigned_seconds_ago: float = 0.0,
) -> None:
    """Add a task to an agent and backdating its assignment timestamp."""
    mgr.add_active_task(agent_id, task_id)
    if assigned_seconds_ago:
        mgr._task_assigned_at[task_id] = datetime.now(timezone.utc) - timedelta(
            seconds=assigned_seconds_ago
        )


# ---------------------------------------------------------------------------
# _is_task_stale — unit tests
# ---------------------------------------------------------------------------


class TestIsTaskStale:
    def test_unknown_task_is_not_stale(self):
        mgr = _make_manager()
        assert mgr._is_task_stale("nonexistent", datetime.now(timezone.utc)) is False

    def test_task_within_grace_period_is_not_stale(self):
        mgr = _make_manager(stale_task_timeout_seconds=300, grace_period_seconds=300)
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=10)
        assert mgr._is_task_stale("t1", datetime.now(timezone.utc)) is False

    def test_task_beyond_timeout_but_within_grace_is_not_stale(self):
        # grace_period_seconds > age → still protected even if age > timeout
        mgr = _make_manager(stale_task_timeout_seconds=5, grace_period_seconds=600)
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=100)
        assert mgr._is_task_stale("t1", datetime.now(timezone.utc)) is False

    def test_task_beyond_timeout_and_grace_is_stale(self):
        mgr = _make_manager(stale_task_timeout_seconds=60, grace_period_seconds=30)
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=90)
        assert mgr._is_task_stale("t1", datetime.now(timezone.utc)) is True

    def test_task_with_recent_progress_is_not_stale(self):
        mgr = _make_manager(
            stale_task_timeout_seconds=60,
            grace_period_seconds=30,
            progress_ttl_seconds=120,
        )
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=90)
        mgr.report_task_progress("t1")  # progress just now
        assert mgr._is_task_stale("t1", datetime.now(timezone.utc)) is False

    def test_task_with_old_progress_is_stale(self):
        mgr = _make_manager(
            stale_task_timeout_seconds=60,
            grace_period_seconds=30,
            progress_ttl_seconds=30,
        )
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=120)
        # Backdate last progress to 60 s ago (older than progress_ttl_seconds=30)
        mgr._task_last_progress["t1"] = datetime.now(timezone.utc) - timedelta(seconds=60)
        assert mgr._is_task_stale("t1", datetime.now(timezone.utc)) is True

    def test_max_reassignments_exceeded_prevents_stealing(self):
        mgr = _make_manager(
            stale_task_timeout_seconds=10, grace_period_seconds=5, max_reassignments=2
        )
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=300)
        mgr._task_reassignment_count["t1"] = 2  # already at limit
        assert mgr._is_task_stale("t1", datetime.now(timezone.utc)) is False


# ---------------------------------------------------------------------------
# _collect_stale_tasks
# ---------------------------------------------------------------------------


class TestCollectStaleTasks:
    def test_returns_empty_when_no_agents(self):
        mgr = _make_manager()
        assert mgr._collect_stale_tasks(datetime.now(timezone.utc)) == []

    def test_returns_stale_pair(self):
        mgr = _make_manager(stale_task_timeout_seconds=60, grace_period_seconds=30)
        _register_agent(mgr, "agent-1")
        _assign_task(mgr, "agent-1", "task-A", assigned_seconds_ago=120)
        pairs = mgr._collect_stale_tasks(datetime.now(timezone.utc))
        assert ("agent-1", "task-A") in pairs

    def test_skips_fresh_tasks(self):
        mgr = _make_manager(stale_task_timeout_seconds=300, grace_period_seconds=300)
        _register_agent(mgr, "agent-1")
        _assign_task(mgr, "agent-1", "task-B", assigned_seconds_ago=5)
        assert mgr._collect_stale_tasks(datetime.now(timezone.utc)) == []

    def test_multiple_agents_multiple_tasks(self):
        mgr = _make_manager(stale_task_timeout_seconds=60, grace_period_seconds=30)
        for aid in ("a1", "a2"):
            _register_agent(mgr, aid)
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=120)  # stale
        _assign_task(mgr, "a1", "t2", assigned_seconds_ago=5)   # fresh
        _assign_task(mgr, "a2", "t3", assigned_seconds_ago=200)  # stale
        pairs = mgr._collect_stale_tasks(datetime.now(timezone.utc))
        assert ("a1", "t1") in pairs
        assert ("a2", "t3") in pairs
        assert all(p[1] != "t2" for p in pairs)


# ---------------------------------------------------------------------------
# _reassign_task
# ---------------------------------------------------------------------------


class TestReassignTask:
    @pytest.mark.asyncio
    async def test_unknown_agent_returns_false(self):
        mgr = _make_manager()
        result = await mgr._reassign_task("ghost", "t1")
        assert result is False

    @pytest.mark.asyncio
    async def test_task_removed_from_agent(self):
        mgr = _make_manager()
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=400)
        await mgr._reassign_task("a1", "t1")
        assert "t1" not in mgr.distributed_agents["a1"].active_tasks

    @pytest.mark.asyncio
    async def test_reassignment_count_incremented(self):
        mgr = _make_manager()
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=400)
        await mgr._reassign_task("a1", "t1")
        assert mgr._task_reassignment_count["t1"] == 1
        # Simulate re-assignment by manually adding task back + calling again
        mgr.distributed_agents["a1"].active_tasks.add("t1")
        mgr._task_assigned_at["t1"] = datetime.now(timezone.utc) - timedelta(seconds=400)
        await mgr._reassign_task("a1", "t1")
        assert mgr._task_reassignment_count["t1"] == 2

    @pytest.mark.asyncio
    async def test_assigned_at_cleared_after_reassignment(self):
        mgr = _make_manager()
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=400)
        await mgr._reassign_task("a1", "t1")
        assert "t1" not in mgr._task_assigned_at

    @pytest.mark.asyncio
    async def test_event_emitter_called(self):
        emitter = AsyncMock()
        mgr = _make_manager()
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=400)
        await mgr._reassign_task("a1", "t1", event_emitter=emitter)
        emitter.assert_awaited_once()
        call_args = emitter.call_args
        assert call_args[0][0] == "global"
        assert call_args[0][1] == "task_reassigned"
        payload = call_args[0][2]
        assert payload["task_id"] == "t1"
        assert payload["source_agent_id"] == "a1"

    @pytest.mark.asyncio
    async def test_emitter_failure_does_not_raise(self):
        async def bad_emitter(*_args, **_kwargs):
            raise RuntimeError("boom")

        mgr = _make_manager()
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=400)
        # Should not raise even if emitter fails
        result = await mgr._reassign_task("a1", "t1", event_emitter=bad_emitter)
        assert result is True


# ---------------------------------------------------------------------------
# _detect_and_steal_stale_tasks
# ---------------------------------------------------------------------------


class TestDetectAndStealStaleTasks:
    @pytest.mark.asyncio
    async def test_returns_zero_when_nothing_stale(self):
        mgr = _make_manager()
        count = await mgr._detect_and_steal_stale_tasks()
        assert count == 0

    @pytest.mark.asyncio
    async def test_steals_one_stale_task(self):
        mgr = _make_manager(stale_task_timeout_seconds=60, grace_period_seconds=30)
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=120)
        count = await mgr._detect_and_steal_stale_tasks()
        assert count == 1
        assert "t1" not in mgr.distributed_agents["a1"].active_tasks

    @pytest.mark.asyncio
    async def test_steals_multiple_stale_tasks_across_agents(self):
        mgr = _make_manager(stale_task_timeout_seconds=60, grace_period_seconds=30)
        for aid in ("a1", "a2"):
            _register_agent(mgr, aid)
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=120)
        _assign_task(mgr, "a2", "t2", assigned_seconds_ago=200)
        _assign_task(mgr, "a1", "t3", assigned_seconds_ago=5)  # fresh
        count = await mgr._detect_and_steal_stale_tasks()
        assert count == 2

    @pytest.mark.asyncio
    async def test_grace_period_prevents_stealing(self):
        mgr = _make_manager(stale_task_timeout_seconds=60, grace_period_seconds=600)
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=300)
        count = await mgr._detect_and_steal_stale_tasks()
        assert count == 0

    @pytest.mark.asyncio
    async def test_max_reassignments_stops_stealing(self):
        mgr = _make_manager(
            stale_task_timeout_seconds=10, grace_period_seconds=5, max_reassignments=1
        )
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=300)
        mgr._task_reassignment_count["t1"] = 1  # already at limit
        count = await mgr._detect_and_steal_stale_tasks()
        assert count == 0


# ---------------------------------------------------------------------------
# add_active_task / remove_active_task tracking
# ---------------------------------------------------------------------------


class TestTaskTrackingIntegration:
    def test_add_active_task_records_assigned_at(self):
        mgr = _make_manager()
        _register_agent(mgr, "a1")
        before = datetime.now(timezone.utc)
        mgr.add_active_task("a1", "t1")
        after = datetime.now(timezone.utc)
        assert "t1" in mgr._task_assigned_at
        assert before <= mgr._task_assigned_at["t1"] <= after

    def test_remove_active_task_clears_all_tracking(self):
        mgr = _make_manager()
        _register_agent(mgr, "a1")
        mgr.add_active_task("a1", "t1")
        mgr.report_task_progress("t1")
        mgr._task_reassignment_count["t1"] = 2
        mgr.remove_active_task("a1", "t1")
        assert "t1" not in mgr._task_assigned_at
        assert "t1" not in mgr._task_last_progress
        assert "t1" not in mgr._task_reassignment_count

    def test_report_task_progress_updates_timestamp(self):
        mgr = _make_manager()
        _register_agent(mgr, "a1")
        mgr.add_active_task("a1", "t1")
        before = datetime.now(timezone.utc)
        mgr.report_task_progress("t1")
        after = datetime.now(timezone.utc)
        assert before <= mgr._task_last_progress["t1"] <= after


# ---------------------------------------------------------------------------
# get_statistics — work-stealing fields present
# ---------------------------------------------------------------------------


class TestGetStatisticsWorkStealing:
    def test_work_stealing_section_present(self):
        mgr = _make_manager(
            stale_task_timeout_seconds=120,
            grace_period_seconds=60,
            max_reassignments=2,
            progress_ttl_seconds=45,
        )
        stats = mgr.get_statistics()
        ws = stats["_work_stealing"]
        assert ws["stale_task_timeout_seconds"] == 120
        assert ws["grace_period_seconds"] == 60
        assert ws["max_reassignments"] == 2
        assert ws["progress_ttl_seconds"] == 45

    def test_task_reassignment_counts_in_agent_stats(self):
        mgr = _make_manager()
        _register_agent(mgr, "a1")
        mgr.add_active_task("a1", "t1")
        mgr._task_reassignment_count["t1"] = 2
        stats = mgr.get_statistics()
        assert stats["a1"]["task_reassignment_counts"]["t1"] == 2
