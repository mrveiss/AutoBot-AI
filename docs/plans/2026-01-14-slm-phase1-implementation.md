# Service Lifecycle Manager - Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the foundation layer for SLM including database schema, state machine, and lightweight node agent.

**Architecture:** Extends existing infrastructure models in `backend/models/infrastructure.py` with new SLM-specific tables. Adds state machine logic as a service. Agent is a standalone Python script deployed via Ansible.

**Tech Stack:** SQLAlchemy (existing), FastAPI (existing), asyncssh, systemd

**Issue:** #726

---

## Task 1: Extend Database Schema with SLM Tables

**Files:**
- Modify: `backend/models/infrastructure.py` (add new models)
- Create: `backend/services/slm/__init__.py`
- Create: `backend/services/slm/models.py` (Pydantic schemas)
- Test: `tests/services/slm/test_slm_models.py`

**Step 1: Write the failing test for NodeState enum and SLMNode model**

```python
# tests/services/slm/test_slm_models.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM database models."""

import pytest
from datetime import datetime
from backend.models.infrastructure import (
    SLMNode,
    SLMRole,
    SLMStateTransition,
    SLMDeployment,
    SLMMaintenanceWindow,
    NodeState,
    MaintenanceType,
    DeploymentStrategy,
)


class TestNodeStateEnum:
    """Test NodeState enumeration."""

    def test_all_states_defined(self):
        """Verify all required states exist."""
        states = [s.value for s in NodeState]
        assert "unknown" in states
        assert "pending" in states
        assert "enrolling" in states
        assert "online" in states
        assert "degraded" in states
        assert "error" in states
        assert "maintenance_draining" in states
        assert "maintenance_planned" in states
        assert "maintenance_immediate" in states
        assert "maintenance_offline" in states
        assert "maintenance_recovering" in states

    def test_state_is_maintenance(self):
        """Test maintenance state detection."""
        assert NodeState.MAINTENANCE_DRAINING.is_maintenance
        assert NodeState.MAINTENANCE_PLANNED.is_maintenance
        assert NodeState.MAINTENANCE_OFFLINE.is_maintenance
        assert not NodeState.ONLINE.is_maintenance
        assert not NodeState.DEGRADED.is_maintenance


class TestSLMNodeModel:
    """Test SLMNode SQLAlchemy model."""

    def test_slm_node_creation(self, db_session):
        """Test creating an SLM node."""
        node = SLMNode(
            id="node-001",
            name="redis-vm",
            ip_address="172.16.168.23",
            state=NodeState.PENDING.value,
            current_role="redis",
            capability_tags=["can_be_redis", "has_ssd"],
        )
        db_session.add(node)
        db_session.commit()

        retrieved = db_session.query(SLMNode).filter_by(id="node-001").first()
        assert retrieved is not None
        assert retrieved.name == "redis-vm"
        assert retrieved.state == "pending"
        assert "can_be_redis" in retrieved.capability_tags

    def test_slm_node_state_transition(self, db_session):
        """Test recording state transition."""
        node = SLMNode(
            id="node-002",
            name="frontend-vm",
            ip_address="172.16.168.21",
            state=NodeState.ONLINE.value,
        )
        db_session.add(node)
        db_session.commit()

        transition = SLMStateTransition(
            node_id="node-002",
            from_state=NodeState.PENDING.value,
            to_state=NodeState.ONLINE.value,
            trigger="enrollment_complete",
            details={"ansible_run_id": "abc-123"},
        )
        db_session.add(transition)
        db_session.commit()

        assert len(db_session.query(SLMStateTransition).all()) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/slm/test_slm_models.py -v`
Expected: FAIL with "cannot import name 'SLMNode' from 'backend.models.infrastructure'"

**Step 3: Create test directory and conftest**

```python
# tests/services/slm/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""SLM test package."""
```

```python
# tests/services/slm/conftest.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pytest fixtures for SLM tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.infrastructure import Base


@pytest.fixture
def db_session():
    """Create in-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
```

**Step 4: Add NodeState enum to infrastructure models**

```python
# Add to backend/models/infrastructure.py after existing imports

from enum import Enum

class NodeState(str, Enum):
    """Node lifecycle states for SLM."""

    UNKNOWN = "unknown"
    PENDING = "pending"
    ENROLLING = "enrolling"
    ONLINE = "online"
    DEGRADED = "degraded"
    ERROR = "error"
    MAINTENANCE_DRAINING = "maintenance_draining"
    MAINTENANCE_PLANNED = "maintenance_planned"
    MAINTENANCE_IMMEDIATE = "maintenance_immediate"
    MAINTENANCE_OFFLINE = "maintenance_offline"
    MAINTENANCE_RECOVERING = "maintenance_recovering"

    @property
    def is_maintenance(self) -> bool:
        """Check if state is a maintenance state."""
        return self.value.startswith("maintenance_")


class MaintenanceType(str, Enum):
    """Types of maintenance operations."""

    DRAINING = "draining"
    PLANNED = "planned"
    IMMEDIATE = "immediate"


class DeploymentStrategy(str, Enum):
    """Deployment strategies for updates."""

    SEQUENTIAL = "sequential"
    BLUE_GREEN = "blue_green"
    REPLICATED_SWAP = "replicated_swap"
    MAINTENANCE_WINDOW = "maintenance_window"


class ServiceType(str, Enum):
    """Service types for role definitions."""

    STATELESS = "stateless"
    STATEFUL = "stateful"
```

**Step 5: Add SLMNode model**

```python
# Add to backend/models/infrastructure.py after enums

class SLMNode(Base):
    """
    Service Lifecycle Manager node registry.

    Tracks nodes managed by SLM with full state machine support,
    capability tags for role borrowing, and maintenance tracking.
    """
    __tablename__ = 'slm_nodes'

    id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(255), unique=True, nullable=False, index=True)
    ip_address = Column(String(45), unique=True, nullable=False, index=True)
    ssh_port = Column(Integer, default=22, nullable=False)
    ssh_user = Column(String(50), default='autobot', nullable=False)

    # State management
    state = Column(String(30), default=NodeState.UNKNOWN.value, nullable=False, index=True)
    state_changed = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Role management
    current_role = Column(String(50), index=True)
    primary_role = Column(String(50))  # Original role for role borrowing
    capability_tags = Column(JSON, default=list)  # ["can_be_redis", "has_gpu"]

    # Maintenance
    maintenance_type = Column(String(20))
    maintenance_reason = Column(Text)
    maintenance_start = Column(DateTime)
    maintenance_end = Column(DateTime)
    drain_timeout_sec = Column(Integer, default=300)

    # Health
    last_heartbeat = Column(DateTime)
    last_health = Column(JSON)  # Health snapshot
    consecutive_failures = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    state_transitions = relationship(
        "SLMStateTransition", back_populates="node", cascade="all, delete-orphan"
    )

    def __repr__(self):
        """Return string representation."""
        return f"<SLMNode(id={self.id}, name='{self.name}', state='{self.state}')>"
```

