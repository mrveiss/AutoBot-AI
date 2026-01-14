# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM database service."""

import pytest
from datetime import datetime
from backend.models.infrastructure import NodeState
from backend.services.slm.db_service import SLMDatabaseService
from backend.services.slm.state_machine import InvalidStateTransition


@pytest.fixture
def slm_db(tmp_path):
    """Create SLM database service with temp database."""
    db_path = tmp_path / "test_slm.db"
    return SLMDatabaseService(db_path=str(db_path))


class TestSLMNodeCRUD:
    """Test SLM node CRUD operations."""

    def test_create_node(self, slm_db):
        """Test creating a new node."""
        node = slm_db.create_node(
            name="test-node",
            ip_address="192.168.1.100",
            ssh_user="autobot",
            capability_tags=["can_be_redis"],
        )
        assert node.id is not None
        assert node.name == "test-node"
        assert node.state == NodeState.UNKNOWN

    def test_get_node_by_name(self, slm_db):
        """Test retrieving node by name."""
        slm_db.create_node(name="redis-vm", ip_address="172.16.168.23")
        node = slm_db.get_node_by_name("redis-vm")
        assert node is not None
        assert node.ip_address == "172.16.168.23"

    def test_get_node_by_ip(self, slm_db):
        """Test retrieving node by IP address."""
        slm_db.create_node(name="frontend-vm", ip_address="172.16.168.21")
        node = slm_db.get_node_by_ip("172.16.168.21")
        assert node is not None
        assert node.name == "frontend-vm"

    def test_get_all_nodes(self, slm_db):
        """Test retrieving all nodes."""
        slm_db.create_node(name="node1", ip_address="192.168.1.1")
        slm_db.create_node(name="node2", ip_address="192.168.1.2")
        slm_db.create_node(name="node3", ip_address="192.168.1.3")

        all_nodes = slm_db.get_all_nodes()
        assert len(all_nodes) == 3

    def test_get_all_nodes_filtered_by_state(self, slm_db):
        """Test retrieving nodes filtered by state."""
        node1 = slm_db.create_node(name="node1", ip_address="192.168.1.1")
        node2 = slm_db.create_node(name="node2", ip_address="192.168.1.2")

        # Transition node1 to PENDING
        slm_db.update_node_state(node1.id, NodeState.PENDING, trigger="test")

        pending_nodes = slm_db.get_all_nodes(state=NodeState.PENDING)
        assert len(pending_nodes) == 1
        assert pending_nodes[0].name == "node1"

    def test_update_node_state(self, slm_db):
        """Test updating node state with transition logging."""
        node = slm_db.create_node(name="frontend-vm", ip_address="172.16.168.21")
        slm_db.update_node_state(
            node.id,
            NodeState.PENDING,
            trigger="api",
            details={"user": "admin"},
        )
        updated = slm_db.get_node(node.id)
        assert updated.state == NodeState.PENDING

    def test_invalid_state_transition_raises_error(self, slm_db):
        """Test that invalid state transitions raise InvalidStateTransition."""
        node = slm_db.create_node(name="test-vm", ip_address="192.168.1.1")

        # UNKNOWN -> ONLINE is not a valid transition
        with pytest.raises(InvalidStateTransition):
            slm_db.update_node_state(node.id, NodeState.ONLINE, trigger="test")

    def test_state_transition_logged(self, slm_db):
        """Test that state transitions are logged."""
        node = slm_db.create_node(name="npu-vm", ip_address="172.16.168.22")
        slm_db.update_node_state(node.id, NodeState.PENDING, trigger="api")

        transitions = slm_db.get_state_transitions(node.id)
        assert len(transitions) == 1
        assert transitions[0].from_state == NodeState.UNKNOWN
        assert transitions[0].to_state == NodeState.PENDING

    def test_update_node_health(self, slm_db):
        """Test updating node health data."""
        node = slm_db.create_node(name="test-vm", ip_address="192.168.1.1")

        health_data = {
            "cpu_percent": 45.2,
            "memory_percent": 68.5,
            "disk_usage": 72.0,
        }

        updated = slm_db.update_node_health(node.id, health_data)
        assert updated.last_heartbeat is not None
        assert updated.consecutive_failures == 0

    def test_increment_failure_count(self, slm_db):
        """Test incrementing consecutive failure count."""
        node = slm_db.create_node(name="test-vm", ip_address="192.168.1.1")

        count1 = slm_db.increment_failure_count(node.id)
        assert count1 == 1

        count2 = slm_db.increment_failure_count(node.id)
        assert count2 == 2

    def test_delete_node(self, slm_db):
        """Test deleting a node."""
        node = slm_db.create_node(name="delete-test", ip_address="192.168.1.200")
        node_id = node.id

        result = slm_db.delete_node(node_id)
        assert result is True

        # Verify it's deleted
        assert slm_db.get_node(node_id) is None

    def test_delete_nonexistent_node(self, slm_db):
        """Test deleting a non-existent node returns False."""
        result = slm_db.delete_node("nonexistent-id")
        assert result is False


class TestSLMRoleCRUD:
    """Test SLM role CRUD operations."""

    def test_create_role(self, slm_db):
        """Test creating a new role."""
        role = slm_db.create_role(
            name="test-redis",
            description="Test Redis Stack data layer",
            service_type="stateful",
            services=["redis-stack-server"],
            health_checks=[{"type": "tcp", "port": 6379}],
        )
        assert role.id is not None
        assert role.name == "test-redis"
        assert role.service_type.value == "stateful"

    def test_get_role_by_name(self, slm_db):
        """Test retrieving role by name."""
        slm_db.create_role(
            name="test-frontend",
            description="Test Vue.js frontend",
            service_type="stateless",
            services=["nginx"],
        )
        role = slm_db.get_role_by_name("test-frontend")
        assert role is not None
        assert "nginx" in role.services

    def test_get_all_roles(self, slm_db):
        """Test retrieving all roles."""
        slm_db.create_role(name="test-db", service_type="stateful")
        slm_db.create_role(name="test-web", service_type="stateless")
        slm_db.create_role(name="test-worker", service_type="stateless")

        roles = slm_db.get_all_roles()
        # 3 custom + 5 default = 8 total
        assert len(roles) == 8


class TestSLMStatistics:
    """Test SLM statistics generation."""

    def test_get_statistics(self, slm_db):
        """Test getting SLM statistics."""
        # Create nodes
        node1 = slm_db.create_node(name="node1", ip_address="192.168.1.1")
        node2 = slm_db.create_node(name="node2", ip_address="192.168.1.2")
        node3 = slm_db.create_node(name="node3", ip_address="192.168.1.3")

        # Transition some nodes
        slm_db.update_node_state(node1.id, NodeState.PENDING, trigger="test")
        slm_db.update_node_state(node2.id, NodeState.PENDING, trigger="test")

        # Create custom roles (5 default roles already exist)
        slm_db.create_role(name="test-service-1", service_type="stateful")
        slm_db.create_role(name="test-service-2", service_type="stateless")

        stats = slm_db.get_statistics()

        assert stats["total_nodes"] == 3
        assert stats["nodes_by_state"]["unknown"] == 1
        assert stats["nodes_by_state"]["pending"] == 2
        assert stats["total_roles"] == 7  # 5 default + 2 custom
        assert stats["total_transitions"] == 2
