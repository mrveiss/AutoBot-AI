# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM nodes API."""

from unittest.mock import MagicMock, patch

import pytest

# Import the FastAPI app - we'll need to create a test app fixture
from api.slm.nodes import router as nodes_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with SLM routes."""
    app = FastAPI()
    app.include_router(nodes_router, prefix="/api/v1")
    return TestClient(app)


@pytest.fixture
def mock_db_service():
    """Mock the SLM database service."""
    with patch("backend.api.slm.nodes.get_db_service") as mock:
        mock_service = MagicMock()
        mock.return_value = mock_service
        yield mock_service


class TestNodesAPI:
    """Test SLM nodes REST API."""

    def test_list_nodes_empty(self, client, mock_db_service):
        """Test listing nodes when empty."""
        mock_db_service.get_all_nodes.return_value = []

        response = client.get("/api/v1/slm/nodes")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert data["nodes"] == []
        assert data["total"] == 0

    def test_create_node(self, client, mock_db_service):
        """Test creating a new node."""
        mock_node = MagicMock()
        mock_node.id = "test-123"
        mock_node.name = "test-node"
        mock_node.ip_address = "192.168.1.100"
        mock_node.ssh_port = 22
        mock_node.ssh_user = "autobot"
        mock_node.state = "unknown"
        mock_node.current_role = None
        mock_node.capability_tags = ["can_be_redis"]
        mock_node.consecutive_failures = 0
        mock_node.last_heartbeat = None

        mock_db_service.get_node_by_name.return_value = None
        mock_db_service.get_node_by_ip.return_value = None
        mock_db_service.create_node.return_value = mock_node

        response = client.post(
            "/api/v1/slm/nodes",
            json={
                "name": "test-node",
                "ip_address": "192.168.1.100",
                "capability_tags": ["can_be_redis"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-node"
        assert data["state"] == "unknown"

    def test_get_node(self, client, mock_db_service):
        """Test getting node by ID."""
        mock_node = MagicMock()
        mock_node.id = "test-123"
        mock_node.name = "get-test"
        mock_node.ip_address = "192.168.1.101"
        mock_node.ssh_port = 22
        mock_node.ssh_user = "autobot"
        mock_node.state = "pending"
        mock_node.current_role = None
        mock_node.capability_tags = []
        mock_node.consecutive_failures = 0
        mock_node.last_heartbeat = None

        mock_db_service.get_node.return_value = mock_node

        response = client.get("/api/v1/slm/nodes/test-123")
        assert response.status_code == 200
        assert response.json()["name"] == "get-test"

    def test_get_node_not_found(self, client, mock_db_service):
        """Test getting non-existent node."""
        mock_db_service.get_node.return_value = None

        response = client.get("/api/v1/slm/nodes/nonexistent")
        assert response.status_code == 404
