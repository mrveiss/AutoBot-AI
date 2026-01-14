# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM State Machine

Defines valid state transitions for managed nodes.
Based on design in docs/plans/2026-01-14-service-lifecycle-manager-design.md
"""

import logging
from typing import Dict, FrozenSet, Optional

from backend.models.infrastructure import NodeState

logger = logging.getLogger(__name__)


class InvalidStateTransition(Exception):
    """Raised when attempting an invalid state transition."""

    def __init__(self, from_state: NodeState, to_state: NodeState, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        message = f"Invalid transition: {from_state.value} → {to_state.value}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


# Valid state transitions as adjacency list
VALID_TRANSITIONS: Dict[NodeState, FrozenSet[NodeState]] = {
    NodeState.UNKNOWN: frozenset({NodeState.PENDING}),
    NodeState.PENDING: frozenset({NodeState.ENROLLING, NodeState.UNKNOWN}),
    NodeState.ENROLLING: frozenset({NodeState.ONLINE, NodeState.ERROR}),
    NodeState.ONLINE: frozenset({
        NodeState.DEGRADED,
        NodeState.MAINTENANCE_DRAINING,
        NodeState.MAINTENANCE_PLANNED,
        NodeState.MAINTENANCE_IMMEDIATE,
    }),
    NodeState.DEGRADED: frozenset({
        NodeState.ONLINE,
        NodeState.ERROR,
        NodeState.MAINTENANCE_DRAINING,
        NodeState.MAINTENANCE_IMMEDIATE,
    }),
    NodeState.ERROR: frozenset({
        NodeState.PENDING,  # Re-enroll after human approval
        NodeState.ONLINE,   # Manual recovery
    }),
    NodeState.MAINTENANCE_DRAINING: frozenset({NodeState.MAINTENANCE_OFFLINE}),
    NodeState.MAINTENANCE_PLANNED: frozenset({NodeState.MAINTENANCE_OFFLINE}),
    NodeState.MAINTENANCE_IMMEDIATE: frozenset({NodeState.MAINTENANCE_OFFLINE}),
    NodeState.MAINTENANCE_OFFLINE: frozenset({NodeState.MAINTENANCE_RECOVERING}),
    NodeState.MAINTENANCE_RECOVERING: frozenset({NodeState.ONLINE, NodeState.ERROR}),
}


class SLMStateMachine:
    """
    State machine for SLM node lifecycle management.

    Enforces valid state transitions and provides transition validation.
    """

    def __init__(self):
        """Initialize state machine with transition rules."""
        self.transitions = VALID_TRANSITIONS

    def can_transition(self, from_state: NodeState, to_state: NodeState) -> bool:
        """
        Check if transition is valid.

        Args:
            from_state: Current node state
            to_state: Desired target state

        Returns:
            True if transition is allowed
        """
        if from_state not in self.transitions:
            return False
        return to_state in self.transitions[from_state]

    def transition(
        self,
        from_state: NodeState,
        to_state: NodeState,
        reason: Optional[str] = None,
    ) -> NodeState:
        """
        Execute state transition with validation.

        Args:
            from_state: Current node state
            to_state: Desired target state
            reason: Optional reason for the transition

        Returns:
            The new state (to_state) if valid

        Raises:
            InvalidStateTransition: If transition is not allowed
        """
        if not self.can_transition(from_state, to_state):
            raise InvalidStateTransition(from_state, to_state, reason or "transition not allowed")

        logger.info(
            "State transition: %s → %s%s",
            from_state.value,
            to_state.value,
            f" (reason: {reason})" if reason else "",
        )
        return to_state

    def get_valid_transitions(self, from_state: NodeState) -> FrozenSet[NodeState]:
        """
        Get all valid target states from current state.

        Args:
            from_state: Current node state

        Returns:
            Set of valid target states
        """
        return self.transitions.get(from_state, frozenset())

    def is_maintenance_state(self, state: NodeState) -> bool:
        """Check if state is a maintenance state."""
        return state.is_maintenance

    def is_terminal_state(self, state: NodeState) -> bool:
        """
        Check if state requires human intervention to exit.

        ERROR is considered terminal - needs human approval for re-enrollment.
        """
        return state == NodeState.ERROR
