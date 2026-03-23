# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for MeshBrainScheduler and mesh_brain API endpoints (#1994, #2120)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from services.mesh_brain.scheduler import JobStatus, MeshBrainScheduler

# =============================================================================
# Helpers
# =============================================================================


def _make_scheduler(**components) -> MeshBrainScheduler:
    """Return a MeshBrainScheduler with optional component overrides."""
    defaults = {
        "edge_learner": None,
        "edge_sync": None,
        "edge_discoverer": None,
        "mesh_pruner": None,
        "node_promoter": None,
        "mesh_db": None,
    }
    defaults.update(components)
    return MeshBrainScheduler(**defaults)


def _make_component(method: str = "sync") -> AsyncMock:
    """Return a mock component whose relevant method is an AsyncMock."""
    comp = AsyncMock()
    setattr(comp, method, AsyncMock())
    return comp


# =============================================================================
# Initialisation
# =============================================================================


class TestMeshBrainSchedulerInit:
    def test_init_creates_job_statuses(self):
        """All five expected jobs are present in _jobs after construction."""
        scheduler = _make_scheduler()
        assert set(scheduler._jobs.keys()) == {
            "edge_learner",
            "edge_sync",
            "node_promoter",
            "edge_discoverer",
            "mesh_pruner",
        }

    def test_init_job_statuses_are_idle(self):
        """Every JobStatus starts with no run history and is_running=False."""
        scheduler = _make_scheduler()
        for job in scheduler._jobs.values():
            assert isinstance(job, JobStatus)
            assert job.last_run is None
            assert job.last_result is None
            assert job.is_running is False

    def test_init_not_running(self):
        """Scheduler is not running until start() is called."""
        scheduler = _make_scheduler()
        assert scheduler._running is False


# =============================================================================
# get_status
# =============================================================================


class TestGetStatus:
    def test_get_status_returns_all_jobs(self):
        """status dict contains exactly five job entries."""
        scheduler = _make_scheduler()
        status = scheduler.get_status()
        assert len(status["jobs"]) == 5

    def test_get_status_running_reflects_state(self):
        """'running' key mirrors the scheduler's _running flag."""
        scheduler = _make_scheduler()
        assert status_running(scheduler) is False
        scheduler._running = True
        assert status_running(scheduler) is True

    def test_get_status_component_available_false_when_none(self):
        """component_available is False when no component was injected."""
        scheduler = _make_scheduler()
        status = scheduler.get_status()
        for job in status["jobs"].values():
            assert job["component_available"] is False

    def test_get_status_component_available_true_when_injected(self):
        """component_available is True for the injected edge_sync component."""
        scheduler = _make_scheduler(edge_sync=_make_component("sync"))
        status = scheduler.get_status()
        assert status["jobs"]["edge_sync"]["component_available"] is True
        assert status["jobs"]["node_promoter"]["component_available"] is False


def status_running(scheduler: MeshBrainScheduler) -> bool:
    return scheduler.get_status()["running"]


# =============================================================================
# _execute_job
# =============================================================================


class TestExecuteJob:
    @pytest.mark.asyncio
    async def test_execute_job_success_updates_status(self):
        """last_result becomes 'success' and is_running resets to False after a clean run."""
        sync_comp = _make_component("sync")
        scheduler = _make_scheduler(edge_sync=sync_comp)
        await scheduler._execute_job("edge_sync")

        job = scheduler._jobs["edge_sync"]
        assert job.last_result == "success"
        assert job.is_running is False
        assert job.last_run is not None
        sync_comp.sync.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_job_failure_logs_evolution(self):
        """last_result becomes 'failed' and log_evolution is called when a job raises."""
        sync_comp = AsyncMock()
        sync_comp.sync = AsyncMock(side_effect=RuntimeError("db down"))
        mesh_db = AsyncMock()
        mesh_db.log_evolution = AsyncMock()

        scheduler = _make_scheduler(edge_sync=sync_comp, mesh_db=mesh_db)
        await scheduler._execute_job("edge_sync")

        assert scheduler._jobs["edge_sync"].last_result == "failed"
        assert scheduler._jobs["edge_sync"].is_running is False
        mesh_db.log_evolution.assert_awaited_once()
        call_args = mesh_db.log_evolution.call_args[0]
        assert call_args[0] == "job_failed"
        assert call_args[4] == "edge_sync"

    @pytest.mark.asyncio
    async def test_execute_job_failure_no_mesh_db_does_not_raise(self):
        """A job failure without mesh_db does not propagate an exception."""
        sync_comp = AsyncMock()
        sync_comp.sync = AsyncMock(side_effect=ValueError("fail"))
        scheduler = _make_scheduler(edge_sync=sync_comp)
        # Should complete without raising
        await scheduler._execute_job("edge_sync")
        assert scheduler._jobs["edge_sync"].last_result == "failed"

    @pytest.mark.asyncio
    async def test_execute_job_skips_missing_component(self):
        """_execute_job is a no-op and raises nothing when no component is injected."""
        scheduler = _make_scheduler()
        await scheduler._execute_job("edge_sync")
        assert scheduler._jobs["edge_sync"].last_result is None

    @pytest.mark.asyncio
    async def test_execute_job_node_promoter_calls_evaluate(self):
        """node_promoter job invokes .evaluate() on its component."""
        promoter = _make_component("evaluate")
        scheduler = _make_scheduler(node_promoter=promoter)
        await scheduler._execute_job("node_promoter")
        promoter.evaluate.assert_awaited_once()


