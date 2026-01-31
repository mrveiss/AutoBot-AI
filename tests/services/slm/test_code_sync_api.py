# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Code Sync API endpoints (Issue #741).
"""


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
