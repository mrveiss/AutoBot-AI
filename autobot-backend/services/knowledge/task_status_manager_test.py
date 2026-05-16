# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for task status manager Redis-backed tracking.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.knowledge.task_status_manager import (
    TaskStatusManager,
    TaskStatusRecord,
)


@pytest.fixture
def sample_task_id():
    return "test-task-12345"


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    mock = MagicMock()
    mock.get = MagicMock(return_value=None)
    mock.setex = MagicMock(return_value=True)
    mock.delete = MagicMock(return_value=1)
    return mock


class TestTaskStatusManager:
    """Tests for TaskStatusManager."""

    @pytest.mark.asyncio
    async def test_create_task(self, sample_task_id, mock_redis_client) -> None:
        """Test creating a new task status."""
        with patch("services.knowledge.task_status_manager.get_redis_client", return_value=mock_redis_client):
            status = await TaskStatusManager.create_task(
                task_id=sample_task_id,
                message="Test task created",
                total_items=100,
            )

            assert status.task_id == sample_task_id
            assert status.status == "queued"
            assert status.message == "Test task created"
            assert status.items_total == 100
            assert status.progress_percent == 0
            assert status.created_at is not None
            assert status.updated_at is not None

            # Verify Redis setex was called
            mock_redis_client.setex.assert_called_once()
            args = mock_redis_client.setex.call_args
            assert sample_task_id in args[0][0]  # Key should contain task_id

    @pytest.mark.asyncio
    async def test_update_task_status(self, sample_task_id, mock_redis_client) -> None:
        """Test updating task status during execution."""
        with patch("services.knowledge.task_status_manager.get_redis_client", return_value=mock_redis_client):
            # Create initial task
            await TaskStatusManager.create_task(sample_task_id, "Starting")

            # Update progress
            status = await TaskStatusManager.update_task(
                task_id=sample_task_id,
                status="running",
                message="Processing files",
                progress_percent=50,
                items_processed=50,
                items_total=100,
            )

            assert status.status == "running"
            assert status.progress_percent == 50
            assert status.items_processed == 50

    @pytest.mark.asyncio
    async def test_complete_task(self, sample_task_id, mock_redis_client) -> None:
        """Test marking task as completed."""
        with patch("services.knowledge.task_status_manager.get_redis_client", return_value=mock_redis_client):
            status = await TaskStatusManager.complete_task(
                task_id=sample_task_id,
                message="Task completed successfully",
                items_processed=100,
                elapsed_seconds=123.45,
            )

            assert status.status == "completed"
            assert status.progress_percent == 100
            assert status.items_processed == 100
            assert status.elapsed_seconds == 123.45
            assert status.error is None

    @pytest.mark.asyncio
    async def test_fail_task(self, sample_task_id, mock_redis_client) -> None:
        """Test marking task as failed."""
        with patch("services.knowledge.task_status_manager.get_redis_client", return_value=mock_redis_client):
            error_msg = "Connection timeout"
            status = await TaskStatusManager.fail_task(
                task_id=sample_task_id,
                error_message=error_msg,
            )

            assert status.status == "failed"
            assert status.error == error_msg
            assert status.progress_percent == 0

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, sample_task_id, mock_redis_client) -> None:
        """Test retrieving non-existent task."""
        mock_redis_client.get.return_value = None

        with patch("services.knowledge.task_status_manager.get_redis_client", return_value=mock_redis_client):
            status = await TaskStatusManager.get_task(sample_task_id)

            assert status is None

    @pytest.mark.asyncio
    async def test_get_task_found(self, sample_task_id, mock_redis_client) -> None:
        """Test retrieving existing task."""
        import json

        task_data = {
            "task_id": sample_task_id,
            "status": "running",
            "message": "Processing",
            "progress_percent": 50,
            "items_processed": 50,
            "items_total": 100,
            "error": None,
            "created_at": "2026-04-10T12:00:00+00:00",
            "updated_at": "2026-04-10T12:05:00+00:00",
            "elapsed_seconds": 300.0,
        }
        mock_redis_client.get.return_value = json.dumps(task_data)

        with patch("services.knowledge.task_status_manager.get_redis_client", return_value=mock_redis_client):
            status = await TaskStatusManager.get_task(sample_task_id)

            assert status is not None
            assert status.task_id == sample_task_id
            assert status.status == "running"
            assert status.progress_percent == 50

    @pytest.mark.asyncio
    async def test_delete_task(self, sample_task_id, mock_redis_client) -> None:
        """Test deleting task status."""
        with patch("services.knowledge.task_status_manager.get_redis_client", return_value=mock_redis_client):
            result = await TaskStatusManager.delete_task(sample_task_id)

            assert result is True
            mock_redis_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_status_dataclass(self) -> None:
        """Test TaskStatusRecord dataclass."""
        status = TaskStatusRecord(
            task_id="test-123",
            status="running",
            message="Processing",
            progress_percent=50,
        )

        assert status.task_id == "test-123"
        assert status.status == "running"
        assert status.created_at is not None
        assert status.updated_at is not None

    @pytest.mark.asyncio
    async def test_redis_save_error_handling(self, sample_task_id) -> None:
        """Test error handling when Redis save fails."""
        mock_redis_client = MagicMock()
        mock_redis_client.setex.side_effect = Exception("Redis connection failed")

        with patch("services.knowledge.task_status_manager.get_redis_client", return_value=mock_redis_client):
            status = TaskStatusRecord(
                task_id=sample_task_id,
                status="running",
                message="Test",
            )

            result = await TaskStatusManager._save_to_redis(status)
            assert result is False

    @pytest.mark.asyncio
    async def test_get_redis_key_format(self, sample_task_id) -> None:
        """Test that Redis key format is correct."""
        key = TaskStatusManager._get_redis_key(sample_task_id)

        assert key.startswith("task_status:")
        assert sample_task_id in key
        assert key == f"task_status:{sample_task_id}"