**Step 6: Add SLMRole model**

```python
# Add to backend/models/infrastructure.py

class SLMRole(Base):
    """
    Role definitions for SLM managed services.

    Defines service configurations, health checks, and deployment strategies.
    """
    __tablename__ = 'slm_roles'

    id = Column(String(36), primary_key=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text)
    service_type = Column(String(20), default=ServiceType.STATELESS.value)
    services = Column(JSON, default=list)  # ["redis-stack-server"]
    required_tags = Column(JSON, default=list)  # ["has_ssd"]
    dependencies = Column(JSON, default=list)  # ["redis"]
    update_strategies = Column(JSON, default=list)  # ["blue_green", "maintenance_window"]
    replication_config = Column(JSON)  # {"method": "redis_replica", ...}
    health_checks = Column(JSON, default=list)  # Health check definitions
    install_playbook = Column(String(255))
    purge_playbook = Column(String(255))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        """Return string representation."""
        return f"<SLMRole(id={self.id}, name='{self.name}')>"
```

**Step 7: Add SLMStateTransition model**

```python
# Add to backend/models/infrastructure.py

class SLMStateTransition(Base):
    """
    Audit log for node state transitions.

    Records all state changes with trigger and context details.
    """
    __tablename__ = 'slm_state_transitions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(36), ForeignKey('slm_nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    from_state = Column(String(30))
    to_state = Column(String(30), nullable=False)
    trigger = Column(String(50))  # 'health_check', 'api', 'remediation', 'timeout'
    details = Column(JSON)  # Context details
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationship
    node = relationship("SLMNode", back_populates="state_transitions")

    def __repr__(self):
        """Return string representation."""
        return f"<SLMStateTransition({self.from_state} → {self.to_state})>"
```

**Step 8: Add SLMDeployment model**

```python
# Add to backend/models/infrastructure.py

class SLMDeployment(Base):
    """
    Deployment tracking for SLM orchestrated updates.

    Tracks rolling updates, role swaps, and enrollments.
    """
    __tablename__ = 'slm_deployments'

    id = Column(String(36), primary_key=True)
    deployment_type = Column(String(30), nullable=False)  # 'update', 'role_change', 'enrollment'
    strategy = Column(String(30), nullable=False)  # DeploymentStrategy value
    strategy_params = Column(JSON)  # {"backup_before": true, "sync_timeout": 600}
    state = Column(String(20), nullable=False, index=True)  # 'pending', 'running', 'completed', 'failed', 'rolled_back'
    target_nodes = Column(JSON)  # Array of node IDs
    current_node = Column(String(36))
    progress = Column(JSON)  # Progress details
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    rollback_at = Column(DateTime)
    error = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        """Return string representation."""
        return f"<SLMDeployment(id={self.id}, type='{self.deployment_type}', state='{self.state}')>"
```

**Step 9: Add SLMMaintenanceWindow model**

```python
# Add to backend/models/infrastructure.py

class SLMMaintenanceWindow(Base):
    """
    Scheduled maintenance windows for nodes.

    Allows scheduling planned maintenance in advance.
    """
    __tablename__ = 'slm_maintenance_windows'

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(36), ForeignKey('slm_nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    maintenance_type = Column(String(20), nullable=False)
    reason = Column(Text)
    scheduled_start = Column(DateTime, nullable=False)
    scheduled_end = Column(DateTime)
    executed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        """Return string representation."""
        return f"<SLMMaintenanceWindow(node={self.node_id}, type='{self.maintenance_type}')>"
```

**Step 10: Run test to verify it passes**

Run: `pytest tests/services/slm/test_slm_models.py -v`
Expected: PASS

**Step 11: Commit**

```bash
git add backend/models/infrastructure.py tests/services/slm/
git commit -m "feat(slm): Add SLM database models and enums (#726)

- Add NodeState, MaintenanceType, DeploymentStrategy enums
- Add SLMNode model for node registry with state machine support
- Add SLMRole model for role definitions
- Add SLMStateTransition for audit trail
- Add SLMDeployment for deployment tracking
- Add SLMMaintenanceWindow for scheduled maintenance

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Implement State Machine Service

**Files:**
- Create: `backend/services/slm/__init__.py`
- Create: `backend/services/slm/state_machine.py`
- Test: `tests/services/slm/test_state_machine.py`

**Step 1: Write failing test for state machine transitions**

```python
# tests/services/slm/test_state_machine.py
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/slm/test_state_machine.py -v`
Expected: FAIL with "No module named 'backend.services.slm.state_machine'"

**Step 3: Create SLM service package**

```python
# backend/services/slm/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Lifecycle Manager (SLM) Package

Provides orchestration for AutoBot's distributed VM fleet including:
- Node state machine management
- Health monitoring and reconciliation
- Deployment orchestration
- Maintenance scheduling
"""

from backend.services.slm.state_machine import (
    SLMStateMachine,
    InvalidStateTransition,
    VALID_TRANSITIONS,
)

__all__ = [
    "SLMStateMachine",
    "InvalidStateTransition",
    "VALID_TRANSITIONS",
]
```

**Step 4: Implement state machine**

```python
# backend/services/slm/state_machine.py
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
# Key: current state, Value: set of valid next states
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
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/services/slm/test_state_machine.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/services/slm/
git commit -m "feat(slm): Implement state machine for node lifecycle (#726)

- Add SLMStateMachine class with transition validation
- Define VALID_TRANSITIONS mapping all allowed state changes
- Add InvalidStateTransition exception
- Support maintenance mode transitions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create SLM Database Service

**Files:**
- Create: `backend/services/slm/db_service.py`
- Test: `tests/services/slm/test_db_service.py`

**Step 1: Write failing test for SLM database service**

```python
# tests/services/slm/test_db_service.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM database service."""

import pytest
from uuid import uuid4
from backend.models.infrastructure import NodeState
from backend.services.slm.db_service import SLMDatabaseService


class TestSLMNodeCRUD:
    """Test SLM node CRUD operations."""

    @pytest.fixture
    def slm_db(self, tmp_path):
        """Create SLM database service with temp database."""
        db_path = tmp_path / "test_slm.db"
        return SLMDatabaseService(db_path=str(db_path))

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
        assert node.state == NodeState.UNKNOWN.value

    def test_get_node_by_name(self, slm_db):
        """Test retrieving node by name."""
        slm_db.create_node(name="redis-vm", ip_address="172.16.168.23")
        node = slm_db.get_node_by_name("redis-vm")
        assert node is not None
        assert node.ip_address == "172.16.168.23"

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
        assert updated.state == NodeState.PENDING.value

    def test_state_transition_logged(self, slm_db):
        """Test that state transitions are logged."""
        node = slm_db.create_node(name="npu-vm", ip_address="172.16.168.22")
        slm_db.update_node_state(node.id, NodeState.PENDING, trigger="api")

        transitions = slm_db.get_state_transitions(node.id)
        assert len(transitions) == 1
        assert transitions[0].from_state == NodeState.UNKNOWN.value
        assert transitions[0].to_state == NodeState.PENDING.value


