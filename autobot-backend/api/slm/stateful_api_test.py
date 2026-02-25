# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for SLM Stateful Services API.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.slm.stateful import router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.slm.stateful_manager import (
    BackupContext,
    BackupState,
    ReplicationContext,
    ReplicationState,
    StatefulServiceManager,
)


@pytest.fixture
def app():
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_manager():
    """Create mock stateful service manager."""
    manager = MagicMock(spec=StatefulServiceManager)
    manager.active_replications = []
    manager.active_backups = []
    return manager


@pytest.fixture
def sample_replication():
    """Create sample replication context."""
    return ReplicationContext(
        replication_id="rep-123",
        primary_node_id="node-1",
        replica_node_id="node-2",
        service_type="redis",
        state=ReplicationState.SYNCING,
        sync_progress=0.5,
    )


@pytest.fixture
def sample_backup():
    """Create sample backup context."""
    return BackupContext(
        backup_id="bak-123",
        node_id="node-1",
        service_type="redis",
        backup_path="/tmp/backups/backup.rdb",
        state=BackupState.COMPLETED,
        size_bytes=1024,
        checksum="abc123",
    )


class TestListReplications:
    """Test list replications endpoint."""

    def test_list_empty(self, client, mock_manager):
        """Test listing with no replications."""
        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.get("/v1/slm/stateful/replications")

        assert response.status_code == 200
        data = response.json()
        assert data["replications"] == []
        assert data["total"] == 0

    def test_list_with_replications(self, client, mock_manager, sample_replication):
        """Test listing with replications."""
        mock_manager.active_replications = [sample_replication]

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.get("/v1/slm/stateful/replications")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["replications"][0]["replication_id"] == "rep-123"


