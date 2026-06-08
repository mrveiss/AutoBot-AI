# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for SLM Deployments API.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.slm.deployments import router
from models.infrastructure import DeploymentStrategy as DeploymentStrategyType
from services.slm.deployment_bridge import (
    DeploymentContext,
    DeploymentCoordinator,
    DeploymentStatus,
    DeploymentStep,
    DeploymentStepType,
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
def mock_orchestrator():
    """Create mock orchestrator."""
    orch = MagicMock(spec=DeploymentCoordinator)
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
            "api.slm.deployments.get_orchestrator",
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
            "api.slm.deployments.get_orchestrator",
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
            "api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments?status_filter=running")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_list_filter_excludes_other_status(self, client, mock_orchestrator, sample_context):
        """Test filter excludes other statuses."""
        sample_context.status = DeploymentStatus.QUEUED
        mock_orchestrator.active_deployments = [sample_context]

        with patch(
            "api.slm.deployments.get_orchestrator",
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
            "api.slm.deployments.get_orchestrator",
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
            "api.slm.deployments.get_orchestrator",
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

        # Pydantic v2 rejects unknown enum values at request validation time (422).
        assert response.status_code == 422

    def test_create_deployment_missing_fields(self, client, mock_orchestrator):
        """Test create with missing required fields — Pydantic returns 422."""
        with patch(
            "api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
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
            "api.slm.deployments.get_orchestrator",
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
            "api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments/nonexistent")

        assert response.status_code == 404


class TestExecuteDeployment:
    """Test execute deployment endpoint."""

    def test_execute_deployment_success(self, client, mock_orchestrator, sample_context):
        """Test executing a queued deployment."""
        sample_context.status = DeploymentStatus.QUEUED
        mock_orchestrator.get_deployment.return_value = sample_context

        with patch(
            "api.slm.deployments.get_orchestrator",
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
            "api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/deploy-123/execute")

        assert response.status_code == 400

    def test_execute_not_found(self, client, mock_orchestrator):
        """Test executing nonexistent deployment."""
        mock_orchestrator.get_deployment.return_value = None

        with patch(
            "api.slm.deployments.get_orchestrator",
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
            "api.slm.deployments.get_orchestrator",
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
            "api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/deploy-123/cancel")

        assert response.status_code == 400

    def test_cancel_not_found(self, client, mock_orchestrator):
        """Test cancelling nonexistent deployment."""
        mock_orchestrator.cancel_deployment = AsyncMock(return_value=False)
        mock_orchestrator.get_deployment.return_value = None

        with patch(
            "api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/nonexistent/cancel")

        assert response.status_code == 404


class TestRollbackDeployment:
    """Test rollback deployment endpoint."""

    def test_rollback_deployment_success(self, client, mock_orchestrator, sample_context):
        """Test triggering rollback."""
        mock_orchestrator.get_deployment.return_value = sample_context
        mock_orchestrator.trigger_rollback = AsyncMock(return_value=True)

        with patch(
            "api.slm.deployments.get_orchestrator",
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
            "api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/deploy-123/rollback")

        assert response.status_code == 400

    def test_rollback_not_found(self, client, mock_orchestrator):
        """Test rollback nonexistent deployment."""
        mock_orchestrator.get_deployment.return_value = None

        with patch(
            "api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.post("/v1/slm/deployments/nonexistent/rollback")

        assert response.status_code == 404


class TestDeploymentResponseFormat:
    """Test deployment response format."""

    def test_response_includes_steps(self, client, mock_orchestrator, sample_context):
        """Test response includes deployment steps."""
        from autobot_shared.datetime_utils import datetime_now

        sample_context.steps = [
            DeploymentStep(
                step_type=DeploymentStepType.DRAIN,
                node_id="node-1",
                node_name="test-node",
                description="Draining node",
                started_at=datetime_now(),
                completed_at=datetime_now(),
                success=True,
            )
        ]
        mock_orchestrator.get_deployment.return_value = sample_context

        with patch(
            "api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments/deploy-123")

        assert response.status_code == 200
        data = response.json()
        assert len(data["steps"]) == 1
        assert data["steps"][0]["step_type"] == "drain"
        assert data["steps"][0]["success"] is True

    def test_response_timestamps_formatted(self, client, mock_orchestrator, sample_context):
        """Test timestamps are ISO formatted."""
        from datetime import datetime

        sample_context.started_at = datetime(2025, 1, 15, 10, 30, 0)
        mock_orchestrator.get_deployment.return_value = sample_context

        with patch(
            "api.slm.deployments.get_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = client.get("/v1/slm/deployments/deploy-123")

        assert response.status_code == 200
        data = response.json()
        assert data["started_at"] == "2025-01-15T10:30:00"


# =============================================================================
# SLMDeploymentBridge integration tests (real bridge + test-double
# SLM HTTP client — not MagicMock wrapping the whole orchestrator)
# =============================================================================


class FakeSLMClient:
    """
    Test-double for the SLM HTTP client.

    Returns deterministic canned responses so tests exercise the real
    SLMDeploymentBridge translation logic without hitting a live SLM.
    """

    def __init__(self, deployment_id: str = "slm-deploy-001", node_id: str = "node-99"):
        self._deployment_id = deployment_id
        self._node_id = node_id

    async def create_deployment(self, payload: dict) -> dict:
        return {
            "deployment_id": self._deployment_id,
            "node_id": payload.get("node_id", self._node_id),
            "status": "running",
            "started_at": None,
            "completed_at": None,
            "error": None,
        }

    async def get_deployment(self, deployment_id: str) -> dict:
        return {
            "deployment_id": deployment_id,
            "node_id": self._node_id,
            "status": "completed",
            "started_at": None,
            "completed_at": None,
            "error": None,
        }

    async def list_deployments(self, node_id=None) -> dict:
        return {
            "deployments": [
                {
                    "deployment_id": self._deployment_id,
                    "node_id": self._node_id,
                    "status": "completed",
                    "started_at": None,
                    "completed_at": None,
                    "error": None,
                }
            ]
        }


class TestSLMDeploymentBridgeIntegration:
    """Integration tests for SLMDeploymentBridge with a test-double SLM client."""

    @pytest.fixture
    def fake_client(self):
        return FakeSLMClient()

    @pytest.fixture
    def slm_orch(self, fake_client):
        from services.slm.deployment_bridge import SLMDeploymentBridge

        return SLMDeploymentBridge(slm_client=fake_client)

    @pytest.mark.asyncio
    async def test_deploy_docker_calls_slm_and_maps_response(self, slm_orch):
        """deploy_docker translates the request and returns a DockerDeploymentStatus."""
        from models.infrastructure import DockerContainerSpec, DockerDeploymentRequest

        request = DockerDeploymentRequest(
            node_id="node-99",
            containers=[
                DockerContainerSpec(
                    name="my-app",
                    image="my-org/my-app",
                    tag="1.2.3",
                )
            ],
        )
        result = await slm_orch.deploy_docker(request)

        assert result.deployment_id == "slm-deploy-001"
        assert result.node_id == "node-99"
        assert result.status == "running"

    @pytest.mark.asyncio
    async def test_deploy_docker_builds_extra_vars_with_ports(self, fake_client):
        """build_extra_vars correctly serialises port mappings."""
        from models.infrastructure import (
            DockerContainerSpec,
            DockerDeploymentRequest,
            PortMapping,
        )
        from services.slm.deployment_bridge import SLMDeploymentBridge

        captured: dict = {}

        async def capturing_create(payload):
            captured.update(payload)
            return {
                "deployment_id": "x",
                "node_id": "n",
                "status": "queued",
                "started_at": None,
                "completed_at": None,
                "error": None,
            }

        fake_client.create_deployment = capturing_create
        orch = SLMDeploymentBridge(slm_client=fake_client)

        request = DockerDeploymentRequest(
            node_id="node-1",
            containers=[
                DockerContainerSpec(
                    name="svc",
                    image="acme/svc",
                    tag="latest",
                    ports=[PortMapping(host_port=8080, container_port=80)],
                    environment={"ENV": "prod"},
                )
            ],
        )
        await orch.deploy_docker(request)

        containers = captured["extra_data"]["extra_vars"]["docker_containers"]
        assert len(containers) == 1
        assert containers[0]["ports"] == ["8080:80/tcp"]
        assert containers[0]["environment"] == {"ENV": "prod"}

    @pytest.mark.asyncio
    async def test_get_deployment_returns_status(self, slm_orch):
        """get_deployment fetches and maps a deployment by ID."""
        result = await slm_orch.get_deployment("slm-deploy-001")

        assert result.deployment_id == "slm-deploy-001"
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_list_deployments_returns_list(self, slm_orch):
        """list_deployments returns a non-empty list from the SLM."""
        results = await slm_orch.list_deployments()

        assert len(results) == 1
        assert results[0].deployment_id == "slm-deploy-001"

    @pytest.mark.asyncio
    async def test_list_deployments_node_filter_forwarded(self, fake_client):
        """node_id filter is forwarded to the SLM client."""
        from services.slm.deployment_bridge import SLMDeploymentBridge

        received_kwargs: dict = {}

        async def spy_list(node_id=None):
            received_kwargs["node_id"] = node_id
            return {"deployments": []}

        fake_client.list_deployments = spy_list
        orch = SLMDeploymentBridge(slm_client=fake_client)
        await orch.list_deployments(node_id="node-42")

        assert received_kwargs["node_id"] == "node-42"