class TestSLMRoleCRUD:
    """Test SLM role CRUD operations."""

    @pytest.fixture
    def slm_db(self, tmp_path):
        """Create SLM database service with temp database."""
        db_path = tmp_path / "test_slm.db"
        return SLMDatabaseService(db_path=str(db_path))

    def test_create_role(self, slm_db):
        """Test creating a new role."""
        role = slm_db.create_role(
            name="redis",
            description="Redis Stack data layer",
            service_type="stateful",
            services=["redis-stack-server"],
            health_checks=[{"type": "tcp", "port": 6379}],
        )
        assert role.id is not None
        assert role.name == "redis"
        assert role.service_type == "stateful"

    def test_get_role_by_name(self, slm_db):
        """Test retrieving role by name."""
        slm_db.create_role(name="frontend", services=["nginx"])
        role = slm_db.get_role_by_name("frontend")
        assert role is not None
        assert "nginx" in role.services
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/slm/test_db_service.py -v`
Expected: FAIL with "No module named 'backend.services.slm.db_service'"

**Step 3: Implement SLM database service**

```python
# backend/services/slm/db_service.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Database Service

Provides CRUD operations for SLM entities with state transition tracking.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models.infrastructure import (
    Base,
    NodeState,
    ServiceType,
    SLMNode,
    SLMRole,
    SLMStateTransition,
    SLMDeployment,
    SLMMaintenanceWindow,
)
from backend.services.slm.state_machine import SLMStateMachine, InvalidStateTransition

logger = logging.getLogger(__name__)


class SLMDatabaseService:
    """
    Database service layer for SLM operations.

    Provides:
    - Node registry management with state machine
    - Role definitions
    - State transition audit logging
    - Deployment tracking
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SLM database service.

        Args:
            db_path: Path to SQLite database (defaults to slm.db)
        """
        if db_path is None:
            db_path = "slm.db"

        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)

        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.state_machine = SLMStateMachine()

        logger.info("SLM database initialized at %s", db_path)

    # ==================== Node Management ====================

    def create_node(
        self,
        name: str,
        ip_address: str,
        ssh_port: int = 22,
        ssh_user: str = "autobot",
        capability_tags: Optional[List[str]] = None,
        current_role: Optional[str] = None,
    ) -> SLMNode:
        """
        Create a new node in UNKNOWN state.

        Args:
            name: Node name (unique)
            ip_address: Node IP address (unique)
            ssh_port: SSH port (default: 22)
            ssh_user: SSH user (default: autobot)
            capability_tags: List of capability tags
            current_role: Initial role assignment

        Returns:
            Created SLMNode instance
        """
        with self.SessionLocal() as session:
            node = SLMNode(
                id=str(uuid4()),
                name=name,
                ip_address=ip_address,
                ssh_port=ssh_port,
                ssh_user=ssh_user,
                state=NodeState.UNKNOWN.value,
                capability_tags=capability_tags or [],
                current_role=current_role,
            )
            session.add(node)
            session.commit()
            session.refresh(node)

            logger.info("Created node: %s (%s)", name, ip_address)
            return node

    def get_node(self, node_id: str) -> Optional[SLMNode]:
        """Get node by ID."""
        with self.SessionLocal() as session:
            return session.query(SLMNode).filter(SLMNode.id == node_id).first()

    def get_node_by_name(self, name: str) -> Optional[SLMNode]:
        """Get node by name."""
        with self.SessionLocal() as session:
            return session.query(SLMNode).filter(SLMNode.name == name).first()

    def get_node_by_ip(self, ip_address: str) -> Optional[SLMNode]:
        """Get node by IP address."""
        with self.SessionLocal() as session:
            return session.query(SLMNode).filter(SLMNode.ip_address == ip_address).first()

    def get_all_nodes(self, state: Optional[NodeState] = None) -> List[SLMNode]:
        """Get all nodes, optionally filtered by state."""
        with self.SessionLocal() as session:
            query = session.query(SLMNode)
            if state:
                query = query.filter(SLMNode.state == state.value)
            return query.all()

    def update_node_state(
        self,
        node_id: str,
        new_state: NodeState,
        trigger: str = "api",
        details: Optional[Dict] = None,
        validate_transition: bool = True,
    ) -> SLMNode:
        """
        Update node state with transition validation and logging.

        Args:
            node_id: Node ID
            new_state: Target state
            trigger: What triggered the transition
            details: Additional context
            validate_transition: Whether to validate against state machine

        Returns:
            Updated SLMNode

        Raises:
            InvalidStateTransition: If transition is not allowed
            ValueError: If node not found
        """
        with self.SessionLocal() as session:
            node = session.query(SLMNode).filter(SLMNode.id == node_id).first()
            if not node:
                raise ValueError(f"Node not found: {node_id}")

            old_state = NodeState(node.state)

            # Validate transition
            if validate_transition:
                self.state_machine.transition(old_state, new_state)

            # Update node
            node.state = new_state.value
            node.state_changed = datetime.utcnow()

            # Log transition
            transition = SLMStateTransition(
                node_id=node_id,
                from_state=old_state.value,
                to_state=new_state.value,
                trigger=trigger,
                details=details,
            )
            session.add(transition)
            session.commit()
            session.refresh(node)

            logger.info(
                "Node %s state: %s → %s (trigger: %s)",
                node.name, old_state.value, new_state.value, trigger,
            )
            return node

    def update_node_health(
        self,
        node_id: str,
        health_data: Dict,
        heartbeat_time: Optional[datetime] = None,
    ) -> SLMNode:
        """
        Update node health data and heartbeat.

        Args:
            node_id: Node ID
            health_data: Health snapshot data
            heartbeat_time: Heartbeat timestamp (defaults to now)

        Returns:
            Updated SLMNode
        """
        with self.SessionLocal() as session:
            node = session.query(SLMNode).filter(SLMNode.id == node_id).first()
            if not node:
                raise ValueError(f"Node not found: {node_id}")

            node.last_health = health_data
            node.last_heartbeat = heartbeat_time or datetime.utcnow()
            node.consecutive_failures = 0  # Reset on successful health update

            session.commit()
            session.refresh(node)
            return node

    def increment_failure_count(self, node_id: str) -> int:
        """Increment consecutive failure count, return new count."""
        with self.SessionLocal() as session:
            node = session.query(SLMNode).filter(SLMNode.id == node_id).first()
            if node:
                node.consecutive_failures += 1
                session.commit()
                return node.consecutive_failures
        return 0

    def get_state_transitions(
        self, node_id: str, limit: int = 100
    ) -> List[SLMStateTransition]:
        """Get state transitions for a node."""
        with self.SessionLocal() as session:
            return (
                session.query(SLMStateTransition)
                .filter(SLMStateTransition.node_id == node_id)
                .order_by(SLMStateTransition.created_at.desc())
                .limit(limit)
                .all()
            )

    # ==================== Role Management ====================

    def create_role(
        self,
        name: str,
        description: str = "",
        service_type: str = "stateless",
        services: Optional[List[str]] = None,
        required_tags: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        health_checks: Optional[List[Dict]] = None,
        install_playbook: Optional[str] = None,
        purge_playbook: Optional[str] = None,
    ) -> SLMRole:
        """Create a new role definition."""
        with self.SessionLocal() as session:
            role = SLMRole(
                id=str(uuid4()),
                name=name,
                description=description,
                service_type=service_type,
                services=services or [],
                required_tags=required_tags or [],
                dependencies=dependencies or [],
                health_checks=health_checks or [],
                install_playbook=install_playbook,
                purge_playbook=purge_playbook,
            )
            session.add(role)
            session.commit()
            session.refresh(role)

            logger.info("Created role: %s", name)
            return role

    def get_role(self, role_id: str) -> Optional[SLMRole]:
        """Get role by ID."""
        with self.SessionLocal() as session:
            return session.query(SLMRole).filter(SLMRole.id == role_id).first()

    def get_role_by_name(self, name: str) -> Optional[SLMRole]:
        """Get role by name."""
        with self.SessionLocal() as session:
            return session.query(SLMRole).filter(SLMRole.name == name).first()

    def get_all_roles(self) -> List[SLMRole]:
        """Get all role definitions."""
        with self.SessionLocal() as session:
            return session.query(SLMRole).all()

    # ==================== Statistics ====================

    def get_statistics(self) -> Dict:
        """Get SLM statistics."""
        with self.SessionLocal() as session:
            total_nodes = session.query(SLMNode).count()
            nodes_by_state = {}

            for state in NodeState:
                count = session.query(SLMNode).filter(
                    SLMNode.state == state.value
                ).count()
                if count > 0:
                    nodes_by_state[state.value] = count

            return {
                "total_nodes": total_nodes,
                "nodes_by_state": nodes_by_state,
                "total_roles": session.query(SLMRole).count(),
                "total_transitions": session.query(SLMStateTransition).count(),
            }
