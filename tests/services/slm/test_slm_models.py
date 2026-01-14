# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""Tests for SLM database models."""

import pytest
from datetime import datetime, timedelta
from backend.models.infrastructure import (
    NodeState,
    MaintenanceType,
    DeploymentStrategy,
    ServiceType,
    SLMNode,
    SLMRole,
    SLMStateTransition,
    SLMDeployment,
    SLMMaintenanceWindow,
)


class TestNodeState:
    """Test NodeState enum."""

    def test_all_states_defined(self):
        """Test that all required states are defined."""
        assert NodeState.UNKNOWN
        assert NodeState.PENDING
        assert NodeState.ENROLLING
        assert NodeState.ONLINE
        assert NodeState.DEGRADED
        assert NodeState.ERROR
        assert NodeState.MAINTENANCE_DRAINING
        assert NodeState.MAINTENANCE_PLANNED
        assert NodeState.MAINTENANCE_IMMEDIATE
        assert NodeState.MAINTENANCE_OFFLINE
        assert NodeState.MAINTENANCE_RECOVERING

    def test_is_maintenance_property(self):
        """Test is_maintenance property for maintenance states."""
        # Maintenance states
        assert NodeState.MAINTENANCE_DRAINING.is_maintenance is True
        assert NodeState.MAINTENANCE_PLANNED.is_maintenance is True
        assert NodeState.MAINTENANCE_IMMEDIATE.is_maintenance is True
        assert NodeState.MAINTENANCE_OFFLINE.is_maintenance is True
        assert NodeState.MAINTENANCE_RECOVERING.is_maintenance is True

        # Non-maintenance states
        assert NodeState.ONLINE.is_maintenance is False
        assert NodeState.ERROR.is_maintenance is False
        assert NodeState.DEGRADED.is_maintenance is False