class TestStartReplication:
    """Test start replication endpoint."""

    def test_start_replication_success(self, client, mock_manager, sample_replication):
        """Test successful replication start."""
        mock_manager.start_replication = AsyncMock(return_value=sample_replication)

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post(
                "/v1/slm/stateful/replications",
                json={
                    "primary_node_id": "node-1",
                    "replica_node_id": "node-2",
                    "service_type": "redis",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["replication_id"] == "rep-123"
        assert data["state"] == "syncing"

    def test_start_replication_failure(self, client, mock_manager):
        """Test replication start failure."""
        failed_ctx = ReplicationContext(
            replication_id="rep-fail",
            primary_node_id="node-1",
            replica_node_id="node-2",
            service_type="redis",
            state=ReplicationState.FAILED,
            error="Connection refused",
        )
        mock_manager.start_replication = AsyncMock(return_value=failed_ctx)

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post(
                "/v1/slm/stateful/replications",
                json={
                    "primary_node_id": "node-1",
                    "replica_node_id": "node-2",
                },
            )

        assert response.status_code == 400
        assert "Connection refused" in response.json()["detail"]


class TestGetReplication:
    """Test get replication endpoint."""

    def test_get_replication_success(self, client, mock_manager, sample_replication):
        """Test getting replication by ID."""
        mock_manager.get_replication.return_value = sample_replication
        mock_manager.check_replication_sync = AsyncMock(return_value=(False, 0.5))

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.get("/v1/slm/stateful/replications/rep-123")

        assert response.status_code == 200
        data = response.json()
        assert data["replication_id"] == "rep-123"

    def test_get_replication_not_found(self, client, mock_manager):
        """Test getting nonexistent replication."""
        mock_manager.get_replication.return_value = None

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.get("/v1/slm/stateful/replications/nonexistent")

        assert response.status_code == 404


class TestPromoteReplica:
    """Test promote replica endpoint."""

    def test_promote_success(self, client, mock_manager, sample_replication):
        """Test successful promotion."""
        sample_replication.state = ReplicationState.SYNCED
        mock_manager.get_replication.return_value = sample_replication
        mock_manager.promote_replica = AsyncMock(return_value=True)

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post("/v1/slm/stateful/replications/rep-123/promote")

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "promote"
        assert data["success"] is True

    def test_promote_not_synced(self, client, mock_manager, sample_replication):
        """Test promotion when not synced."""
        sample_replication.state = ReplicationState.PENDING
        mock_manager.get_replication.return_value = sample_replication

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post("/v1/slm/stateful/replications/rep-123/promote")

        assert response.status_code == 400
        assert "Cannot promote" in response.json()["detail"]

    def test_promote_not_found(self, client, mock_manager):
        """Test promotion of nonexistent replication."""
        mock_manager.get_replication.return_value = None

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post("/v1/slm/stateful/replications/nonexistent/promote")

        assert response.status_code == 404


class TestListBackups:
    """Test list backups endpoint."""

    def test_list_empty(self, client, mock_manager):
        """Test listing with no backups."""
        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.get("/v1/slm/stateful/backups")

        assert response.status_code == 200
        data = response.json()
        assert data["backups"] == []
        assert data["total"] == 0

    def test_list_with_backups(self, client, mock_manager, sample_backup):
        """Test listing with backups."""
        mock_manager.active_backups = [sample_backup]

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.get("/v1/slm/stateful/backups")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["backups"][0]["backup_id"] == "bak-123"


class TestCreateBackup:
    """Test create backup endpoint."""

    def test_create_backup_success(self, client, mock_manager, sample_backup):
        """Test successful backup creation."""
        mock_manager.create_backup = AsyncMock(return_value=sample_backup)

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post(
                "/v1/slm/stateful/backups",
                json={
                    "node_id": "node-1",
                    "service_type": "redis",
                    "backup_name": "test_backup",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["backup_id"] == "bak-123"
        assert data["state"] == "completed"

    def test_create_backup_failure(self, client, mock_manager):
        """Test backup creation failure."""
        failed_ctx = BackupContext(
            backup_id="bak-fail",
            node_id="node-1",
            service_type="redis",
            backup_path="",
            state=BackupState.FAILED,
            error="Disk full",
        )
        mock_manager.create_backup = AsyncMock(return_value=failed_ctx)

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post(
                "/v1/slm/stateful/backups",
                json={
                    "node_id": "node-1",
                },
            )

        assert response.status_code == 400
        assert "Disk full" in response.json()["detail"]


class TestGetBackup:
    """Test get backup endpoint."""

    def test_get_backup_success(self, client, mock_manager, sample_backup):
        """Test getting backup by ID."""
        mock_manager.get_backup.return_value = sample_backup

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.get("/v1/slm/stateful/backups/bak-123")

        assert response.status_code == 200
        data = response.json()
        assert data["backup_id"] == "bak-123"

    def test_get_backup_not_found(self, client, mock_manager):
        """Test getting nonexistent backup."""
        mock_manager.get_backup.return_value = None

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.get("/v1/slm/stateful/backups/nonexistent")

        assert response.status_code == 404


class TestRestoreBackup:
    """Test restore backup endpoint."""

    def test_restore_success(self, client, mock_manager, sample_backup):
        """Test successful restore."""
        mock_manager.get_backup.return_value = sample_backup
        mock_manager.restore_backup = AsyncMock(return_value=True)

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post("/v1/slm/stateful/backups/bak-123/restore")

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "restore"
        assert data["success"] is True

    def test_restore_not_completed(self, client, mock_manager, sample_backup):
        """Test restore when backup not completed."""
        sample_backup.state = BackupState.IN_PROGRESS
        mock_manager.get_backup.return_value = sample_backup

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post("/v1/slm/stateful/backups/bak-123/restore")

        assert response.status_code == 400
        assert "Cannot restore" in response.json()["detail"]

    def test_restore_not_found(self, client, mock_manager):
        """Test restore of nonexistent backup."""
        mock_manager.get_backup.return_value = None

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post("/v1/slm/stateful/backups/nonexistent/restore")

        assert response.status_code == 404


class TestVerifyData:
    """Test data verification endpoint."""

    def test_verify_success(self, client, mock_manager):
        """Test successful verification."""
        mock_manager.verify_data = AsyncMock(
            return_value=(
                True,
                {
                    "keyspace": {"db0": "keys=100"},
                    "memory": {"used_memory": "1000000"},
                    "errors": [],
                },
            )
        )

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post(
                "/v1/slm/stateful/verify",
                json={
                    "node_id": "node-1",
                    "service_type": "redis",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["is_healthy"] is True
        assert "keyspace" in data["details"]

    def test_verify_unhealthy(self, client, mock_manager):
        """Test verification with errors."""
        mock_manager.verify_data = AsyncMock(
            return_value=(
                False,
                {
                    "errors": ["RDB save failed"],
                },
            )
        )

        with patch(
            "api.slm.stateful.get_stateful_manager",
            return_value=mock_manager,
        ):
            response = client.post(
                "/v1/slm/stateful/verify",
                json={
                    "node_id": "node-1",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["is_healthy"] is False
        assert "RDB save failed" in data["details"]["errors"]