```

**Step 4: Update __init__.py exports**

```python
# backend/services/slm/__init__.py - add new exports
from backend.services.slm.db_service import SLMDatabaseService

__all__ = [
    "SLMStateMachine",
    "InvalidStateTransition",
    "VALID_TRANSITIONS",
    "SLMDatabaseService",
]
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/services/slm/test_db_service.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/services/slm/
git commit -m "feat(slm): Add SLM database service with CRUD operations (#726)

- Add SLMDatabaseService for node and role management
- Implement state transition with automatic audit logging
- Add health update and failure tracking
- Integrate state machine validation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create Lightweight Node Agent

**Files:**
- Create: `src/slm/agent/__init__.py`
- Create: `src/slm/agent/agent.py`
- Create: `src/slm/agent/health_collector.py`
- Create: `ansible/roles/slm_agent/tasks/main.yml`
- Create: `ansible/roles/slm_agent/templates/autobot-agent.service.j2`
- Test: `tests/slm/test_agent.py`

**Step 1: Write failing test for health collector**

```python
# tests/slm/test_agent.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM node agent."""

import pytest
from unittest.mock import patch, MagicMock
from src.slm.agent.health_collector import HealthCollector


class TestHealthCollector:
    """Test health data collection."""

    def test_collect_basic_health(self):
        """Test collecting basic health metrics."""
        collector = HealthCollector()
        health = collector.collect()

        assert "timestamp" in health
        assert "hostname" in health
        assert "cpu_percent" in health
        assert "memory_percent" in health
        assert "disk_percent" in health

    def test_check_service_status(self):
        """Test checking systemd service status."""
        collector = HealthCollector()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="active")
            status = collector.check_service("redis-stack-server")
            assert status["active"] is True

    def test_check_port_open(self):
        """Test port connectivity check."""
        collector = HealthCollector()

        with patch("socket.socket") as mock_socket:
            mock_instance = MagicMock()
            mock_socket.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_socket.return_value.__exit__ = MagicMock(return_value=False)
            mock_instance.connect_ex.return_value = 0

            is_open = collector.check_port("localhost", 6379)
            assert is_open is True

    def test_collect_includes_services(self):
        """Test health includes service checks."""
        collector = HealthCollector(services=["redis-stack-server"])

        with patch.object(collector, "check_service") as mock_check:
            mock_check.return_value = {"active": True, "status": "running"}
            health = collector.collect()

            assert "services" in health
            assert "redis-stack-server" in health["services"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/slm/test_agent.py -v`
Expected: FAIL with "No module named 'src.slm.agent'"

**Step 3: Create agent package structure**

```python
# src/slm/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""SLM (Service Lifecycle Manager) package."""
```

```python
# src/slm/agent/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Node Agent Package

Lightweight agent deployed to each managed node for:
- Health data collection
- Heartbeat sending
- Command receiving
"""

from src.slm.agent.health_collector import HealthCollector

__all__ = ["HealthCollector"]
```

**Step 4: Implement health collector**

```python
# src/slm/agent/health_collector.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Health Collector for SLM Agent

Collects system and service health metrics for reporting to admin.
"""

import logging
import platform
import socket
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


class HealthCollector:
    """
    Collects health metrics from the local node.

    Gathers:
    - System metrics (CPU, memory, disk)
    - Service status (systemd)
    - Port connectivity
    """

    def __init__(
        self,
        services: Optional[List[str]] = None,
        ports: Optional[List[Dict]] = None,
    ):
        """
        Initialize health collector.

        Args:
            services: List of systemd service names to check
            ports: List of port checks [{"host": "localhost", "port": 6379}]
        """
        self.services = services or []
        self.ports = ports or []
        self.hostname = platform.node()

    def collect(self) -> Dict:
        """
        Collect all health metrics.

        Returns:
            Dictionary with health snapshot
        """
        health = {
            "timestamp": datetime.utcnow().isoformat(),
            "hostname": self.hostname,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "load_avg": list(psutil.getloadavg()),
            "uptime_seconds": int(
                datetime.now().timestamp() - psutil.boot_time()
            ),
        }

        # Collect service statuses
        if self.services:
            health["services"] = {}
            for service in self.services:
                health["services"][service] = self.check_service(service)

        # Collect port checks
        if self.ports:
            health["ports"] = {}
            for port_check in self.ports:
                host = port_check.get("host", "localhost")
                port = port_check["port"]
                key = f"{host}:{port}"
                health["ports"][key] = self.check_port(host, port)

        return health

    def check_service(self, service_name: str) -> Dict:
        """
        Check systemd service status.

        Args:
            service_name: Name of systemd service

        Returns:
            Dictionary with service status
        """
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            is_active = result.returncode == 0
            status = result.stdout.strip()

            return {
                "active": is_active,
                "status": status,
            }
        except subprocess.TimeoutExpired:
            return {"active": False, "status": "timeout"}
        except Exception as e:
            return {"active": False, "status": str(e)}

    def check_port(self, host: str, port: int, timeout: float = 2.0) -> bool:
        """
        Check if a port is open and accepting connections.

        Args:
            host: Target hostname or IP
            port: Target port number
            timeout: Connection timeout in seconds

        Returns:
            True if port is open
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                result = sock.connect_ex((host, port))
                return result == 0
        except Exception:
            return False

    def is_healthy(self, thresholds: Optional[Dict] = None) -> bool:
        """
        Quick health check against thresholds.

        Args:
            thresholds: Optional custom thresholds

        Returns:
            True if all metrics within thresholds
        """
        defaults = {
            "cpu_percent": 90,
            "memory_percent": 90,
            "disk_percent": 90,
        }
        thresholds = {**defaults, **(thresholds or {})}

        health = self.collect()

        if health["cpu_percent"] > thresholds["cpu_percent"]:
            return False
        if health["memory_percent"] > thresholds["memory_percent"]:
            return False
        if health["disk_percent"] > thresholds["disk_percent"]:
            return False

        # Check all services are active
        for service_status in health.get("services", {}).values():
            if not service_status.get("active"):
                return False

        return True
```