# =============================================================================
# start / stop
# =============================================================================


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_creates_tasks_for_available_components(self):
        """asyncio.Task entries are created for each injected component."""
        sync_comp = _make_component("sync")
        promoter_comp = _make_component("evaluate")

        scheduler = _make_scheduler(edge_sync=sync_comp, node_promoter=promoter_comp)

        with _patch_sleep():
            await scheduler.start()

        assert "edge_sync" in scheduler._tasks
        assert "node_promoter" in scheduler._tasks
        assert "edge_learner" not in scheduler._tasks
        assert scheduler._running is True

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_creates_realtime_task_for_edge_learner(self):
        """edge_learner gets a task when that component is injected."""
        learner = AsyncMock()
        learner.consume_feedback_stream = AsyncMock()

        scheduler = _make_scheduler(edge_learner=learner)

        with _patch_sleep():
            await scheduler.start()

        assert "edge_learner" in scheduler._tasks
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self):
        """stop() cancels all tasks and clears the _tasks dict."""
        mock_task_a = MagicMock(spec=asyncio.Task)
        mock_task_b = MagicMock(spec=asyncio.Task)

        scheduler = _make_scheduler()
        scheduler._running = True
        scheduler._tasks = {"edge_sync": mock_task_a, "node_promoter": mock_task_b}

        await scheduler.stop()

        mock_task_a.cancel.assert_called_once()
        mock_task_b.cancel.assert_called_once()
        assert scheduler._tasks == {}
        assert scheduler._running is False


# =============================================================================
# API endpoint helpers (mesh_brain.py)
# =============================================================================


class TestMeshBrainApiHelpers:
    def test_health_endpoint_returns_healthy_when_no_failed_jobs(self):
        """_build_health_response returns healthy=True when no jobs have failed."""
        from api.mesh_brain import _build_health_response

        status = {
            "running": True,
            "jobs": {
                "edge_sync": {"last_result": "success"},
                "node_promoter": {"last_result": None},
            },
        }
        result = _build_health_response(status)
        assert result["healthy"] is True
        assert result["failed_jobs"] == []
        assert result["running"] is True

    def test_health_endpoint_returns_unhealthy_when_job_failed(self):
        """_build_health_response returns healthy=False and lists the failed job."""
        from api.mesh_brain import _build_health_response

        status = {
            "running": True,
            "jobs": {
                "edge_sync": {"last_result": "failed"},
                "node_promoter": {"last_result": "success"},
            },
        }
        result = _build_health_response(status)
        assert result["healthy"] is False
        assert "edge_sync" in result["failed_jobs"]

    def test_set_scheduler_registers_instance(self):
        """set_scheduler() stores the scheduler so get_status endpoint can use it."""
        import api.mesh_brain as mb

        original = mb._scheduler
        try:
            mock_scheduler = MagicMock()
            mb.set_scheduler(mock_scheduler)
            assert mb._scheduler is mock_scheduler
        finally:
            mb._scheduler = original

    @pytest.mark.asyncio
    async def test_status_endpoint_returns_not_initialized_message(self):
        """get_mesh_brain_status returns a safe dict when _scheduler is None."""
        import api.mesh_brain as mb

        original = mb._scheduler
        try:
            mb._scheduler = None
            result = await mb.get_mesh_brain_status()
            assert result["running"] is False
            assert "message" in result
        finally:
            mb._scheduler = original

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_not_initialized(self):
        """get_mesh_brain_health returns healthy=False with reason when _scheduler is None."""
        import api.mesh_brain as mb

        original = mb._scheduler
        try:
            mb._scheduler = None
            result = await mb.get_mesh_brain_health()
            assert result["healthy"] is False
            assert result["reason"] == "not_initialized"
        finally:
            mb._scheduler = original


# =============================================================================
# Internal helpers
# =============================================================================


def _patch_sleep():
    """Patch asyncio.sleep to return immediately during start() tests."""
    return patch("services.mesh_brain.scheduler.asyncio.sleep", new=AsyncMock())