class TestSLMNode:
    """Test SLMNode model."""

    def test_create_node(self, db_session):
        """Test creating a new SLM node."""
        node = SLMNode(
            name="test-node-01",
            ip_address="172.16.168.30",
            ssh_port=22,
            ssh_user="autobot",
            state=NodeState.PENDING,
            primary_role="worker",
            capability_tags=["cpu", "gpu"],
        )
        db_session.add(node)
        db_session.commit()

        # Retrieve and verify
        retrieved = db_session.query(SLMNode).filter_by(name="test-node-01").first()
        assert retrieved is not None
        assert retrieved.name == "test-node-01"
        assert retrieved.ip_address == "172.16.168.30"
        assert retrieved.state == NodeState.PENDING
        assert retrieved.capability_tags == ["cpu", "gpu"]

    def test_node_ip_unique(self, db_session):
        """Test that IP address must be unique."""
        node1 = SLMNode(
            name="node1",
            ip_address="172.16.168.30",
            ssh_port=22,
            ssh_user="autobot",
            state=NodeState.PENDING,
        )
        node2 = SLMNode(
            name="node2",
            ip_address="172.16.168.30",  # Duplicate IP
            ssh_port=22,
            ssh_user="autobot",
            state=NodeState.PENDING,
        )
        db_session.add(node1)
        db_session.commit()

        db_session.add(node2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()

    def test_node_state_tracking(self, db_session):
        """Test node state change tracking."""
        node = SLMNode(
            name="test-node",
            ip_address="172.16.168.31",
            ssh_port=22,
            ssh_user="autobot",
            state=NodeState.PENDING,
        )
        db_session.add(node)
        db_session.commit()

        # Update state
        node.state = NodeState.ONLINE
        node.state_changed = datetime.utcnow()
        db_session.commit()

        # Verify state changed
        retrieved = db_session.query(SLMNode).filter_by(name="test-node").first()
        assert retrieved.state == NodeState.ONLINE
        assert retrieved.state_changed is not None


class TestSLMStateTransition:
    """Test SLMStateTransition model."""

    def test_create_state_transition(self, db_session):
        """Test creating a state transition record."""
        # Create a node
        node = SLMNode(
            name="test-node",
            ip_address="172.16.168.32",
            ssh_port=22,
            ssh_user="autobot",
            state=NodeState.ONLINE,
        )
        db_session.add(node)
        db_session.commit()

        # Create transition
        transition = SLMStateTransition(
            node_id=node.id,
            from_state=NodeState.PENDING,
            to_state=NodeState.ONLINE,
            trigger="enrollment_complete",
            details={"duration_seconds": 45},
        )
        db_session.add(transition)
        db_session.commit()

        # Verify
        retrieved = db_session.query(SLMStateTransition).filter_by(node_id=node.id).first()
        assert retrieved is not None
        assert retrieved.from_state == NodeState.PENDING
        assert retrieved.to_state == NodeState.ONLINE
        assert retrieved.trigger == "enrollment_complete"
        assert retrieved.details["duration_seconds"] == 45

    def test_transition_relationship(self, db_session):
        """Test relationship between node and transitions."""
        node = SLMNode(
            name="test-node",
            ip_address="172.16.168.33",
            ssh_port=22,
            ssh_user="autobot",
            state=NodeState.ONLINE,
        )
        db_session.add(node)
        db_session.commit()

        # Add multiple transitions
        for i in range(3):
            transition = SLMStateTransition(
                node_id=node.id,
                from_state=NodeState.PENDING,
                to_state=NodeState.ONLINE,
                trigger=f"test_{i}",
            )
            db_session.add(transition)
        db_session.commit()

        # Verify relationship
        retrieved = db_session.query(SLMNode).filter_by(name="test-node").first()
        assert len(retrieved.state_transitions) == 3

    def test_cascade_delete_with_node(self, db_session):
        """Test that deleting node cascades to transitions."""
        node = SLMNode(
            name="cascade-test",
            ip_address="192.168.1.200",
            state=NodeState.ONLINE.value,
        )
        db_session.add(node)
        db_session.commit()

        transition = SLMStateTransition(
            node_id=node.id,
            from_state=NodeState.PENDING.value,
            to_state=NodeState.ONLINE.value,
            trigger="test",
        )
        db_session.add(transition)
        db_session.commit()

        # Delete the node
        db_session.delete(node)
        db_session.commit()

        # Verify transition is also deleted
        remaining = db_session.query(SLMStateTransition).filter_by(node_id=node.id).all()
        assert len(remaining) == 0


class TestSLMRole:
    """Test SLMRole model."""

    def test_create_role(self, db_session):
        """Test creating a role definition."""
        role = SLMRole(
            name="redis-server",
            description="Redis database server",
            service_type=ServiceType.STATEFUL,
            services=["redis-server"],
            required_tags=["storage"],
            install_playbook="redis-install.yml",
            purge_playbook="redis-purge.yml",
        )
        db_session.add(role)
        db_session.commit()

        # Verify
        retrieved = db_session.query(SLMRole).filter_by(name="redis-server").first()
        assert retrieved is not None
        assert retrieved.service_type == ServiceType.STATEFUL
        assert retrieved.services == ["redis-server"]

    def test_role_name_unique(self, db_session):
        """Test that role name must be unique."""
        role1 = SLMRole(
            name="worker",
            service_type=ServiceType.STATELESS,
            services=["app"],
        )
        role2 = SLMRole(
            name="worker",  # Duplicate name
            service_type=ServiceType.STATEFUL,
            services=["db"],
        )
        db_session.add(role1)
        db_session.commit()

        db_session.add(role2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()


class TestSLMDeployment:
    """Test SLMDeployment model."""

    def test_create_deployment(self, db_session):
        """Test creating a deployment record."""
        deployment = SLMDeployment(
            role_name="redis-server",
            target_nodes=["node1", "node2"],
            strategy=DeploymentStrategy.SEQUENTIAL,
            strategy_params={"batch_size": 2, "delay_seconds": 30},
            status="in_progress",
            initiated_by="admin",
        )
        db_session.add(deployment)
        db_session.commit()

        # Verify
        retrieved = db_session.query(SLMDeployment).first()
        assert retrieved is not None
        assert retrieved.role_name == "redis-server"
        assert retrieved.strategy == DeploymentStrategy.SEQUENTIAL
        assert retrieved.strategy_params == {"batch_size": 2, "delay_seconds": 30}
        assert retrieved.rollback_at is None


class TestSLMMaintenanceWindow:
    """Test SLMMaintenanceWindow model."""

    def test_create_maintenance_window(self, db_session):
        """Test creating a maintenance window."""
        # Create a node first
        node = SLMNode(
            name="test-node",
            ip_address="172.16.168.40",
            ssh_port=22,
            ssh_user="autobot",
            state=NodeState.ONLINE,
        )
        db_session.add(node)
        db_session.commit()

        now = datetime.utcnow()
        window = SLMMaintenanceWindow(
            node_id=node.id,
            maintenance_type=MaintenanceType.PLANNED,
            scheduled_start=now + timedelta(hours=1),
            scheduled_end=now + timedelta(hours=2),
            reason="System updates",
            approved_by="admin",
            executed=False,
        )
        db_session.add(window)
        db_session.commit()

        # Verify
        retrieved = db_session.query(SLMMaintenanceWindow).first()
        assert retrieved is not None
        assert retrieved.node_id == node.id
        assert retrieved.maintenance_type == MaintenanceType.PLANNED
        assert retrieved.executed is False
