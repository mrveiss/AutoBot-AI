# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for codebase stats endpoint (Issue #540)

Tests the following functionality:
- Active indexing task detection
- Stale task timeout handling
- Stats endpoint responses during various states
- Thread-safe access to indexing_tasks
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestIsTaskStale:
    """Tests for _is_task_stale function."""

    def test_returns_false_when_no_started_at(self):
        """Task without started_at should not be considered stale."""
        from backend.api.codebase_analytics.endpoints.stats import _is_task_stale

        task_info = {"status": "running"}
        assert _is_task_stale(task_info) is False

    def test_returns_false_for_recent_task(self):
        """Task started recently should not be stale."""
        from backend.api.codebase_analytics.endpoints.stats import _is_task_stale

        task_info = {
            "status": "running",
            "started_at": datetime.now().isoformat(),
        }
        assert _is_task_stale(task_info) is False

    def test_returns_true_for_old_task(self):
        """Task started more than 1 hour ago should be stale."""
        from backend.api.codebase_analytics.endpoints.stats import (
            _STALE_TASK_TIMEOUT_SECONDS,
            _is_task_stale,
        )

        old_time = datetime.now() - timedelta(seconds=_STALE_TASK_TIMEOUT_SECONDS + 60)
        task_info = {
            "status": "running",
            "started_at": old_time.isoformat(),
        }
        assert _is_task_stale(task_info) is True

    def test_handles_invalid_timestamp_gracefully(self):
        """Invalid timestamp should not crash, returns False."""
        from backend.api.codebase_analytics.endpoints.stats import _is_task_stale

        task_info = {
            "status": "running",
            "started_at": "invalid-timestamp",
        }
        assert _is_task_stale(task_info) is False

    def test_handles_none_timestamp(self):
        """None timestamp should return False."""
        from backend.api.codebase_analytics.endpoints.stats import _is_task_stale

        task_info = {
            "status": "running",
            "started_at": None,
        }
        assert _is_task_stale(task_info) is False


class TestGetActiveIndexingTask:
    """Tests for _get_active_indexing_task function."""

    def test_returns_none_when_no_tasks(self):
        """Should return None when no indexing tasks exist."""
        from backend.api.codebase_analytics.endpoints import stats
        from backend.api.codebase_analytics.endpoints.stats import (
            _get_active_indexing_task,
        )

        with patch.object(stats, "indexing_tasks", {}):
            result = _get_active_indexing_task()
            assert result is None

    def test_returns_none_when_all_tasks_completed(self):
        """Should return None when all tasks are completed."""
        from backend.api.codebase_analytics.endpoints import stats
        from backend.api.codebase_analytics.endpoints.stats import (
            _get_active_indexing_task,
        )

        mock_tasks = {
            "task-1": {"status": "completed"},
            "task-2": {"status": "failed"},
        }
        with patch.object(stats, "indexing_tasks", mock_tasks):
            result = _get_active_indexing_task()
            assert result is None

    def test_returns_running_task(self):
        """Should return info for a running task."""
        from backend.api.codebase_analytics.endpoints import stats
        from backend.api.codebase_analytics.endpoints.stats import (
            _get_active_indexing_task,
        )

        mock_tasks = {
            "task-1": {
                "status": "running",
                "progress": {"current": 50, "total": 100},
                "phases": {"current_phase": "scan"},
                "stats": {"files_scanned": 50},
                "started_at": datetime.now().isoformat(),
            }
        }
        with patch.object(stats, "indexing_tasks", mock_tasks):
            result = _get_active_indexing_task()
            assert result is not None
            assert result["task_id"] == "task-1"
            assert result["progress"]["current"] == 50

    def test_ignores_stale_running_task(self):
        """Should ignore tasks that have been running too long."""
        from backend.api.codebase_analytics.endpoints import stats
        from backend.api.codebase_analytics.endpoints.stats import (
            _STALE_TASK_TIMEOUT_SECONDS,
            _get_active_indexing_task,
        )

        old_time = datetime.now() - timedelta(seconds=_STALE_TASK_TIMEOUT_SECONDS + 60)
        mock_tasks = {
            "stale-task": {
                "status": "running",
                "progress": {"current": 10, "total": 100},
                "phases": {},
                "stats": {},
                "started_at": old_time.isoformat(),
            }
        }
        with patch.object(stats, "indexing_tasks", mock_tasks):
            result = _get_active_indexing_task()
            assert result is None

    def test_returns_fresh_task_ignoring_stale(self):
        """Should return fresh running task, ignoring stale ones."""
        from backend.api.codebase_analytics.endpoints import stats
        from backend.api.codebase_analytics.endpoints.stats import (
            _STALE_TASK_TIMEOUT_SECONDS,
            _get_active_indexing_task,
        )

        old_time = datetime.now() - timedelta(seconds=_STALE_TASK_TIMEOUT_SECONDS + 60)
        fresh_time = datetime.now()

        mock_tasks = {
            "stale-task": {
                "status": "running",
                "started_at": old_time.isoformat(),
            },
            "fresh-task": {
                "status": "running",
                "progress": {"current": 75, "total": 100},
                "phases": {"current_phase": "store"},
                "stats": {"files_scanned": 200},
                "started_at": fresh_time.isoformat(),
            },
        }
        with patch.object(stats, "indexing_tasks", mock_tasks):
            result = _get_active_indexing_task()
            assert result is not None
            assert result["task_id"] == "fresh-task"