**Step 5: Create main agent script**

```python
# src/slm/agent/agent.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Node Agent

Lightweight daemon that runs on each managed node:
- Sends heartbeats to admin machine
- Collects and reports health data
- Buffers events when admin is offline
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp

from src.slm.agent.health_collector import HealthCollector

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_ADMIN_URL = "https://172.16.168.10:8443"
DEFAULT_HEARTBEAT_INTERVAL = 30  # seconds
DEFAULT_BUFFER_DB = "/var/lib/autobot-agent/events.db"


class SLMAgent:
    """
    SLM Node Agent daemon.

    Responsibilities:
    - Send heartbeats every 30s
    - Buffer events when admin is offline
    - Sync buffered events on reconnect
    """

    def __init__(
        self,
        admin_url: str = DEFAULT_ADMIN_URL,
        heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL,
        buffer_db: str = DEFAULT_BUFFER_DB,
        services: Optional[list] = None,
        node_id: Optional[str] = None,
    ):
        """Initialize agent."""
        self.admin_url = admin_url.rstrip("/")
        self.heartbeat_interval = heartbeat_interval
        self.buffer_db = buffer_db
        self.node_id = node_id or os.environ.get("SLM_NODE_ID")
        self.running = False

        self.collector = HealthCollector(services=services or [])
        self._init_buffer_db()

    def _init_buffer_db(self):
        """Initialize SQLite buffer database."""
        Path(self.buffer_db).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.buffer_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                synced INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Event buffer initialized at %s", self.buffer_db)

    def buffer_event(self, event_type: str, data: dict):
        """Buffer an event for later sync."""
        conn = sqlite3.connect(self.buffer_db)
        conn.execute(
            "INSERT INTO event_buffer (timestamp, event_type, data) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat(), event_type, json.dumps(data)),
        )
        conn.commit()
        conn.close()

    async def send_heartbeat(self) -> bool:
        """
        Send heartbeat with health data to admin.

        Returns:
            True if heartbeat was accepted
        """
        health = self.collector.collect()
        payload = {
            "node_id": self.node_id,
            "health": health,
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.admin_url}/api/v1/heartbeats"
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,  # TODO: Add mTLS
                ) as response:
                    if response.status == 200:
                        logger.debug("Heartbeat sent successfully")
                        return True
                    else:
                        logger.warning(
                            "Heartbeat rejected: %s %s",
                            response.status, await response.text()
                        )
                        return False
        except aiohttp.ClientError as e:
            logger.warning("Failed to send heartbeat: %s", e)
            self.buffer_event("heartbeat", payload)
            return False

    async def sync_buffered_events(self):
        """Sync buffered events to admin."""
        conn = sqlite3.connect(self.buffer_db)
        cursor = conn.execute(
            "SELECT id, event_type, data FROM event_buffer WHERE synced = 0 ORDER BY id LIMIT 100"
        )
        events = cursor.fetchall()

        if not events:
            return

        logger.info("Syncing %d buffered events", len(events))

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.admin_url}/api/v1/events/sync"
                payload = [
                    {"id": e[0], "type": e[1], "data": json.loads(e[2])}
                    for e in events
                ]
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                    ssl=False,
                ) as response:
                    if response.status == 200:
                        # Mark as synced
                        ids = [e[0] for e in events]
                        conn.execute(
                            f"UPDATE event_buffer SET synced = 1 WHERE id IN ({','.join('?' * len(ids))})",
                            ids,
                        )
                        conn.commit()
                        logger.info("Synced %d events", len(events))
        except aiohttp.ClientError as e:
            logger.warning("Failed to sync events: %s", e)
        finally:
            conn.close()

    async def run(self):
        """Main agent loop."""
        self.running = True
        logger.info(
            "SLM Agent started (node_id=%s, admin=%s)",
            self.node_id, self.admin_url
        )

        while self.running:
            # Send heartbeat
            success = await self.send_heartbeat()

            # If connected, try to sync buffered events
            if success:
                await self.sync_buffered_events()

            # Wait for next heartbeat
            await asyncio.sleep(self.heartbeat_interval)

        logger.info("SLM Agent stopped")

    def stop(self):
        """Stop the agent."""
        self.running = False


def main():
    """CLI entrypoint for SLM agent."""
    parser = argparse.ArgumentParser(description="SLM Node Agent")
    parser.add_argument(
        "--admin-url",
        default=os.environ.get("SLM_ADMIN_URL", DEFAULT_ADMIN_URL),
        help="Admin machine URL",
    )
    parser.add_argument(
        "--node-id",
        default=os.environ.get("SLM_NODE_ID"),
        help="Node ID",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_HEARTBEAT_INTERVAL,
        help="Heartbeat interval in seconds",
    )
    parser.add_argument(
        "--services",
        nargs="*",
        default=[],
        help="Systemd services to monitor",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.node_id:
        logger.error("Node ID required (--node-id or SLM_NODE_ID)")
        sys.exit(1)

    # Create and run agent
    agent = SLMAgent(
        admin_url=args.admin_url,
        heartbeat_interval=args.interval,
        services=args.services,
        node_id=args.node_id,
    )

    # Handle shutdown signals
    def shutdown_handler(signum, frame):
        logger.info("Received signal %s, shutting down", signum)
        agent.stop()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    # Run
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
```

**Step 6: Run test to verify it passes**

