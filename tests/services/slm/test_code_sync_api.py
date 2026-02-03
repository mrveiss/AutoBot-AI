# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Code Sync API endpoints (Issue #741).
"""

from pathlib import Path

import pytest

# Import code_distributor module directly
code_distributor_path = (
    Path(__file__).parent.parent.parent.parent
    / "slm-server"
    / "services"
    / "code_distributor.py"
)
spec = __import__("importlib.util").util.spec_from_file_location(
    "code_distributor", code_distributor_path
)
code_distributor_module = __import__("importlib.util").util.module_from_spec(spec)
spec.loader.exec_module(code_distributor_module)


class TestCodeSyncStatus:
    """Tests for GET /api/code-sync/status endpoint."""

    def test_status_response_model(self):
        """Test CodeSyncStatusResponse model."""
        from models.schemas import CodeSyncStatusResponse

        response = CodeSyncStatusResponse(
            latest_version="abc123",
            local_version="abc123",
            has_update=False,
            outdated_nodes=0,
            total_nodes=5,
        )

        assert response.latest_version == "abc123"
        assert response.has_update is False
        assert response.total_nodes == 5

    def test_status_response_with_update(self):
        """Test CodeSyncStatusResponse when update is available."""
        from models.schemas import CodeSyncStatusResponse

        response = CodeSyncStatusResponse(
            latest_version="def456",
            local_version="abc123",
            has_update=True,
            outdated_nodes=3,
            total_nodes=5,
        )

        assert response.latest_version == "def456"
        assert response.local_version == "abc123"
        assert response.has_update is True
        assert response.outdated_nodes == 3


class TestCodeSyncRefresh:
    """Tests for POST /api/code-sync/refresh endpoint."""

    def test_refresh_response_model(self):
        """Test CodeSyncRefreshResponse model."""
        from models.schemas import CodeSyncRefreshResponse

        response = CodeSyncRefreshResponse(
            success=True,
            message="Updated",
            latest_version="def456",
            has_update=True,
        )

        assert response.success is True
        assert response.has_update is True
        assert response.message == "Updated"

    def test_refresh_response_failure(self):
        """Test CodeSyncRefreshResponse for failed refresh."""
        from models.schemas import CodeSyncRefreshResponse

        response = CodeSyncRefreshResponse(
            success=False,
            message="Failed to fetch remote version",
            latest_version=None,
            has_update=False,
        )

        assert response.success is False
        assert response.latest_version is None


class TestPendingNodes:
    """Tests for GET /api/code-sync/pending endpoint."""

    def test_pending_node_response_model(self):
        """Test PendingNodeResponse model."""
        from models.schemas import PendingNodeResponse

        node = PendingNodeResponse(
            node_id="node-001",
            hostname="test-host",
            ip_address="192.168.1.100",
            current_version="abc123",
            code_status="outdated",
        )

        assert node.node_id == "node-001"
        assert node.code_status == "outdated"
        assert node.hostname == "test-host"

    def test_pending_nodes_response_model(self):
        """Test PendingNodesResponse model."""
        from models.schemas import PendingNodeResponse, PendingNodesResponse

        nodes = [
            PendingNodeResponse(
                node_id="node-001",
                hostname="host1",
                ip_address="192.168.1.1",
                current_version="abc",
                code_status="outdated",
            )
        ]

        response = PendingNodesResponse(
            nodes=nodes,
            total=1,
            latest_version="def456",
        )

        assert response.total == 1
        assert len(response.nodes) == 1
        assert response.latest_version == "def456"

    def test_pending_nodes_empty(self):
        """Test PendingNodesResponse with no pending nodes."""
        from models.schemas import PendingNodesResponse

        response = PendingNodesResponse(
            nodes=[],
            total=0,
            latest_version="abc123",
        )

        assert response.total == 0
        assert len(response.nodes) == 0


class TestCodeSyncSchemas:
    """Additional schema validation tests."""

    def test_status_response_optional_fields(self):
        """Test CodeSyncStatusResponse with optional fields."""
        from datetime import datetime

        from models.schemas import CodeSyncStatusResponse

        response = CodeSyncStatusResponse(
            latest_version=None,
            local_version=None,
            last_fetch=datetime.utcnow(),
            has_update=False,
            outdated_nodes=0,
            total_nodes=0,
        )

        assert response.latest_version is None
        assert response.local_version is None
        assert response.last_fetch is not None

    def test_pending_node_minimal_fields(self):
        """Test PendingNodeResponse with minimal required fields."""
        from models.schemas import PendingNodeResponse

        node = PendingNodeResponse(
            node_id="node-001",
            hostname="test",
            ip_address="10.0.0.1",
            current_version=None,
            code_status="unknown",
        )

        assert node.current_version is None
        assert node.code_status == "unknown"


class TestNodeSync:
    """Tests for POST /api/code-sync/nodes/{node_id}/sync endpoint."""

    def test_node_sync_request_model(self):
        """Test NodeSyncRequest model."""
        from models.schemas import NodeSyncRequest

        request = NodeSyncRequest(restart=True, strategy="graceful")
        assert request.restart is True
        assert request.strategy == "graceful"

    def test_node_sync_response_model(self):
        """Test NodeSyncResponse model."""
        from models.schemas import NodeSyncResponse

        response = NodeSyncResponse(
            success=True,
            message="Sync initiated",
            node_id="node-001",
            job_id="job-123",
        )
        assert response.success is True
        assert response.node_id == "node-001"


class TestFleetSync:
    """Tests for POST /api/code-sync/fleet/sync endpoint."""

    def test_fleet_sync_request_model(self):
        """Test FleetSyncRequest model."""
        from models.schemas import FleetSyncRequest

        request = FleetSyncRequest(
            node_ids=["node-001", "node-002"],
            strategy="rolling",
            batch_size=2,
        )
        assert request.strategy == "rolling"
        assert request.batch_size == 2

    def test_fleet_sync_response_model(self):
        """Test FleetSyncResponse model."""
        from models.schemas import FleetSyncResponse

        response = FleetSyncResponse(
            success=True,
            message="Queued",
            job_id="job-456",
            nodes_queued=5,
        )
        assert response.nodes_queued == 5


class TestCodeDistributor:
    """Tests for CodeDistributor service."""

    def test_distributor_initialization(self):
        """Test CodeDistributor can be initialized."""
        CodeDistributor = code_distributor_module.CodeDistributor

        distributor = CodeDistributor(repo_path="/tmp/test-repo")
        assert distributor.repo_path.as_posix() == "/tmp/test-repo"

    @pytest.mark.asyncio
    async def test_get_current_commit(self):
        """Test getting current commit from real repo."""
        CodeDistributor = code_distributor_module.CodeDistributor

        distributor = CodeDistributor(repo_path="/home/kali/Desktop/AutoBot")
        commit = await distributor.get_current_commit()

        # Should return a 40-char hex string
        assert commit is not None
        assert len(commit) == 40
