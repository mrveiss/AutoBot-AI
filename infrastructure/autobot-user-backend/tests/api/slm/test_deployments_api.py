# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for SLM Deployments API.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.api.slm.deployments import router
from backend.models.infrastructure import DeploymentStrategy as DeploymentStrategyType
from backend.services.slm.deployment_orchestrator import (
    DeploymentContext,
    DeploymentOrchestrator,
    DeploymentStatus,
    DeploymentStep,
    DeploymentStepType,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


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
def mock_orchestrator():
    """Create mock orchestrator."""
    orch = MagicMock(spec=DeploymentOrchestrator)
    orch.active_deployments = []
    return orch


@pytest.fixture
def sample_context():
    """Create sample deployment context."""
    return DeploymentContext(
        deployment_id="deploy-123",
        strategy=DeploymentStrategyType.SEQUENTIAL,
        role_name="worker",
        target_nodes=["node-1", "node-2"],
        playbook_path="/path/to/playbook.yml",
    )


class TestListDeployments:
    """Test list deployments endpoint."""

    def test_list_empty(self, client, mock_orchestrator):
        """Test listing with no deployments."""
        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments")

        assert response.status_code == 200
        data = response.json()
        assert data["deployments"] == []
        assert data["total"] == 0

    def test_list_with_deployments(self, client, mock_orchestrator, sample_context):
        """Test listing with deployments."""
        mock_orchestrator.active_deployments = [sample_context]

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["deployments"][0]["deployment_id"] == "deploy-123"

    def test_list_filter_by_status(self, client, mock_orchestrator, sample_context):
        """Test filtering by status."""
        sample_context.status = DeploymentStatus.RUNNING
        mock_orchestrator.active_deployments = [sample_context]

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments?status_filter=running")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_list_filter_excludes_other_status(
        self, client, mock_orchestrator, sample_context
    ):
        """Test filter excludes other statuses."""
        sample_context.status = DeploymentStatus.QUEUED
        mock_orchestrator.active_deployments = [sample_context]

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments?status_filter=running")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


