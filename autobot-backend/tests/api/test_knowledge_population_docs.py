# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for populate_autobot_docs endpoint and TaskStatusRecord dataclass.

Tests for GitHub issue #4103: Background task for documentation indexing.
Ensures populate_autobot_docs returns immediately with task_id.
"""


def test_task_status_dataclass_initialization():
    """Test TaskStatusRecord dataclass initialization with default values."""
    from services.knowledge.task_status_manager import TaskStatusRecord

    task = TaskStatusRecord(task_id="test-task-123", status="queued", message="Documentation indexing started")

    # Verify all fields are initialized correctly
    assert task.task_id == "test-task-123"
    assert task.status == "queued"
    assert task.message == "Documentation indexing started"
    assert task.progress_percent == 0
    assert task.items_processed == 0
    assert task.items_total == 0
    assert task.error is None
    assert task.created_at is not None
    assert task.updated_at is not None


def test_task_status_dataclass_custom_values():
    """Test TaskStatusRecord dataclass with custom field values."""
    from services.knowledge.task_status_manager import TaskStatusRecord

    task = TaskStatusRecord(
        task_id="test-task-456",
        status="running",
        message="Indexing files",
        progress_percent=50,
        items_processed=50,
        items_total=100,
        elapsed_seconds=30.5,
    )

    # Verify custom values are set
    assert task.progress_percent == 50
    assert task.items_processed == 50
    assert task.items_total == 100
    assert task.elapsed_seconds == 30.5
    assert task.status == "running"


def test_task_status_dataclass_with_error():
    """Test TaskStatusRecord dataclass with error information."""
    from services.knowledge.task_status_manager import TaskStatusRecord

    error_message = "Failed to read documentation file"
    task = TaskStatusRecord(
        task_id="test-task-error", status="failed", message="Documentation indexing failed", error=error_message
    )

    assert task.status == "failed"
    assert task.error == error_message


def test_task_status_manager_redis_key_format():
    """Test TaskStatusManager generates correct Redis key format."""
    from services.knowledge.task_status_manager import TaskStatusManager

    task_id = "test-task-id-12345"
    expected_prefix = "task_status:"

    # Call the private method to get the Redis key
    redis_key = TaskStatusManager._get_redis_key(task_id)

    # Verify key format
    assert redis_key.startswith(expected_prefix)
    assert task_id in redis_key
    assert redis_key == f"task_status:{task_id}"
