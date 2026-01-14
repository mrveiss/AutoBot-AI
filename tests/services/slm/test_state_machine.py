# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM state machine."""

import pytest
from backend.models.infrastructure import NodeState
from backend.services.slm.state_machine import (
    SLMStateMachine,
    InvalidStateTransition,
    VALID_TRANSITIONS,
)


class TestStateMachineTransitions:
    """Test valid and invalid state transitions."""

    def test_valid_transition_unknown_to_pending(self):
        """UNKNOWN → PENDING is valid."""
        sm = SLMStateMachine()
        assert sm.can_transition(NodeState.UNKNOWN, NodeState.PENDING)

    def test_valid_transition_pending_to_enrolling(self):
        """PENDING → ENROLLING is valid."""
        sm = SLMStateMachine()
        assert sm.can_transition(NodeState.PENDING, NodeState.ENROLLING)

    def test_valid_transition_enrolling_to_online(self):
        """ENROLLING → ONLINE is valid."""
        sm = SLMStateMachine()
        assert sm.can_transition(NodeState.ENROLLING, NodeState.ONLINE)

    def test_valid_transition_online_to_degraded(self):
        """ONLINE → DEGRADED is valid."""
        sm = SLMStateMachine()
        assert sm.can_transition(NodeState.ONLINE, NodeState.DEGRADED)

    def test_invalid_transition_online_to_pending(self):
        """ONLINE → PENDING is invalid."""
        sm = SLMStateMachine()
        assert not sm.can_transition(NodeState.ONLINE, NodeState.PENDING)

    def test_invalid_transition_raises_exception(self):
        """Invalid transition raises InvalidStateTransition."""
        sm = SLMStateMachine()
        with pytest.raises(InvalidStateTransition):
            sm.transition(NodeState.ONLINE, NodeState.PENDING)

    def test_transition_returns_new_state(self):
        """Valid transition returns new state."""
        sm = SLMStateMachine()
        new_state = sm.transition(NodeState.UNKNOWN, NodeState.PENDING)
        assert new_state == NodeState.PENDING


class TestMaintenanceTransitions:
    """Test maintenance mode transitions."""

    def test_online_to_maintenance_draining(self):
        """ONLINE → MAINTENANCE_DRAINING is valid."""
        sm = SLMStateMachine()
        assert sm.can_transition(NodeState.ONLINE, NodeState.MAINTENANCE_DRAINING)

    def test_maintenance_draining_to_offline(self):
        """MAINTENANCE_DRAINING → MAINTENANCE_OFFLINE is valid."""
        sm = SLMStateMachine()
        assert sm.can_transition(NodeState.MAINTENANCE_DRAINING, NodeState.MAINTENANCE_OFFLINE)

    def test_maintenance_offline_to_recovering(self):
        """MAINTENANCE_OFFLINE → MAINTENANCE_RECOVERING is valid."""
        sm = SLMStateMachine()
        assert sm.can_transition(NodeState.MAINTENANCE_OFFLINE, NodeState.MAINTENANCE_RECOVERING)

    def test_maintenance_recovering_to_online(self):
        """MAINTENANCE_RECOVERING → ONLINE is valid."""
        sm = SLMStateMachine()
        assert sm.can_transition(NodeState.MAINTENANCE_RECOVERING, NodeState.ONLINE)

    def test_maintenance_recovering_to_error(self):
        """MAINTENANCE_RECOVERING → ERROR is valid (recovery failed)."""
        sm = SLMStateMachine()
        assert sm.can_transition(NodeState.MAINTENANCE_RECOVERING, NodeState.ERROR)