Run: `pytest tests/slm/test_agent.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add src/slm/ tests/slm/
git commit -m "feat(slm): Add lightweight node agent with health collector (#726)

- Add HealthCollector for system/service metrics
- Add SLMAgent daemon with heartbeat sender
- Implement event buffering for offline resilience
- Support systemd service and port checks

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Create Ansible Role for Agent Deployment

**Files:**
- Create: `ansible/roles/slm_agent/tasks/main.yml`
- Create: `ansible/roles/slm_agent/templates/autobot-agent.service.j2`
- Create: `ansible/roles/slm_agent/templates/agent-config.yaml.j2`
- Create: `ansible/roles/slm_agent/defaults/main.yml`

**Step 1: Create role directory structure**

```bash
mkdir -p ansible/roles/slm_agent/{tasks,templates,defaults,handlers}
```

**Step 2: Create defaults**

```yaml
# ansible/roles/slm_agent/defaults/main.yml
---
# SLM Agent configuration defaults
slm_admin_url: "https://172.16.168.10:8443"
slm_heartbeat_interval: 30
slm_agent_user: autobot
slm_agent_group: autobot
slm_agent_dir: /opt/autobot-agent
slm_agent_data_dir: /var/lib/autobot-agent
slm_services_to_monitor: []
```

**Step 3: Create main tasks**

```yaml
# ansible/roles/slm_agent/tasks/main.yml
---
# SLM Agent deployment tasks
- name: Create agent directories
  file:
    path: "{{ item }}"
    state: directory
    owner: "{{ slm_agent_user }}"
    group: "{{ slm_agent_group }}"
    mode: '0755'
  loop:
    - "{{ slm_agent_dir }}"
    - "{{ slm_agent_data_dir }}"

- name: Install Python dependencies
  pip:
    name:
      - aiohttp
      - psutil
    state: present

- name: Copy agent source files
  copy:
    src: "{{ item.src }}"
    dest: "{{ slm_agent_dir }}/{{ item.dest }}"
    owner: "{{ slm_agent_user }}"
    group: "{{ slm_agent_group }}"
    mode: '0644'
  loop:
    - { src: "slm/agent/__init__.py", dest: "slm/agent/__init__.py" }
    - { src: "slm/agent/agent.py", dest: "slm/agent/agent.py" }
    - { src: "slm/agent/health_collector.py", dest: "slm/agent/health_collector.py" }
  notify: Restart SLM agent

- name: Deploy agent configuration
  template:
    src: agent-config.yaml.j2
    dest: "{{ slm_agent_dir }}/config.yaml"
    owner: "{{ slm_agent_user }}"
    group: "{{ slm_agent_group }}"
    mode: '0640'
  notify: Restart SLM agent

- name: Deploy systemd service
  template:
    src: autobot-agent.service.j2
    dest: /etc/systemd/system/autobot-agent.service
    mode: '0644'
  notify:
    - Reload systemd
    - Restart SLM agent

- name: Enable and start SLM agent
  systemd:
    name: autobot-agent
    enabled: yes
    state: started
    daemon_reload: yes
```

**Step 4: Create systemd service template**

```jinja2
# ansible/roles/slm_agent/templates/autobot-agent.service.j2
[Unit]
Description=AutoBot SLM Node Agent
After=network.target

[Service]
Type=simple
User={{ slm_agent_user }}
Group={{ slm_agent_group }}
WorkingDirectory={{ slm_agent_dir }}

Environment=SLM_NODE_ID={{ slm_node_id }}
Environment=SLM_ADMIN_URL={{ slm_admin_url }}
Environment=PYTHONPATH={{ slm_agent_dir }}

ExecStart=/usr/bin/python3 -m slm.agent.agent \
    --admin-url {{ slm_admin_url }} \
    --node-id {{ slm_node_id }} \
    --interval {{ slm_heartbeat_interval }} \
{% if slm_services_to_monitor %}
    --services {{ slm_services_to_monitor | join(' ') }}
{% endif %}

Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={{ slm_agent_data_dir }}

[Install]
WantedBy=multi-user.target
```

**Step 5: Create config template**

```yaml
# ansible/roles/slm_agent/templates/agent-config.yaml.j2
---
# SLM Agent Configuration
# Generated by Ansible - do not edit manually

node_id: "{{ slm_node_id }}"
admin_url: "{{ slm_admin_url }}"
heartbeat_interval: {{ slm_heartbeat_interval }}

services:
{% for service in slm_services_to_monitor %}
  - {{ service }}
{% endfor %}

data_dir: "{{ slm_agent_data_dir }}"
```

**Step 6: Create handlers**

```yaml
# ansible/roles/slm_agent/handlers/main.yml
---
- name: Reload systemd
  systemd:
    daemon_reload: yes

- name: Restart SLM agent
  systemd:
    name: autobot-agent
    state: restarted
```

**Step 7: Commit**

```bash
git add ansible/roles/slm_agent/
git commit -m "feat(slm): Add Ansible role for agent deployment (#726)

- Add slm_agent role with systemd service
- Include agent configuration template
- Support service monitoring configuration
- Add security hardening to systemd unit

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Create Basic API Endpoints

**Files:**
- Create: `autobot-user-backend/api/slm/__init__.py`
- Create: `autobot-user-backend/api/slm/nodes.py`
- Create: `autobot-user-backend/api/slm/heartbeats.py`
- Test: `tests/api/slm/test_nodes_api.py`

**Step 1: Write failing test for nodes API**

```python
# tests/api/slm/test_nodes_api.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM nodes API."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app


class TestNodesAPI:
    """Test SLM nodes REST API."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_list_nodes_empty(self, client):
        """Test listing nodes when empty."""
        response = client.get("/api/v1/slm/nodes")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert isinstance(data["nodes"], list)

    def test_create_node(self, client):
        """Test creating a new node."""
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

    def test_get_node(self, client):
        """Test getting node by ID."""
        # Create node first
        create_resp = client.post(
            "/api/v1/slm/nodes",
            json={"name": "get-test", "ip_address": "192.168.1.101"},
        )
        node_id = create_resp.json()["id"]

        # Get node
        response = client.get(f"/api/v1/slm/nodes/{node_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "get-test"

    def test_update_node_state(self, client):
        """Test updating node state."""
        # Create node
        create_resp = client.post(
            "/api/v1/slm/nodes",
            json={"name": "state-test", "ip_address": "192.168.1.102"},
        )
        node_id = create_resp.json()["id"]

        # Update state
        response = client.post(
            f"/api/v1/slm/nodes/{node_id}/state",
            json={"state": "pending", "trigger": "api"},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "pending"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/slm/test_nodes_api.py -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Create API package**

```python
# autobot-user-backend/api/slm/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM API Package

REST API endpoints for Service Lifecycle Manager.
"""

from backend.api.slm.nodes import router as nodes_router
from backend.api.slm.heartbeats import router as heartbeats_router

__all__ = ["nodes_router", "heartbeats_router"]
```

**Step 4: Implement nodes API**

```python
# autobot-user-backend/api/slm/nodes.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Nodes API

REST endpoints for node management.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.models.infrastructure import NodeState
from backend.services.slm.db_service import SLMDatabaseService
from backend.services.slm.state_machine import InvalidStateTransition

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm/nodes", tags=["SLM Nodes"])

# Singleton database service
_db_service: Optional[SLMDatabaseService] = None


def get_db_service() -> SLMDatabaseService:
    """Get or create database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = SLMDatabaseService()
    return _db_service