class TestCreateDeployment:
    """Test create deployment endpoint."""

    def test_create_deployment_success(self, client, mock_orchestrator, sample_context):
        """Test successful deployment creation."""
        mock_orchestrator.create_deployment = AsyncMock(return_value=sample_context)

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post(
                "/v1/slm/deployments",
                json={
                    "role_name": "worker",
                    "target_nodes": ["node-1", "node-2"],
                    "strategy": "sequential",
                    "playbook_path": "/path/to/playbook.yml",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["deployment_id"] == "deploy-123"
        assert data["role_name"] == "worker"
        assert data["status"] == "queued"

    def test_create_deployment_invalid_strategy(self, client, mock_orchestrator):
        """Test create with invalid strategy."""
        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post(
                "/v1/slm/deployments",
                json={
                    "role_name": "worker",
                    "target_nodes": ["node-1"],
                    "strategy": "invalid_strategy",
                },
            )

        assert response.status_code == 400
        assert "Invalid strategy" in response.json()["detail"]

    def test_create_deployment_missing_fields(self, client):
        """Test create with missing required fields."""
        response = client.post(
            "/v1/slm/deployments",
            json={"role_name": "worker"},  # Missing target_nodes
        )

        assert response.status_code == 422


class TestGetDeployment:
    """Test get deployment endpoint."""

    def test_get_deployment_success(self, client, mock_orchestrator, sample_context):
        """Test getting deployment by ID."""
        mock_orchestrator.get_deployment.return_value = sample_context

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments/deploy-123")

        assert response.status_code == 200
        data = response.json()
        assert data["deployment_id"] == "deploy-123"

    def test_get_deployment_not_found(self, client, mock_orchestrator):
        """Test getting nonexistent deployment."""
        mock_orchestrator.get_deployment.return_value = None

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments/nonexistent")

        assert response.status_code == 404


class TestExecuteDeployment:
    """Test execute deployment endpoint."""

    def test_execute_deployment_success(
        self, client, mock_orchestrator, sample_context
    ):
        """Test executing a queued deployment."""
        sample_context.status = DeploymentStatus.QUEUED
        mock_orchestrator.get_deployment.return_value = sample_context

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/deploy-123/execute")

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "execute"
        assert data["success"] is True

    def test_execute_not_queued(self, client, mock_orchestrator, sample_context):
        """Test executing a non-queued deployment."""
        sample_context.status = DeploymentStatus.RUNNING
        mock_orchestrator.get_deployment.return_value = sample_context

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/deploy-123/execute")

        assert response.status_code == 400

    def test_execute_not_found(self, client, mock_orchestrator):
        """Test executing nonexistent deployment."""
        mock_orchestrator.get_deployment.return_value = None

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/nonexistent/execute")

        assert response.status_code == 404


class TestCancelDeployment:
    """Test cancel deployment endpoint."""

    def test_cancel_deployment_success(self, client, mock_orchestrator, sample_context):
        """Test cancelling a queued deployment."""
        mock_orchestrator.cancel_deployment = AsyncMock(return_value=True)

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/deploy-123/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "cancel"
        assert data["success"] is True

    def test_cancel_not_cancellable(self, client, mock_orchestrator, sample_context):
        """Test cancelling when not cancellable."""
        sample_context.status = DeploymentStatus.RUNNING
        mock_orchestrator.cancel_deployment = AsyncMock(return_value=False)
        mock_orchestrator.get_deployment.return_value = sample_context

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/deploy-123/cancel")

        assert response.status_code == 400

    def test_cancel_not_found(self, client, mock_orchestrator):
        """Test cancelling nonexistent deployment."""
        mock_orchestrator.cancel_deployment = AsyncMock(return_value=False)
        mock_orchestrator.get_deployment.return_value = None

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/nonexistent/cancel")

        assert response.status_code == 404


class TestRollbackDeployment:
    """Test rollback deployment endpoint."""

    def test_rollback_deployment_success(
        self, client, mock_orchestrator, sample_context
    ):
        """Test triggering rollback."""
        mock_orchestrator.get_deployment.return_value = sample_context
        mock_orchestrator.trigger_rollback = AsyncMock(return_value=True)

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/deploy-123/rollback")

        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "rollback"
        assert data["success"] is True

    def test_rollback_no_nodes(self, client, mock_orchestrator, sample_context):
        """Test rollback with no nodes to rollback."""
        mock_orchestrator.get_deployment.return_value = sample_context
        mock_orchestrator.trigger_rollback = AsyncMock(return_value=False)

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/deploy-123/rollback")

        assert response.status_code == 400

    def test_rollback_not_found(self, client, mock_orchestrator):
        """Test rollback nonexistent deployment."""
        mock_orchestrator.get_deployment.return_value = None

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/nonexistent/rollback")

        assert response.status_code == 404


class TestDeploymentResponseFormat:
    """Test deployment response format."""

    def test_response_includes_steps(self, client, mock_orchestrator, sample_context):
        """Test response includes deployment steps."""
        from datetime import datetime

        sample_context.steps = [
            DeploymentStep(
                step_type=DeploymentStepType.DRAIN,
                node_id="node-1",
                node_name="test-node",
                description="Draining node",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                success=True,
            )
        ]
        mock_orchestrator.get_deployment.return_value = sample_context

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments/deploy-123")

        assert response.status_code == 200
        data = response.json()
        assert len(data["steps"]) == 1
        assert data["steps"][0]["step_type"] == "drain"
        assert data["steps"][0]["success"] is True

    def test_response_timestamps_formatted(
        self, client, mock_orchestrator, sample_context
    ):
        """Test timestamps are ISO formatted."""
        from datetime import datetime

        sample_context.started_at = datetime(2025, 1, 15, 10, 30, 0)
        mock_orchestrator.get_deployment.return_value = sample_context

        with patch(
            "backend.api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments/deploy-123")

        assert response.status_code == 200
        data = response.json()
        assert data["started_at"] == "2025-01-15T10:30:00"
