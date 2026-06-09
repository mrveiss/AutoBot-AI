# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for analytics Celery tasks — enqueue → run → result-backend cycle (GH#6505).

Uses Celery's eager mode (CELERY_TASK_ALWAYS_EAGER=True) so tasks execute
synchronously in-process without a broker or result backend.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def celery_eager(monkeypatch):
    """Force Celery to run tasks synchronously (no broker needed)."""
    from celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


class TestRunDashboardAnalysis:
    """Enqueue → run → result-backend cycle for run_dashboard_analysis."""

    def _make_fake_gather_result(self):
        """Return lightweight stubs for all asyncio.gather branches."""
        health = {"cpu": 0.1}
        perf = {"latency_ms": 5}
        comm = {"agents": []}
        usage = {"sessions": 0}
        trends = {"direction": "flat"}
        return health, perf, comm, usage, trends

    @patch("tasks.analytics_tasks._run_async")
    def test_enqueue_run_result(self, mock_run_async):
        """Task returns a result envelope with started_at and completed_at."""
        expected_result = {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "system_health": {},
            "performance_metrics": {},
            "communication_patterns": {},
            "code_analysis_status": {},
            "usage_statistics": {},
            "realtime_metrics": {},
            "trends": {},
        }
        mock_run_async.return_value = expected_result

        from tasks.analytics_tasks import run_dashboard_analysis

        result = run_dashboard_analysis.delay()

        assert result.successful()
        payload = result.get()
        assert payload["result"] == expected_result
        assert "started_at" in payload
        assert "completed_at" in payload

    @patch("tasks.analytics_tasks._run_async")
    def test_celery_result_to_status_maps_success(self, mock_run_async):
        """celery_result_to_status converts SUCCESS state to 'completed'."""
        mock_run_async.return_value = {"status": "ok"}

        from celery.result import AsyncResult

        from tasks.analytics_tasks import run_dashboard_analysis
        from utils.celery_task_status import celery_result_to_status

        celery_result = run_dashboard_analysis.delay()
        status = celery_result_to_status(AsyncResult(celery_result.id))

        assert status is not None
        assert status["status"] == "completed"
        assert status["progress"] == 100.0
        assert status["result"] == {"status": "ok"}

    @patch("tasks.analytics_tasks._run_async")
    def test_failure_maps_to_failed_status(self, mock_run_async):
        """Task failure maps to 'failed' in celery_result_to_status."""
        mock_run_async.side_effect = RuntimeError("boom")

        from celery.result import AsyncResult

        from celery_app import celery_app
        from tasks.analytics_tasks import run_dashboard_analysis
        from utils.celery_task_status import celery_result_to_status

        celery_app.conf.task_eager_propagates = False
        try:
            celery_result = run_dashboard_analysis.delay()
            status = celery_result_to_status(AsyncResult(celery_result.id))
            assert status is not None
            assert status["status"] == "failed"
            assert status["error"]
        finally:
            celery_app.conf.task_eager_propagates = True


class TestCeleryTaskStatusHelper:
    """Unit tests for celery_result_to_status without running real tasks."""

    def _mock_result(self, state, info=None):
        r = MagicMock()
        r.state = state
        r.info = info or {}
        r.id = "test-id-123"
        return r

    def test_pending_state(self):
        from utils.celery_task_status import celery_result_to_status

        status = celery_result_to_status(self._mock_result("PENDING"))
        assert status["status"] == "pending"
        assert status["progress"] == 0.0

    def test_progress_state(self):
        from utils.celery_task_status import celery_result_to_status

        status = celery_result_to_status(self._mock_result("PROGRESS", {"step": "Scanning", "progress": 42.0}))
        assert status["status"] == "running"
        assert status["progress"] == 42.0
        assert status["current_step"] == "Scanning"

    def test_success_state(self):
        from utils.celery_task_status import celery_result_to_status

        status = celery_result_to_status(
            self._mock_result("SUCCESS", {"result": {"data": 1}, "completed_at": "2026-01-01T00:00:00+00:00"})
        )
        assert status["status"] == "completed"
        assert status["progress"] == 100.0
        assert status["result"] == {"data": 1}

    def test_failure_state(self):
        from utils.celery_task_status import celery_result_to_status

        exc = RuntimeError("bad things happened")
        status = celery_result_to_status(self._mock_result("FAILURE", exc))
        assert status["status"] == "failed"
        assert "bad things" in status["error"]