# ==================== Pydantic Models ====================

class NodeCreate(BaseModel):
    """Request model for creating a node."""

    name: str = Field(..., min_length=1, max_length=255)
    ip_address: str = Field(..., pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_user: str = Field(default="autobot", max_length=50)
    capability_tags: List[str] = Field(default_factory=list)
    current_role: Optional[str] = None


class NodeResponse(BaseModel):
    """Response model for node data."""

    id: str
    name: str
    ip_address: str
    ssh_port: int
    ssh_user: str
    state: str
    current_role: Optional[str]
    capability_tags: List[str]
    consecutive_failures: int
    last_heartbeat: Optional[str]

    class Config:
        """Pydantic config."""

        from_attributes = True


class NodeListResponse(BaseModel):
    """Response model for node list."""

    nodes: List[NodeResponse]
    total: int


class StateUpdateRequest(BaseModel):
    """Request model for state update."""

    state: str
    trigger: str = "api"
    details: Optional[dict] = None


# ==================== Endpoints ====================

@router.get("", response_model=NodeListResponse)
async def list_nodes(state: Optional[str] = None):
    """List all nodes, optionally filtered by state."""
    db = get_db_service()
    state_filter = NodeState(state) if state else None
    nodes = db.get_all_nodes(state=state_filter)

    return NodeListResponse(
        nodes=[
            NodeResponse(
                id=n.id,
                name=n.name,
                ip_address=n.ip_address,
                ssh_port=n.ssh_port,
                ssh_user=n.ssh_user,
                state=n.state,
                current_role=n.current_role,
                capability_tags=n.capability_tags or [],
                consecutive_failures=n.consecutive_failures,
                last_heartbeat=n.last_heartbeat.isoformat() if n.last_heartbeat else None,
            )
            for n in nodes
        ],
        total=len(nodes),
    )


@router.post("", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(node: NodeCreate):
    """Create a new node."""
    db = get_db_service()

    # Check for duplicates
    if db.get_node_by_name(node.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Node with name '{node.name}' already exists",
        )
    if db.get_node_by_ip(node.ip_address):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Node with IP '{node.ip_address}' already exists",
        )

    created = db.create_node(
        name=node.name,
        ip_address=node.ip_address,
        ssh_port=node.ssh_port,
        ssh_user=node.ssh_user,
        capability_tags=node.capability_tags,
        current_role=node.current_role,
    )

    return NodeResponse(
        id=created.id,
        name=created.name,
        ip_address=created.ip_address,
        ssh_port=created.ssh_port,
        ssh_user=created.ssh_user,
        state=created.state,
        current_role=created.current_role,
        capability_tags=created.capability_tags or [],
        consecutive_failures=created.consecutive_failures,
        last_heartbeat=None,
    )


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(node_id: str):
    """Get node by ID."""
    db = get_db_service()
    node = db.get_node(node_id)

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found",
        )

    return NodeResponse(
        id=node.id,
        name=node.name,
        ip_address=node.ip_address,
        ssh_port=node.ssh_port,
        ssh_user=node.ssh_user,
        state=node.state,
        current_role=node.current_role,
        capability_tags=node.capability_tags or [],
        consecutive_failures=node.consecutive_failures,
        last_heartbeat=node.last_heartbeat.isoformat() if node.last_heartbeat else None,
    )


@router.post("/{node_id}/state", response_model=NodeResponse)
async def update_node_state(node_id: str, request: StateUpdateRequest):
    """Update node state with transition validation."""
    db = get_db_service()

    try:
        new_state = NodeState(request.state)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state: {request.state}",
        )

    try:
        node = db.update_node_state(
            node_id=node_id,
            new_state=new_state,
            trigger=request.trigger,
            details=request.details,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return NodeResponse(
        id=node.id,
        name=node.name,
        ip_address=node.ip_address,
        ssh_port=node.ssh_port,
        ssh_user=node.ssh_user,
        state=node.state,
        current_role=node.current_role,
        capability_tags=node.capability_tags or [],
        consecutive_failures=node.consecutive_failures,
        last_heartbeat=node.last_heartbeat.isoformat() if node.last_heartbeat else None,
    )


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(node_id: str):
    """Delete a node (must be in UNKNOWN or ERROR state)."""
    db = get_db_service()
    node = db.get_node(node_id)

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found",
        )

    # Only allow deletion of nodes in safe states
    safe_states = {NodeState.UNKNOWN.value, NodeState.ERROR.value}
    if node.state not in safe_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete node in state '{node.state}'. "
                   f"Node must be in UNKNOWN or ERROR state.",
        )

    # TODO: Implement actual deletion
    logger.info("Would delete node %s", node_id)
```

**Step 5: Implement heartbeats API**

```python
# autobot-user-backend/api/slm/heartbeats.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Heartbeats API

REST endpoints for agent heartbeat handling.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.services.slm.db_service import SLMDatabaseService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm", tags=["SLM Heartbeats"])

# Singleton database service
_db_service: Optional[SLMDatabaseService] = None


def get_db_service() -> SLMDatabaseService:
    """Get or create database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = SLMDatabaseService()
    return _db_service


class HeartbeatRequest(BaseModel):
    """Request model for heartbeat."""

    node_id: str
    health: Dict
    timestamp: str


class HeartbeatResponse(BaseModel):
    """Response model for heartbeat."""

    accepted: bool
    node_state: str


class EventSyncRequest(BaseModel):
    """Request model for event sync."""

    id: int
    type: str
    data: Dict


@router.post("/heartbeats", response_model=HeartbeatResponse)
async def receive_heartbeat(heartbeat: HeartbeatRequest):
    """
    Receive heartbeat from node agent.

    Updates node health data and resets failure count.
    """
    db = get_db_service()
    node = db.get_node(heartbeat.node_id)

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{heartbeat.node_id}' not found",
        )

    # Parse timestamp
    try:
        heartbeat_time = datetime.fromisoformat(heartbeat.timestamp)
    except ValueError:
        heartbeat_time = datetime.utcnow()

    # Update health
    db.update_node_health(
        node_id=heartbeat.node_id,
        health_data=heartbeat.health,
        heartbeat_time=heartbeat_time,
    )

    logger.debug(
        "Heartbeat received from %s (cpu=%.1f%%, mem=%.1f%%)",
        node.name,
        heartbeat.health.get("cpu_percent", 0),
        heartbeat.health.get("memory_percent", 0),
    )

    return HeartbeatResponse(
        accepted=True,
        node_state=node.state,
    )


@router.post("/events/sync", status_code=status.HTTP_200_OK)
async def sync_events(events: List[EventSyncRequest]):
    """
    Sync buffered events from node agent.

    Processes events that were buffered when admin was offline.
    """
    logger.info("Received %d buffered events for sync", len(events))

    # Process events (for now just log them)
    for event in events:
        logger.debug(
            "Processing buffered event: type=%s, id=%d",
            event.type, event.id,
        )

    return {"synced": len(events)}
```

**Step 6: Register routers in main app**

Add to `backend/main.py`:

```python
# Add to imports
from backend.api.slm import nodes_router, heartbeats_router

# Add in router registration section
app.include_router(nodes_router, prefix="/api/v1")
app.include_router(heartbeats_router, prefix="/api/v1")
```

**Step 7: Run test to verify it passes**

Run: `pytest tests/api/slm/test_nodes_api.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add autobot-user-backend/api/slm/ tests/api/slm/ backend/main.py
git commit -m "feat(slm): Add REST API for nodes and heartbeats (#726)

- Add /api/v1/slm/nodes CRUD endpoints
- Add /api/v1/slm/heartbeats endpoint for agent
- Add /api/v1/slm/events/sync for buffered events
- Include state transition validation in API

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Initialize Default Roles

**Files:**
- Modify: `backend/services/slm/db_service.py`
- Test: `tests/services/slm/test_default_roles.py`

**Step 1: Write failing test for default roles**

```python
# tests/services/slm/test_default_roles.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM default role initialization."""

