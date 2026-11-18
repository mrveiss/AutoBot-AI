# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for snapshot cleanup Celery task (GH#4458, MVA-2228).
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, create_autospec, patch

import pytest

from services.execution.docker_backend import DockerBackend
from services.execution.docker_backend_accessor import get_docker_backend_singleton
from services.execution.snapshot_index import SnapshotIndex, SnapshotRecord
from tasks.snapshot_cleanup import cleanup_expired_snapshots


def _make_backend(snapshots):
    """Spec-constrained DockerBackend: a call the real class lacks fails."""
    backend = create_autospec(DockerBackend, instance=True)
    # _snapshot_index is assigned in __init__, so autospec cannot see it.
    backend._snapshot_index = create_autospec(SnapshotIndex, instance=True)
    backend._snapshot_index.list_all.return_value = snapshots
    return backend


@pytest.fixture
def inject_backend():
    """Inject a backend through the real singleton factory (#20889)."""

    def _inject(backend):
        get_docker_backend_singleton.set_for_test(backend)

    yield _inject
    get_docker_backend_singleton.reset()


@pytest.mark.asyncio
async def test_cleanup_expired_snapshots_ttl_filter(inject_backend):
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

    mock_backend = _make_backend(snapshots)
    mock_backend.delete_snapshot = AsyncMock(return_value=True)

    inject_backend(mock_backend)
    result = cleanup_expired_snapshots(ttl_days=7)

    assert result["deleted"] == 1
    assert result["errors"] == 0
    mock_backend.delete_snapshot.assert_called_once_with("old1", caller_user_id="__system__")


@pytest.mark.asyncio
async def test_cleanup_expired_snapshots_env_var(inject_backend):
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

    mock_backend = _make_backend(snapshots)
    mock_backend.delete_snapshot = AsyncMock(return_value=True)

    with patch.dict(os.environ, {"AUTOBOT_SNAPSHOT_TTL_DAYS": "14"}):
        inject_backend(mock_backend)
        result = cleanup_expired_snapshots()

    assert result["deleted"] == 1
    assert result["errors"] == 0
    mock_backend.delete_snapshot.assert_called_once_with("old1", caller_user_id="__system__")


@pytest.mark.asyncio
async def test_cleanup_expired_snapshots_error_handling(inject_backend):
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

    mock_backend = _make_backend(snapshots)
    # First delete fails, second succeeds
    mock_backend.delete_snapshot = AsyncMock(side_effect=[Exception("Docker error"), True])

    inject_backend(mock_backend)
    result = cleanup_expired_snapshots(ttl_days=7)

    assert result["deleted"] == 1
    assert result["errors"] == 1
    assert mock_backend.delete_snapshot.call_count == 2


def test_singleton_accessor_returns_instance_not_factory(inject_backend):
    """The accessor is a factory; calling it yields the DockerBackend (#20889)."""
    backend = _make_backend([])
    inject_backend(backend)
    assert get_docker_backend_singleton() is backend


def test_api_dependency_returns_instance_not_factory(inject_backend):
    """The snapshot API dependency must hand endpoints an instance (#20889)."""
    from api.execution_snapshots import get_docker_backend

    backend = _make_backend([])
    inject_backend(backend)
    assert get_docker_backend() is backend
