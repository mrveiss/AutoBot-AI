# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for SLM Reconciler service.
"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.infrastructure import NodeState
from backend.services.slm.db_service import SLMDatabaseService
from backend.services.slm.reconciler import (
    HEARTBEAT_STALE_THRESHOLD,
    HEARTBEAT_CRITICAL_THRESHOLD,
    REMEDIATION_RETRY_LIMIT,
    SLMReconciler,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def db_service(temp_db):
    """Create a database service with temporary database."""
    return SLMDatabaseService(db_path=temp_db)


@pytest.fixture
def reconciler(db_service):
    """Create a reconciler with test database."""
    return SLMReconciler(db_service=db_service, interval=1)


class TestReconcilerBasics:
    """Test basic reconciler functionality."""

    def test_init_reconciler(self, db_service):
        """Test reconciler initialization."""
        reconciler = SLMReconciler(db_service=db_service)
        assert reconciler.db == db_service
        assert reconciler.interval == 30
        assert not reconciler.is_running

    def test_init_with_custom_interval(self, db_service):
        """Test reconciler with custom interval."""
        reconciler = SLMReconciler(db_service=db_service, interval=10)
        assert reconciler.interval == 10

    def test_stats_before_start(self, reconciler):
        """Test stats before starting."""
        stats = reconciler.stats
        assert stats["running"] is False
        assert stats["run_count"] == 0
        assert stats["last_run"] is None

    @pytest.mark.asyncio
    async def test_start_stop(self, reconciler):
        """Test starting and stopping reconciler."""
        await reconciler.start()
        assert reconciler.is_running

        await reconciler.stop()
        assert not reconciler.is_running


class TestHeartbeatDetection:
    """Test heartbeat staleness detection."""

    @pytest.mark.asyncio
    async def test_stale_heartbeat_marks_degraded(self, reconciler, db_service):
        """ONLINE node with stale heartbeat should become DEGRADED."""
        # Create node and set to ONLINE
        node = db_service.create_node(name="test-node", ip_address="192.168.1.1")
        db_service.update_node_state(node.id, NodeState.PENDING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ENROLLING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ONLINE, validate_transition=False)

        # Set stale heartbeat (61 seconds ago)
        stale_time = datetime.utcnow() - timedelta(seconds=HEARTBEAT_STALE_THRESHOLD + 1)
        db_service.update_node_health(node.id, {}, stale_time)

        # Run reconciliation
        await reconciler._reconcile()

        # Check node is degraded
        updated_node = db_service.get_node(node.id)
        assert updated_node.state == NodeState.DEGRADED.value

    @pytest.mark.asyncio
    async def test_fresh_heartbeat_keeps_online(self, reconciler, db_service):
        """ONLINE node with fresh heartbeat should stay ONLINE."""
        node = db_service.create_node(name="test-node", ip_address="192.168.1.1")
        db_service.update_node_state(node.id, NodeState.PENDING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ENROLLING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ONLINE, validate_transition=False)

        # Set fresh heartbeat
        db_service.update_node_health(node.id, {}, datetime.utcnow())

        await reconciler._reconcile()

        updated_node = db_service.get_node(node.id)
        assert updated_node.state == NodeState.ONLINE.value

    @pytest.mark.asyncio
    async def test_degraded_recovers_with_fresh_heartbeat(self, reconciler, db_service):
        """DEGRADED node with fresh heartbeat should recover to ONLINE."""
        node = db_service.create_node(name="test-node", ip_address="192.168.1.1")
        # Set up as DEGRADED
        db_service.update_node_state(node.id, NodeState.PENDING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ENROLLING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ONLINE, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.DEGRADED, validate_transition=False)

        # Set fresh heartbeat
        db_service.update_node_health(node.id, {}, datetime.utcnow())

        await reconciler._reconcile()

        updated_node = db_service.get_node(node.id)
        assert updated_node.state == NodeState.ONLINE.value

    @pytest.mark.asyncio
    async def test_no_heartbeat_ever_marks_degraded(self, reconciler, db_service):
        """ONLINE node that never sent heartbeat should become DEGRADED."""
        node = db_service.create_node(name="test-node", ip_address="192.168.1.1")
        db_service.update_node_state(node.id, NodeState.PENDING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ENROLLING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ONLINE, validate_transition=False)
        # No heartbeat update

        await reconciler._reconcile()

        updated_node = db_service.get_node(node.id)
        assert updated_node.state == NodeState.DEGRADED.value


class TestErrorEscalation:
    """Test escalation to ERROR state."""

    @pytest.mark.asyncio
    async def test_degraded_escalates_to_error_after_retries(self, reconciler, db_service):
        """DEGRADED node with max failures should escalate to ERROR."""
        node = db_service.create_node(name="test-node", ip_address="192.168.1.1")
        db_service.update_node_state(node.id, NodeState.PENDING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ENROLLING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ONLINE, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.DEGRADED, validate_transition=False)

        # Set critical heartbeat age and max failures
        critical_time = datetime.utcnow() - timedelta(seconds=HEARTBEAT_CRITICAL_THRESHOLD + 1)
        db_service.update_node_health(node.id, {}, critical_time)

        # Simulate max failures
        for _ in range(REMEDIATION_RETRY_LIMIT):
            db_service.increment_failure_count(node.id)

        await reconciler._reconcile()

        updated_node = db_service.get_node(node.id)
        assert updated_node.state == NodeState.ERROR.value


class TestMaintenanceSkipping:
    """Test that maintenance states are skipped."""

    @pytest.mark.asyncio
    async def test_maintenance_draining_skipped(self, reconciler, db_service):
        """Nodes in MAINTENANCE_DRAINING should be skipped."""
        node = db_service.create_node(name="test-node", ip_address="192.168.1.1")
        db_service.update_node_state(node.id, NodeState.PENDING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ENROLLING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ONLINE, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.MAINTENANCE_DRAINING, validate_transition=False)

        # Set stale heartbeat - should be ignored
        stale_time = datetime.utcnow() - timedelta(seconds=HEARTBEAT_CRITICAL_THRESHOLD + 1)
        db_service.update_node_health(node.id, {}, stale_time)

        await reconciler._reconcile()

        updated_node = db_service.get_node(node.id)
        assert updated_node.state == NodeState.MAINTENANCE_DRAINING.value

    @pytest.mark.asyncio
    async def test_pending_skipped(self, reconciler, db_service):
        """Nodes in PENDING should be skipped."""
        node = db_service.create_node(name="test-node", ip_address="192.168.1.1")
        db_service.update_node_state(node.id, NodeState.PENDING, validate_transition=False)

        await reconciler._reconcile()

        updated_node = db_service.get_node(node.id)
        assert updated_node.state == NodeState.PENDING.value


class TestCallbacks:
    """Test callback notifications."""

    @pytest.mark.asyncio
    async def test_state_change_callback_called(self, db_service):
        """State change callback should be called on transition."""
        callback = MagicMock()
        reconciler = SLMReconciler(db_service=db_service, on_state_change=callback)

        node = db_service.create_node(name="test-node", ip_address="192.168.1.1")
        db_service.update_node_state(node.id, NodeState.PENDING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ENROLLING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ONLINE, validate_transition=False)
        # No heartbeat - should trigger degraded

        await reconciler._reconcile()

        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == node.id
        assert args[1] == NodeState.ONLINE.value
        assert args[2] == NodeState.DEGRADED.value

    @pytest.mark.asyncio
    async def test_alert_callback_called(self, db_service):
        """Alert callback should be called on degradation."""
        callback = MagicMock()
        reconciler = SLMReconciler(db_service=db_service, on_alert=callback)

        node = db_service.create_node(name="test-node", ip_address="192.168.1.1")
        db_service.update_node_state(node.id, NodeState.PENDING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ENROLLING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ONLINE, validate_transition=False)

        await reconciler._reconcile()

        callback.assert_called()
        args = callback.call_args[0]
        assert args[0] == node.id
        assert args[1] == "warning"


class TestRemediationAttempts:
    """Test remediation attempt counting."""

    @pytest.mark.asyncio
    async def test_remediation_increments_failure_count(self, reconciler, db_service):
        """Remediation attempt should increment failure count."""
        from backend.models.infrastructure import SLMNode as NodeModel

        node = db_service.create_node(name="test-node", ip_address="192.168.1.1")
        db_service.update_node_state(node.id, NodeState.PENDING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ENROLLING, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.ONLINE, validate_transition=False)
        db_service.update_node_state(node.id, NodeState.DEGRADED, validate_transition=False)

        # Set stale heartbeat (not critical) - need to set directly in DB
        # because update_node_health resets consecutive_failures
        stale_time = datetime.utcnow() - timedelta(seconds=HEARTBEAT_STALE_THRESHOLD + 1)
        with db_service.SessionLocal() as session:
            n = session.query(NodeModel).filter(NodeModel.id == node.id).first()
            n.last_heartbeat = stale_time
            n.consecutive_failures = 0
            session.commit()

        initial_failures = db_service.get_node(node.id).consecutive_failures

        await reconciler._reconcile()

        updated_node = db_service.get_node(node.id)
        assert updated_node.consecutive_failures > initial_failures
