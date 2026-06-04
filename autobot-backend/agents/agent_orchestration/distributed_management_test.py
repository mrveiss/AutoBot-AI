# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for DistributedAgentManager work-stealing logic (Issue #2109),
circuit breaker logic (Issue #4694), and Redis state persistence (Issue #6479).

Most tests are pure in-memory; Redis calls are patched to AsyncMock.
Integration tests for persistence use _patch_persistence() context manager.
"""

from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.time_utils import now_utc

from .distributed_management import DistributedAgentManager
from .types import CircuitState, DistributedAgentInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_PERSISTENCE_MODULE = "agents.agent_orchestration.distributed_management"


@asynccontextmanager
async def _patch_persistence():
    """Patch all state_persistence async helpers to AsyncMock no-ops.

    Returns a dict of mock objects keyed by function name so callers can
    inspect call counts / arguments.
    """
    mocks = {
        "persist_task_assigned": AsyncMock(),
        "persist_task_progress": AsyncMock(),
        "persist_task_reassignment": AsyncMock(),
        "delete_task_state": AsyncMock(),
        "delete_task_timing_state": AsyncMock(),
        "load_task_state": AsyncMock(return_value=({}, {}, {})),
    }
    with patch.multiple(_PERSISTENCE_MODULE, **mocks):
        yield mocks


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
        last_health_check=now_utc(),
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
    """Directly set up task assignment state without going through async methods.

    This is a test-only helper that mutates internal dicts directly so that
    pure in-memory tests don't need to await or mock Redis.
    """
    if agent_id in mgr.distributed_agents:
        mgr.distributed_agents[agent_id].active_tasks.add(task_id)
    ts = now_utc()
    if assigned_seconds_ago:
        ts = ts - timedelta(seconds=assigned_seconds_ago)
    mgr._task_assigned_at[task_id] = ts


# ---------------------------------------------------------------------------
# _is_task_stale — unit tests
# ---------------------------------------------------------------------------


class TestIsTaskStale:
    def test_unknown_task_is_not_stale(self):
        mgr = _make_manager()
        assert mgr._is_task_stale("nonexistent", now_utc()) is False

    def test_task_within_grace_period_is_not_stale(self):
        mgr = _make_manager(stale_task_timeout_seconds=300, grace_period_seconds=300)
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=10)
        assert mgr._is_task_stale("t1", now_utc()) is False

    def test_task_beyond_timeout_but_within_grace_is_not_stale(self):
        # grace_period_seconds > age → still protected even if age > timeout
        mgr = _make_manager(stale_task_timeout_seconds=5, grace_period_seconds=600)
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=100)
        assert mgr._is_task_stale("t1", now_utc()) is False

    def test_task_beyond_timeout_and_grace_is_stale(self):
        mgr = _make_manager(stale_task_timeout_seconds=60, grace_period_seconds=30)
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=90)
        assert mgr._is_task_stale("t1", now_utc()) is True

    def test_task_with_recent_progress_is_not_stale(self):
        mgr = _make_manager(
            stale_task_timeout_seconds=60,
            grace_period_seconds=30,
            progress_ttl_seconds=120,
        )
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=90)
        mgr._task_last_progress["t1"] = now_utc()  # direct mutation — bypass async
        assert mgr._is_task_stale("t1", now_utc()) is False

    def test_task_with_old_progress_is_stale(self):
        mgr = _make_manager(
            stale_task_timeout_seconds=60,
            grace_period_seconds=30,
            progress_ttl_seconds=30,
        )
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=120)
        # Backdate last progress to 60 s ago (older than progress_ttl_seconds=30)
        mgr._task_last_progress["t1"] = now_utc() - timedelta(seconds=60)
        assert mgr._is_task_stale("t1", now_utc()) is True

    def test_max_reassignments_exceeded_prevents_stealing(self):
        mgr = _make_manager(stale_task_timeout_seconds=10, grace_period_seconds=5, max_reassignments=2)
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=300)
        mgr._task_reassignment_count["t1"] = 2  # already at limit
        assert mgr._is_task_stale("t1", now_utc()) is False


# ---------------------------------------------------------------------------
# _collect_stale_tasks
# ---------------------------------------------------------------------------


class TestCollectStaleTasks:
    def test_returns_empty_when_no_agents(self):
        mgr = _make_manager()
        assert mgr._collect_stale_tasks(now_utc()) == []

    def test_returns_stale_pair(self):
        mgr = _make_manager(stale_task_timeout_seconds=60, grace_period_seconds=30)
        _register_agent(mgr, "agent-1")
        _assign_task(mgr, "agent-1", "task-A", assigned_seconds_ago=120)
        pairs = mgr._collect_stale_tasks(now_utc())
        assert ("agent-1", "task-A") in pairs

    def test_skips_fresh_tasks(self):
        mgr = _make_manager(stale_task_timeout_seconds=300, grace_period_seconds=300)
        _register_agent(mgr, "agent-1")
        _assign_task(mgr, "agent-1", "task-B", assigned_seconds_ago=5)
        assert mgr._collect_stale_tasks(now_utc()) == []

    def test_multiple_agents_multiple_tasks(self):
        mgr = _make_manager(stale_task_timeout_seconds=60, grace_period_seconds=30)
        for aid in ("a1", "a2"):
            _register_agent(mgr, aid)
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=120)  # stale
        _assign_task(mgr, "a1", "t2", assigned_seconds_ago=5)  # fresh
        _assign_task(mgr, "a2", "t3", assigned_seconds_ago=200)  # stale
        pairs = mgr._collect_stale_tasks(now_utc())
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
        mgr._task_assigned_at["t1"] = now_utc() - timedelta(seconds=400)
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
        mgr = _make_manager(stale_task_timeout_seconds=10, grace_period_seconds=5, max_reassignments=1)
        _register_agent(mgr, "a1")
        _assign_task(mgr, "a1", "t1", assigned_seconds_ago=300)
        mgr._task_reassignment_count["t1"] = 1  # already at limit
        count = await mgr._detect_and_steal_stale_tasks()
        assert count == 0


# ---------------------------------------------------------------------------
# add_active_task / remove_active_task tracking
# ---------------------------------------------------------------------------


class TestTaskTrackingIntegration:
    @pytest.mark.asyncio
    async def test_add_active_task_records_assigned_at(self):
        async with _patch_persistence() as mocks:
            mgr = _make_manager()
            _register_agent(mgr, "a1")
            before = now_utc()
            await mgr.add_active_task("a1", "t1")
            after = now_utc()
            assert "t1" in mgr._task_assigned_at
            assert before <= mgr._task_assigned_at["t1"] <= after
            mocks["persist_task_assigned"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remove_active_task_clears_all_tracking(self):
        async with _patch_persistence():
            mgr = _make_manager()
            _register_agent(mgr, "a1")
            await mgr.add_active_task("a1", "t1")
            await mgr.report_task_progress("t1")
            mgr._task_reassignment_count["t1"] = 2
            await mgr.remove_active_task("a1", "t1")
            assert "t1" not in mgr._task_assigned_at
            assert "t1" not in mgr._task_last_progress
            assert "t1" not in mgr._task_reassignment_count

    @pytest.mark.asyncio
    async def test_report_task_progress_updates_timestamp(self):
        async with _patch_persistence():
            mgr = _make_manager()
            _register_agent(mgr, "a1")
            await mgr.add_active_task("a1", "t1")
            before = now_utc()
            await mgr.report_task_progress("t1")
            after = now_utc()
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
        _assign_task(mgr, "a1", "t1")
        mgr._task_reassignment_count["t1"] = 2
        stats = mgr.get_statistics()
        assert stats["a1"]["task_reassignment_counts"]["t1"] == 2


# ---------------------------------------------------------------------------
# Circuit breaker helpers
# ---------------------------------------------------------------------------


def _make_cb_manager(
    failure_threshold: int = 3,
    recovery_timeout_seconds: int = 300,
) -> DistributedAgentManager:
    """Return a manager configured for circuit breaker tests."""
    return DistributedAgentManager(
        builtin_agents={},
        health_check_interval=30.0,
        circuit_failure_threshold=failure_threshold,
        circuit_recovery_timeout_seconds=recovery_timeout_seconds,
    )


def _make_health_stub(status: str = "healthy") -> MagicMock:
    """Return a minimal AgentHealth stub."""
    h = MagicMock()
    h.status.value = status
    return h


# ---------------------------------------------------------------------------
# Circuit breaker — _process_health_result / state transitions (Issue #4694)
# ---------------------------------------------------------------------------


class TestCircuitBreakerHealthTransitions:
    def test_healthy_result_resets_failure_count(self):
        mgr = _make_cb_manager(failure_threshold=3)
        _register_agent(mgr, "a1")
        mgr.distributed_agents["a1"].circuit_failure_count = 2
        mgr._process_health_result("a1", _make_health_stub("healthy"), None)
        assert mgr.distributed_agents["a1"].circuit_failure_count == 0

    def test_consecutive_failures_open_circuit(self):
        mgr = _make_cb_manager(failure_threshold=3)
        _register_agent(mgr, "a1")
        for _ in range(3):
            mgr._process_health_result("a1", _make_health_stub("unhealthy"), None)
        info = mgr.distributed_agents["a1"]
        assert info.circuit_state == CircuitState.OPEN
        assert info.circuit_opened_at is not None

    def test_failure_below_threshold_does_not_open_circuit(self):
        mgr = _make_cb_manager(failure_threshold=3)
        _register_agent(mgr, "a1")
        for _ in range(2):
            mgr._process_health_result("a1", _make_health_stub("unhealthy"), None)
        assert mgr.distributed_agents["a1"].circuit_state == CircuitState.CLOSED

    def test_exception_in_health_check_counts_as_failure(self):
        mgr = _make_cb_manager(failure_threshold=2)
        _register_agent(mgr, "a1")
        mgr._process_health_result("a1", None, RuntimeError("timeout"))
        mgr._process_health_result("a1", None, RuntimeError("timeout"))
        assert mgr.distributed_agents["a1"].circuit_state == CircuitState.OPEN

    def test_healthy_after_open_half_open_closes_circuit(self):
        mgr = _make_cb_manager(failure_threshold=3)
        _register_agent(mgr, "a1")
        info = mgr.distributed_agents["a1"]
        info.circuit_state = CircuitState.HALF_OPEN
        info.circuit_failure_count = 3
        mgr._process_health_result("a1", _make_health_stub("healthy"), None)
        assert info.circuit_state == CircuitState.CLOSED
        assert info.circuit_failure_count == 0
        assert info.circuit_opened_at is None

    def test_failure_in_half_open_reopens_circuit(self):
        mgr = _make_cb_manager(failure_threshold=3)
        _register_agent(mgr, "a1")
        info = mgr.distributed_agents["a1"]
        info.circuit_state = CircuitState.HALF_OPEN
        info.circuit_failure_count = 3
        original_opened_at = now_utc() - timedelta(seconds=600)
        info.circuit_opened_at = original_opened_at
        mgr._process_health_result("a1", _make_health_stub("degraded"), None)
        assert info.circuit_state == CircuitState.OPEN
        # opened_at must be reset (new backoff window)
        assert info.circuit_opened_at is not None
        assert info.circuit_opened_at > original_opened_at


# ---------------------------------------------------------------------------
# Circuit breaker — get_healthy_agents routing exclusion (Issue #4694)
# ---------------------------------------------------------------------------


class TestCircuitBreakerRouting:
    def test_closed_healthy_agent_is_included(self):
        mgr = _make_cb_manager()
        _register_agent(mgr, "a1")
        agents = mgr.get_healthy_agents()
        assert len(agents) == 1

    def test_open_agent_excluded_from_routing(self):
        mgr = _make_cb_manager(recovery_timeout_seconds=300)
        _register_agent(mgr, "a1")
        info = mgr.distributed_agents["a1"]
        info.circuit_state = CircuitState.OPEN
        info.circuit_opened_at = now_utc()
        assert mgr.get_healthy_agents() == []

    def test_open_agent_promoted_to_half_open_after_backoff(self):
        mgr = _make_cb_manager(recovery_timeout_seconds=60)
        _register_agent(mgr, "a1")
        info = mgr.distributed_agents["a1"]
        info.circuit_state = CircuitState.OPEN
        info.circuit_opened_at = now_utc() - timedelta(seconds=120)
        agents = mgr.get_healthy_agents()
        assert info.circuit_state == CircuitState.HALF_OPEN
        assert len(agents) == 1

    def test_half_open_allows_single_probe_then_blocks(self):
        mgr = _make_cb_manager()
        _register_agent(mgr, "a1")
        info = mgr.distributed_agents["a1"]
        info.circuit_state = CircuitState.HALF_OPEN

        # First call: probe dispatched.
        agents_first = mgr.get_healthy_agents()
        assert len(agents_first) == 1
        assert info.circuit_probe_dispatched_at is not None

        # Second call: probe already dispatched — excluded.
        agents_second = mgr.get_healthy_agents()
        assert agents_second == []

    def test_unhealthy_closed_agent_excluded(self):
        mgr = _make_cb_manager()
        _register_agent(mgr, "a1")
        mgr.distributed_agents["a1"].health.status.value = "degraded"
        assert mgr.get_healthy_agents() == []


# ---------------------------------------------------------------------------
# Circuit breaker — get_statistics exposes circuit state (Issue #4694)
# ---------------------------------------------------------------------------


class TestCircuitBreakerStatistics:
    def test_circuit_state_in_agent_stats(self):
        mgr = _make_cb_manager(failure_threshold=2, recovery_timeout_seconds=120)
        _register_agent(mgr, "a1")
        stats = mgr.get_statistics()
        a1_stats = stats["a1"]
        assert a1_stats["circuit_state"] == "closed"
        assert a1_stats["circuit_failure_count"] == 0
        assert a1_stats["circuit_opened_at"] is None

    def test_circuit_breaker_section_present(self):
        mgr = _make_cb_manager(failure_threshold=4, recovery_timeout_seconds=600)
        stats = mgr.get_statistics()
        cb = stats["_circuit_breaker"]
        assert cb["failure_threshold"] == 4
        assert cb["recovery_timeout_seconds"] == 600

    def test_open_circuit_exposes_opened_at(self):
        mgr = _make_cb_manager()
        _register_agent(mgr, "a1")
        opened_at = now_utc()
        info = mgr.distributed_agents["a1"]
        info.circuit_state = CircuitState.OPEN
        info.circuit_opened_at = opened_at
        stats = mgr.get_statistics()
        assert stats["a1"]["circuit_state"] == "open"
        assert stats["a1"]["circuit_opened_at"] == opened_at.isoformat()


# ---------------------------------------------------------------------------
# Redis persistence — Issue #6479
# ---------------------------------------------------------------------------


class TestRedisPersistence:
    """Verify that task-assignment state is written to Redis and rehydrated on restart."""

    @pytest.mark.asyncio
    async def test_add_active_task_persists_to_redis(self):
        async with _patch_persistence() as mocks:
            mgr = _make_manager()
            _register_agent(mgr, "a1")
            await mgr.add_active_task("a1", "t1")
            mocks["persist_task_assigned"].assert_awaited_once_with(
                mgr._deployment_id, "t1", mgr._task_assigned_at["t1"]
            )

    @pytest.mark.asyncio
    async def test_remove_active_task_deletes_redis_state(self):
        async with _patch_persistence() as mocks:
            mgr = _make_manager()
            _register_agent(mgr, "a1")
            await mgr.add_active_task("a1", "t1")
            await mgr.remove_active_task("a1", "t1")
            mocks["delete_task_state"].assert_awaited_with(mgr._deployment_id, "t1")

    @pytest.mark.asyncio
    async def test_report_task_progress_persists_to_redis(self):
        async with _patch_persistence() as mocks:
            mgr = _make_manager()
            _register_agent(mgr, "a1")
            await mgr.add_active_task("a1", "t1")
            await mgr.report_task_progress("t1")
            mocks["persist_task_progress"].assert_awaited_with(mgr._deployment_id, "t1", mgr._task_last_progress["t1"])

    @pytest.mark.asyncio
    async def test_rehydrate_restores_assigned_at_from_redis(self):
        """Grace period must continue from original assignment after restart."""
        original_assigned_at = now_utc() - timedelta(seconds=250)

        async def _load_state(dep_id: str):
            return ({"task-x": original_assigned_at}, {}, {})

        with patch(f"{_PERSISTENCE_MODULE}.load_task_state", side_effect=_load_state):
            with patch.multiple(
                _PERSISTENCE_MODULE,
                persist_task_assigned=AsyncMock(),
                persist_task_progress=AsyncMock(),
                persist_task_reassignment=AsyncMock(),
                delete_task_state=AsyncMock(),
                delete_task_timing_state=AsyncMock(),
            ):
                mgr = _make_manager(stale_task_timeout_seconds=200, grace_period_seconds=60)
                await mgr._rehydrate_from_redis()

        assert "task-x" in mgr._task_assigned_at
        assert mgr._task_assigned_at["task-x"] == original_assigned_at
        # Task was assigned 250s ago; grace=60s; timeout=200s → stale
        assert mgr._is_task_stale("task-x", now_utc()) is True

    @pytest.mark.asyncio
    async def test_reassign_task_persists_count_clears_timing(self):
        """_reassign_task must update the count and clear only timing entries in Redis."""
        async with _patch_persistence() as mocks:
            mgr = _make_manager()
            _register_agent(mgr, "a1")
            _assign_task(mgr, "a1", "t1", assigned_seconds_ago=400)
            await mgr._reassign_task("a1", "t1")
            # Count should be persisted
            mocks["persist_task_reassignment"].assert_awaited()
            # Only timing state (not full state) deleted
            mocks["delete_task_timing_state"].assert_awaited_with(mgr._deployment_id, "t1")
            # Full delete_task_state should NOT be called on reassign (count survives)
            mocks["delete_task_state"].assert_not_awaited()
