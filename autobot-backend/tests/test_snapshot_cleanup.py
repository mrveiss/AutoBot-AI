# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for snapshot cleanup Celery task (GH#4458, MVA-2228).
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.execution.snapshot_index import SnapshotRecord
from tasks.snapshot_cleanup import cleanup_expired_snapshots


@pytest.mark.asyncio
async def test_cleanup_expired_snapshots_ttl_filter():
    """Verify only snapshots older than TTL are deleted."""
    now = datetime.now(timezone.utc)

    snapshots = [
        SnapshotRecord(
            snapshot_id="old1",
            session_id="s1",
            container_id="c1",
            image_name="img1",
            created_at=(now - timedelta(days=10)).isoformat(),
            size_bytes=1000,
        ),
        SnapshotRecord(
            snapshot_id="recent1",
            session_id="s2",
            container_id="c2",
            image_name="img2",
            created_at=(now - timedelta(days=3)).isoformat(),
            size_bytes=2000,
        ),
    ]

    mock_backend = MagicMock()
    mock_backend._snapshot_index.list_all.return_value = snapshots
    mock_backend.delete_snapshot = AsyncMock(return_value=True)

    with patch("tasks.snapshot_cleanup.lazy_singleton", return_value=mock_backend):
        result = cleanup_expired_snapshots(ttl_days=7)

    assert result["deleted"] == 1
    assert result["errors"] == 0
    mock_backend.delete_snapshot.assert_called_once_with(
        "old1", caller_user_id="__system__"
    )


@pytest.mark.asyncio
async def test_cleanup_expired_snapshots_env_var():
    """Verify AUTOBOT_SNAPSHOT_TTL_DAYS env var is respected."""
    now = datetime.now(timezone.utc)

    snapshots = [
        SnapshotRecord(
            snapshot_id="old1",
            session_id="s1",
            container_id="c1",
            image_name="img1",
            created_at=(now - timedelta(days=15)).isoformat(),
            size_bytes=1000,
        ),
        SnapshotRecord(
            snapshot_id="recent1",
            session_id="s2",
            container_id="c2",
            image_name="img2",
            created_at=(now - timedelta(days=10)).isoformat(),
            size_bytes=2000,
        ),
    ]

    mock_backend = MagicMock()
    mock_backend._snapshot_index.list_all.return_value = snapshots
    mock_backend.delete_snapshot = AsyncMock(return_value=True)

    with patch.dict(os.environ, {"AUTOBOT_SNAPSHOT_TTL_DAYS": "14"}):
        with patch("tasks.snapshot_cleanup.lazy_singleton", return_value=mock_backend):
            result = cleanup_expired_snapshots()

    assert result["deleted"] == 1
    assert result["errors"] == 0
    mock_backend.delete_snapshot.assert_called_once_with(
        "old1", caller_user_id="__system__"
    )


@pytest.mark.asyncio
async def test_cleanup_expired_snapshots_error_handling():
    """Verify errors are logged but don't stop cleanup."""
    now = datetime.now(timezone.utc)

    snapshots = [
        SnapshotRecord(
            snapshot_id="old1",
            session_id="s1",
            container_id="c1",
            image_name="img1",
            created_at=(now - timedelta(days=10)).isoformat(),
            size_bytes=1000,
        ),
        SnapshotRecord(
            snapshot_id="old2",
            session_id="s2",
            container_id="c2",
            image_name="img2",
            created_at=(now - timedelta(days=12)).isoformat(),
            size_bytes=2000,
        ),
    ]

    mock_backend = MagicMock()
    mock_backend._snapshot_index.list_all.return_value = snapshots
    # First delete fails, second succeeds
    mock_backend.delete_snapshot = AsyncMock(
        side_effect=[Exception("Docker error"), True]
    )

    with patch("tasks.snapshot_cleanup.lazy_singleton", return_value=mock_backend):
        result = cleanup_expired_snapshots(ttl_days=7)

    assert result["deleted"] == 1
    assert result["errors"] == 1
    assert mock_backend.delete_snapshot.call_count == 2
