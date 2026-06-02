# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for Execution Snapshot API endpoints (GH#4458, MVA-2227).

Tests:
  - POST /execution/snapshots - create snapshot
  - GET /execution/snapshots - list snapshots
  - POST /execution/snapshots/{id}/restore - restore from snapshot
  - DELETE /execution/snapshots/{id} - delete snapshot
  - Auth: 403 when non-owner attempts restore/delete
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.execution_snapshots import router as execution_snapshots_router
from services.execution.snapshot_index import SnapshotRecord


@pytest.fixture
def app():
    """Create FastAPI app with execution_snapshots router for testing."""
    app = FastAPI()
    app.include_router(execution_snapshots_router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_backend():
    """Mock DockerBackend for testing."""
    backend = MagicMock()
    backend.snapshot = AsyncMock()
    backend.restore = AsyncMock()
    backend.delete_snapshot = AsyncMock()
    backend.get_snapshots_for_session = AsyncMock()
    backend._snapshot_index = MagicMock()
    return backend


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return {"username": "test-user", "role": "user"}


@pytest.fixture
def sample_snapshot_record():
    """Sample snapshot record for testing."""
    return SnapshotRecord(
        snapshot_id="snap-123",
        session_id="session-1",
        container_id="container-abc",
        image_name="autobot-snapshot-snap-123:latest",
        created_at="2025-01-15T10:00:00Z",
        size_bytes=1024000,
        labels={"env": "test"},
        user_id="test-user",
    )


class TestCreateSnapshot:
    """Tests for POST /execution/snapshots."""

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_create_snapshot_success(
        self, mock_get_user, mock_get_backend, client, mock_backend, mock_user, sample_snapshot_record
    ):
        """Test successful snapshot creation."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.snapshot.return_value = sample_snapshot_record

        response = client.post(
            "/execution/snapshots",
            json={
                "container_id": "container-abc",
                "session_id": "session-1",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["snapshot"]["snapshot_id"] == "snap-123"
        assert data["snapshot"]["container_id"] == "container-abc"
        assert data["snapshot"]["session_id"] == "session-1"
        assert data["snapshot"]["user_id"] == "test-user"

        # Verify backend was called with correct params
        mock_backend.snapshot.assert_called_once_with(
            container_id="container-abc",
            session_id="session-1",
            user_id="test-user",
        )

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_create_snapshot_failure(self, mock_get_user, mock_get_backend, client, mock_backend, mock_user):
        """Test snapshot creation failure."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.snapshot.side_effect = RuntimeError("Docker error")

        response = client.post(
            "/execution/snapshots",
            json={
                "container_id": "container-abc",
                "session_id": "session-1",
            },
        )

        assert response.status_code == 500
        assert "Snapshot creation failed" in response.json()["detail"]


class TestListSnapshots:
    """Tests for GET /execution/snapshots."""

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_list_snapshots_by_session(
        self, mock_get_user, mock_get_backend, client, mock_backend, mock_user, sample_snapshot_record
    ):
        """Test listing snapshots filtered by session_id."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.get_snapshots_for_session.return_value = [sample_snapshot_record]

        response = client.get("/execution/snapshots?session_id=session-1")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert len(data["snapshots"]) == 1
        assert data["snapshots"][0]["snapshot_id"] == "snap-123"
        assert data["snapshots"][0]["session_id"] == "session-1"

        mock_backend.get_snapshots_for_session.assert_called_once_with("session-1")

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_list_all_snapshots(
        self, mock_get_user, mock_get_backend, client, mock_backend, mock_user, sample_snapshot_record
    ):
        """Test listing all snapshots without session filter."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend._snapshot_index.list_all.return_value = [sample_snapshot_record]

        response = client.get("/execution/snapshots")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert len(data["snapshots"]) == 1

        mock_backend._snapshot_index.list_all.assert_called_once()

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_list_snapshots_empty(self, mock_get_user, mock_get_backend, client, mock_backend, mock_user):
        """Test listing snapshots when none exist."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend._snapshot_index.list_all.return_value = []

        response = client.get("/execution/snapshots")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 0
        assert data["snapshots"] == []


class TestRestoreSnapshot:
    """Tests for POST /execution/snapshots/{id}/restore."""

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_restore_snapshot_success(self, mock_get_user, mock_get_backend, client, mock_backend, mock_user):
        """Test successful snapshot restore."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.restore.return_value = "container-restored-123"

        response = client.post("/execution/snapshots/snap-123/restore")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["container_id"] == "container-restored-123"
        assert data["snapshot_id"] == "snap-123"

        mock_backend.restore.assert_called_once_with(
            "snap-123",
            caller_user_id="test-user",
        )

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_restore_snapshot_not_found(self, mock_get_user, mock_get_backend, client, mock_backend, mock_user):
        """Test restore with non-existent snapshot."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.restore.side_effect = KeyError("Snapshot not found")

        response = client.post("/execution/snapshots/nonexistent/restore")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_restore_snapshot_permission_denied(
        self, mock_get_user, mock_get_backend, client, mock_backend, mock_user
    ):
        """Test restore when user does not own snapshot (403)."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.restore.side_effect = PermissionError("User does not own this snapshot")

        response = client.post("/execution/snapshots/snap-123/restore")

        assert response.status_code == 403
        assert "User does not own this snapshot" in response.json()["detail"]

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_restore_snapshot_failure(self, mock_get_user, mock_get_backend, client, mock_backend, mock_user):
        """Test restore failure due to runtime error."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.restore.side_effect = RuntimeError("Docker restore failed")

        response = client.post("/execution/snapshots/snap-123/restore")

        assert response.status_code == 500
        assert "Snapshot restore failed" in response.json()["detail"]


class TestDeleteSnapshot:
    """Tests for DELETE /execution/snapshots/{id}."""

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_delete_snapshot_success(self, mock_get_user, mock_get_backend, client, mock_backend, mock_user):
        """Test successful snapshot deletion."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.delete_snapshot.return_value = True

        response = client.delete("/execution/snapshots/snap-123")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deleted successfully" in data["message"]

        mock_backend.delete_snapshot.assert_called_once_with(
            "snap-123",
            caller_user_id="test-user",
        )

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_delete_snapshot_not_found(self, mock_get_user, mock_get_backend, client, mock_backend, mock_user):
        """Test delete with non-existent snapshot (404)."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.delete_snapshot.return_value = False

        response = client.delete("/execution/snapshots/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_delete_snapshot_permission_denied(
        self, mock_get_user, mock_get_backend, client, mock_backend, mock_user
    ):
        """Test delete when user does not own snapshot (403)."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.delete_snapshot.side_effect = PermissionError("User does not own this snapshot")

        response = client.delete("/execution/snapshots/snap-123")

        assert response.status_code == 403
        assert "User does not own this snapshot" in response.json()["detail"]

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_delete_snapshot_failure(self, mock_get_user, mock_get_backend, client, mock_backend, mock_user):
        """Test delete failure due to runtime error."""
        mock_get_user.return_value = mock_user
        mock_get_backend.return_value = mock_backend
        mock_backend.delete_snapshot.side_effect = RuntimeError("Docker delete failed")

        response = client.delete("/execution/snapshots/snap-123")

        assert response.status_code == 500
        assert "Snapshot deletion failed" in response.json()["detail"]


class TestAuthIntegration:
    """Tests for authentication and authorization."""

    @patch("api.execution_snapshots.get_docker_backend")
    @patch("api.execution_snapshots.get_current_user")
    def test_user_id_passed_to_snapshot(self, mock_get_user, mock_get_backend, client, mock_backend):
        """Test that user_id from auth is passed to snapshot creation."""
        mock_get_user.return_value = {"username": "alice", "role": "user"}
        mock_get_backend.return_value = mock_backend
        mock_backend.snapshot.return_value = SnapshotRecord(
            snapshot_id="snap-1",
            session_id="session-1",
            container_id="container-1",
            image_name="test:latest",
            created_at="2025-01-15T10:00:00Z",
            size_bytes=1000,
            labels={},
            user_id="alice",
        )

        response = client.post(
            "/execution/snapshots",
            json={"container_id": "container-1", "session_id": "session-1"},
        )

        assert response.status_code == 200
        # Verify user_id was extracted from auth and passed to backend
        mock_backend.snapshot.assert_called_once_with(
            container_id="container-1",
            session_id="session-1",
            user_id="alice",
        )