import pytest
from backend.services.slm.db_service import SLMDatabaseService


class TestDefaultRoles:
    """Test default role initialization."""

    @pytest.fixture
    def slm_db(self, tmp_path):
        """Create SLM database service with temp database."""
        db_path = tmp_path / "test_slm.db"
        return SLMDatabaseService(db_path=str(db_path))

    def test_default_roles_created(self, slm_db):
        """Test that default roles are created on init."""
        roles = slm_db.get_all_roles()
        role_names = [r.name for r in roles]

        assert "frontend" in role_names
        assert "redis" in role_names
        assert "npu-worker" in role_names
        assert "ai-stack" in role_names
        assert "browser" in role_names

    def test_redis_role_is_stateful(self, slm_db):
        """Test Redis role is marked stateful."""
        role = slm_db.get_role_by_name("redis")
        assert role.service_type == "stateful"

    def test_frontend_role_is_stateless(self, slm_db):
        """Test Frontend role is marked stateless."""
        role = slm_db.get_role_by_name("frontend")
        assert role.service_type == "stateless"

    def test_roles_have_health_checks(self, slm_db):
        """Test roles have health check definitions."""
        redis_role = slm_db.get_role_by_name("redis")
        assert len(redis_role.health_checks) > 0
        assert redis_role.health_checks[0]["type"] == "tcp"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/slm/test_default_roles.py -v`
Expected: FAIL (no default roles created)

**Step 3: Add role initialization to db_service**

Add to `backend/services/slm/db_service.py` `__init__` method:

```python
def __init__(self, db_path: Optional[str] = None):
    # ... existing code ...

    # Initialize default roles
    self._init_default_roles()

def _init_default_roles(self):
    """Initialize default roles if database is empty."""
    with self.SessionLocal() as session:
        count = session.query(SLMRole).count()
        if count > 0:
            return

        default_roles = [
            {
                "name": "frontend",
                "description": "Vue.js frontend server",
                "service_type": "stateless",
                "services": ["nginx", "autobot-frontend"],
                "health_checks": [{"type": "tcp", "port": 5173}],
                "install_playbook": "ansible/playbooks/deploy_frontend.yml",
            },
            {
                "name": "redis",
                "description": "Redis Stack data layer",
                "service_type": "stateful",
                "services": ["redis-stack-server"],
                "health_checks": [{"type": "tcp", "port": 6379}],
                "install_playbook": "ansible/playbooks/deploy_redis.yml",
                "required_tags": ["has_ssd"],
            },
            {
                "name": "npu-worker",
                "description": "NPU hardware acceleration worker",
                "service_type": "stateless",
                "services": ["autobot-npu-worker"],
                "health_checks": [{"type": "tcp", "port": 8081}],
                "install_playbook": "ansible/playbooks/deploy_npu.yml",
                "required_tags": ["has_npu"],
            },
            {
                "name": "ai-stack",
                "description": "AI processing stack with Ollama",
                "service_type": "stateful",
                "services": ["ollama", "autobot-ai-stack"],
                "health_checks": [{"type": "tcp", "port": 8080}],
                "install_playbook": "ansible/playbooks/deploy_ai_stack.yml",
                "required_tags": ["has_gpu"],
            },
            {
                "name": "browser",
                "description": "Playwright browser automation",
                "service_type": "stateless",
                "services": ["autobot-browser"],
                "health_checks": [{"type": "tcp", "port": 3000}],
                "install_playbook": "ansible/playbooks/deploy_browser.yml",
            },
        ]

        for role_data in default_roles:
            role = SLMRole(
                id=str(uuid4()),
                name=role_data["name"],
                description=role_data.get("description", ""),
                service_type=role_data.get("service_type", "stateless"),
                services=role_data.get("services", []),
                required_tags=role_data.get("required_tags", []),
                health_checks=role_data.get("health_checks", []),
                install_playbook=role_data.get("install_playbook"),
            )
            session.add(role)

        session.commit()
        logger.info("Initialized %d default SLM roles", len(default_roles))
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/services/slm/test_default_roles.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/slm/db_service.py tests/services/slm/test_default_roles.py
git commit -m "feat(slm): Initialize default roles on database creation (#726)

- Add frontend, redis, npu-worker, ai-stack, browser roles
- Mark redis and ai-stack as stateful
- Include health check definitions for each role
- Add required_tags for role compatibility

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Final Phase 1 Commit

**Step 1: Run all SLM tests**

Run: `pytest tests/services/slm/ tests/slm/ tests/api/slm/ -v`
Expected: All PASS

**Step 2: Final commit for Phase 1**

```bash
git add -A
git commit -m "feat(slm): Complete Phase 1 Foundation (#726)

Phase 1 delivers:
- SLM database schema with node, role, transition models
- State machine with full lifecycle support
- Database service with CRUD and audit logging
- Lightweight node agent with health collector
- Ansible role for agent deployment
- REST API for nodes and heartbeats
- Default role initialization

Ready for Phase 2: Health & Reconciliation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

Phase 1 Foundation includes:

| Component | Files | Purpose |
|-----------|-------|---------|
| Database Models | `backend/models/infrastructure.py` | SLMNode, SLMRole, SLMStateTransition |
| State Machine | `backend/services/slm/state_machine.py` | Transition validation |
| DB Service | `backend/services/slm/db_service.py` | CRUD with audit logging |
| Node Agent | `src/slm/agent/` | Health collection, heartbeats |
| Ansible Role | `ansible/roles/slm_agent/` | Agent deployment |
| REST API | `autobot-user-backend/api/slm/` | Nodes and heartbeats endpoints |

**Next Phase (Phase 2):** Health & Reconciliation
- Heartbeat collection service
- Reconciliation loop (30s cycle)
- Conservative remediation (service restart)
- WebSocket real-time updates