class TestParseStatsMetadata:
    """Tests for _parse_stats_metadata function."""

    def test_parses_numeric_fields(self):
        """Should parse all numeric fields correctly."""
        from backend.api.codebase_analytics.endpoints.stats import _parse_stats_metadata

        metadata = {
            "total_files": "100",
            "python_files": "50",
            "total_lines": "10000",
            "total_functions": "200",
            "total_classes": "30",
        }
        result = _parse_stats_metadata(metadata)

        assert result["total_files"] == 100
        assert result["python_files"] == 50
        assert result["total_lines"] == 10000
        assert result["total_functions"] == 200
        assert result["total_classes"] == 30

    def test_parses_float_fields(self):
        """Should parse average_file_size as float."""
        from backend.api.codebase_analytics.endpoints.stats import _parse_stats_metadata

        metadata = {"average_file_size": "123.45"}
        result = _parse_stats_metadata(metadata)

        assert result["average_file_size"] == 123.45

    def test_parses_json_category_fields(self):
        """Should parse JSON-encoded category fields."""
        import json

        from backend.api.codebase_analytics.endpoints.stats import _parse_stats_metadata

        metadata = {
            "lines_by_category": json.dumps({"code": 8000, "docs": 2000}),
            "files_by_category": json.dumps({"code": 80, "docs": 20}),
        }
        result = _parse_stats_metadata(metadata)

        assert result["lines_by_category"]["code"] == 8000
        assert result["files_by_category"]["docs"] == 20

    def test_handles_dict_category_fields(self):
        """Should handle category fields that are already dicts."""
        from backend.api.codebase_analytics.endpoints.stats import _parse_stats_metadata

        metadata = {
            "lines_by_category": {"code": 5000},
        }
        result = _parse_stats_metadata(metadata)

        assert result["lines_by_category"]["code"] == 5000

    def test_parses_ratio_strings(self):
        """Should preserve ratio strings as-is."""
        from backend.api.codebase_analytics.endpoints.stats import _parse_stats_metadata

        metadata = {
            "comment_ratio": "15.5%",
            "docstring_ratio": "8.2%",
            "documentation_ratio": "23.7%",
        }
        result = _parse_stats_metadata(metadata)

        assert result["comment_ratio"] == "15.5%"
        assert result["docstring_ratio"] == "8.2%"
        assert result["documentation_ratio"] == "23.7%"


class TestClearChromaDBCollection:
    """Tests for _clear_chromadb_collection preserving codebase_stats."""

    @pytest.mark.asyncio
    async def test_preserves_codebase_stats(self):
        """Should not delete codebase_stats document."""
        from backend.api.codebase_analytics.scanner import _clear_chromadb_collection

        mock_collection = MagicMock()
        mock_collection.get = MagicMock(
            return_value={
                "ids": ["codebase_stats", "function_1", "class_1", "problem_1"]
            }
        )
        mock_collection.delete = MagicMock()

        # Make get async
        async def async_get():
            return {"ids": ["codebase_stats", "function_1", "class_1", "problem_1"]}

        async def async_delete(ids):
            pass

        mock_collection.get = async_get
        mock_collection.delete = MagicMock(side_effect=async_delete)

        await _clear_chromadb_collection(mock_collection, "test-task")

        # Verify delete was called with IDs excluding codebase_stats
        mock_collection.delete.assert_called_once()
        deleted_ids = mock_collection.delete.call_args[1]["ids"]
        assert "codebase_stats" not in deleted_ids
        assert "function_1" in deleted_ids
        assert "class_1" in deleted_ids
        assert "problem_1" in deleted_ids

    @pytest.mark.asyncio
    async def test_handles_empty_collection(self):
        """Should handle empty collection gracefully."""
        from backend.api.codebase_analytics.scanner import _clear_chromadb_collection

        mock_collection = MagicMock()

        async def async_get():
            return {"ids": []}

        mock_collection.get = async_get
        mock_collection.delete = MagicMock()

        # Should not raise
        await _clear_chromadb_collection(mock_collection, "test-task")

        # Delete should not be called for empty collection
        mock_collection.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_only_stats_document(self):
        """Should not delete anything if only codebase_stats exists."""
        from backend.api.codebase_analytics.scanner import _clear_chromadb_collection

        mock_collection = MagicMock()

        async def async_get():
            return {"ids": ["codebase_stats"]}

        mock_collection.get = async_get
        mock_collection.delete = MagicMock()

        await _clear_chromadb_collection(mock_collection, "test-task")

        # Delete should not be called since filtering removes codebase_stats
        mock_collection.delete.assert_not_called()


class TestNoDataResponse:
    """Tests for _no_data_response helper."""

    def test_returns_json_response(self):
        """Should return JSONResponse with correct structure."""
        from backend.api.codebase_analytics.endpoints.stats import _no_data_response
        from fastapi.responses import JSONResponse

        result = _no_data_response()

        assert isinstance(result, JSONResponse)

    def test_default_message(self):
        """Should use default message when none provided."""
        from backend.api.codebase_analytics.endpoints.stats import _no_data_response

        result = _no_data_response()
        # JSONResponse body is bytes, need to decode
        import json

        body = json.loads(result.body)

        assert body["status"] == "no_data"
        assert "Run indexing first" in body["message"]
        assert body["stats"] is None

    def test_custom_message(self):
        """Should use custom message when provided."""
        import json

        from backend.api.codebase_analytics.endpoints.stats import _no_data_response

        result = _no_data_response("Custom error message")
        body = json.loads(result.body)

        assert body["message"] == "Custom error message"
