# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SQLAlchemy ORM Models for Infrastructure Management

This module provides the complete database schema for AutoBot's Infrastructure as Code (IaC)
platform, including host inventory, role definitions, credentials, deployments, and audit logging.
"""

from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ============================================================================
# Service Lifecycle Manager (SLM) Enums
# ============================================================================


class NodeState(str, Enum):
    """
    Node lifecycle states for the Service Lifecycle Manager.

    Defines all possible states a node can be in during its lifecycle,
    including operational states and maintenance modes.
    """
    # Operational states
    UNKNOWN = "unknown"
    PENDING = "pending"
    ENROLLING = "enrolling"
    ONLINE = "online"
    DEGRADED = "degraded"
    ERROR = "error"

    # Maintenance states
    MAINTENANCE_DRAINING = "maintenance_draining"
    MAINTENANCE_PLANNED = "maintenance_planned"
    MAINTENANCE_IMMEDIATE = "maintenance_immediate"
    MAINTENANCE_OFFLINE = "maintenance_offline"
    MAINTENANCE_RECOVERING = "maintenance_recovering"

    @property
    def is_maintenance(self) -> bool:
        """Check if this state is a maintenance state."""
        return self.value.startswith("maintenance_")


class MaintenanceType(str, Enum):
    """Types of maintenance operations."""
    DRAINING = "draining"
    PLANNED = "planned"
    IMMEDIATE = "immediate"


class DeploymentStrategy(str, Enum):
    """Deployment strategies for role updates."""
    SEQUENTIAL = "sequential"
    BLUE_GREEN = "blue_green"
    REPLICATED_SWAP = "replicated_swap"
    MAINTENANCE_WINDOW = "maintenance_window"


class ServiceType(str, Enum):
    """Service types for role classification."""
    STATELESS = "stateless"
    STATEFUL = "stateful"


class InfraRole(Base):
    """
    Infrastructure role definitions for host provisioning.

    Defines the available roles that can be deployed to infrastructure hosts
    (e.g., frontend, redis, npu-worker, ai-stack, browser).
    """
    __tablename__ = 'infra_roles'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text)
    ansible_playbook_path = Column(String(255), nullable=False)
    required_ports = Column(JSON)  # JSON array of required ports
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    hosts = relationship("InfraHost", back_populates="role", cascade="all, delete-orphan")

    def __repr__(self):
        """Return string representation of InfraRole."""
        return f"<InfraRole(id={self.id}, name='{self.name}')>"


class InfraHost(Base):
    """
    Infrastructure host inventory for distributed VM architecture.

    Tracks all managed hosts including their connection details, role assignments,
    and current deployment status.
    """
    __tablename__ = 'infra_hosts'

    id = Column(Integer, primary_key=True)
    hostname = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(45), unique=True, nullable=False, index=True)  # IPv4/IPv6 support
    role_id = Column(Integer, ForeignKey('infra_roles.id', ondelete='RESTRICT'), nullable=False)
    status = Column(String(20), default='new', nullable=False, index=True)
    # Status values: new, provisioning, deployed, healthy, degraded, failed

    # SSH connection details
    ssh_port = Column(Integer, default=22, nullable=False)
    ssh_user = Column(String(50), default='autobot', nullable=False)
    ssh_key_path = Column(String(500))  # Path to SSH private key file

    # Ansible facts and metadata
    ansible_facts = Column(JSON)  # Gathered system facts

    # Timestamps
    last_seen_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    role = relationship("InfraRole", back_populates="hosts")
    credentials = relationship(
        "InfraCredential", back_populates="host", cascade="all, delete-orphan"
    )
    deployments = relationship(
        "InfraDeployment", back_populates="host", cascade="all, delete-orphan"
    )

    def __repr__(self):
        """Return string representation of InfraHost."""
        return (
            f"<InfraHost(id={self.id}, hostname='{self.hostname}', "
            f"ip='{self.ip_address}', status='{self.status}')>"
        )


class InfraCredential(Base):
    """
    Encrypted SSH credentials for infrastructure hosts.

    Stores encrypted SSH credentials (passwords or private keys) using Fernet encryption.
    Supports credential rotation and expiration.
    """
    __tablename__ = 'infra_credentials'

    id = Column(Integer, primary_key=True)
    host_id = Column(
        Integer, ForeignKey('infra_hosts.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    credential_type = Column(String(20), nullable=False)  # 'password' or 'ssh_key'
    encrypted_value = Column(Text, nullable=False)  # Fernet encrypted credential
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    expires_at = Column(DateTime)  # Optional expiration for credential rotation
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    host = relationship("InfraHost", back_populates="credentials")

    def __repr__(self):
        """Return string representation of InfraCredential."""
        return (
            f"<InfraCredential(id={self.id}, host_id={self.host_id}, "
            f"type='{self.credential_type}', active={self.is_active})>"
        )


class InfraDeployment(Base):
    """
    Deployment tracking and history for infrastructure operations.

    Records all deployment attempts including Ansible playbook executions,
    success/failure status, and detailed logs.
    """
    __tablename__ = 'infra_deployments'

    id = Column(Integer, primary_key=True)
    host_id = Column(
        Integer, ForeignKey('infra_hosts.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    role = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default='queued', nullable=False, index=True)
    # Status values: queued, running, success, failed, rolled_back

    ansible_run_id = Column(String(36), index=True)  # UUID for Ansible execution
    log_path = Column(String(500))  # Path to deployment log file
    error_message = Column(Text)  # Error details if deployment failed

    # Timestamps
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    host = relationship("InfraHost", back_populates="deployments")

    def __repr__(self):
        """Return string representation of InfraDeployment."""
        return (
            f"<InfraDeployment(id={self.id}, host_id={self.host_id}, "
            f"role='{self.role}', status='{self.status}')>"
        )


class InfraAuditLog(Base):
    """
    Comprehensive audit trail for all infrastructure operations.

    Records all infrastructure changes for security, compliance, and debugging purposes.
    """
    __tablename__ = 'infra_audit_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), index=True)  # User or service account that performed action
    # Action performed (e.g., 'create_host', 'deploy_role')
    action = Column(String(100), nullable=False, index=True)
    # Resource type (e.g., 'host', 'credential')
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(Integer, index=True)  # ID of affected resource
    details = Column(JSON)  # Additional action details and context
    ip_address = Column(String(45))  # Source IP address of request
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        """Return string representation of InfraAuditLog."""
        return (
            f"<InfraAuditLog(id={self.id}, action='{self.action}', "
            f"resource_type='{self.resource_type}', timestamp={self.timestamp})>"
        )


# ============================================================================
# Service Lifecycle Manager (SLM) Models
# ============================================================================


class SLMNode(Base):
    """
    Service Lifecycle Manager node registry.

    Tracks all nodes in the distributed infrastructure with their current state,
    roles, capabilities, and maintenance status. Provides the foundation for
    the SLM state machine and deployment orchestration.
    """
    __tablename__ = 'slm_nodes'

    # Primary identification
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))  # UUID
    name = Column(String(100), unique=True, nullable=False, index=True)
    ip_address = Column(String(45), unique=True, nullable=False, index=True)

    # SSH connection details
    ssh_port = Column(Integer, default=22, nullable=False)
    ssh_user = Column(String(50), default='autobot', nullable=False)

    # State machine
    state = Column(SQLEnum(NodeState), default=NodeState.UNKNOWN, nullable=False, index=True)
    state_changed = Column(DateTime, default=datetime.utcnow)

    # Role assignment
    current_role = Column(String(100), index=True)
    primary_role = Column(String(100))

    # Node capabilities and metadata
    capability_tags = Column(JSON, default=list)  # ["cpu", "gpu", "storage", etc.]

    # Maintenance tracking
    maintenance_type = Column(SQLEnum(MaintenanceType), nullable=True)
    maintenance_reason = Column(Text, nullable=True)
    maintenance_started = Column(DateTime, nullable=True)
    maintenance_window_id = Column(Integer, nullable=True)

    # Health monitoring
    last_heartbeat = Column(DateTime)
    last_health_check = Column(DateTime)
    consecutive_failures = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    state_transitions = relationship(
        "SLMStateTransition",
        back_populates="node",
        cascade="all, delete-orphan",
        order_by="SLMStateTransition.timestamp.desc()"
    )

    def __repr__(self):
        """Return string representation of SLMNode."""
        return (
            f"<SLMNode(id='{self.id}', name='{self.name}', "
            f"ip='{self.ip_address}', state='{self.state}')>"
        )


class SLMRole(Base):
    """
    Service Lifecycle Manager role definitions.

    Defines roles that can be deployed to nodes, including service dependencies,
    update strategies, health checks, and deployment automation.
    """
    __tablename__ = 'slm_roles'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text)

    # Service classification
    service_type = Column(SQLEnum(ServiceType), nullable=False)

    # Service definitions
    services = Column(JSON, default=list)  # List of systemd service names
    required_tags = Column(JSON, default=list)  # Required capability tags
    dependencies = Column(JSON, default=list)  # Role dependencies

    # Deployment configuration
    update_strategies = Column(JSON, default=dict)  # Strategy options per scenario
    replication_config = Column(JSON, default=dict)  # Replication requirements

    # Health check configuration
    health_checks = Column(JSON, default=dict)  # Health check definitions

    # Ansible automation
    install_playbook = Column(String(255))
    purge_playbook = Column(String(255))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        """Return string representation of SLMRole."""
        return f"<SLMRole(id={self.id}, name='{self.name}', type='{self.service_type}')>"


class SLMStateTransition(Base):
    """
    State transition audit trail for SLM nodes.

    Records all state changes for debugging, compliance, and analysis.
    """
    __tablename__ = 'slm_state_transitions'

    id = Column(Integer, primary_key=True)
    node_id = Column(String(36), ForeignKey('slm_nodes.id', ondelete='CASCADE'), nullable=False, index=True)

    # State transition
    from_state = Column(SQLEnum(NodeState), nullable=False)
    to_state = Column(SQLEnum(NodeState), nullable=False)

    # Transition metadata
    trigger = Column(String(100), nullable=False)  # What triggered the transition
    details = Column(JSON, default=dict)  # Additional context

    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    node = relationship("SLMNode", back_populates="state_transitions")

    def __repr__(self):
        """Return string representation of SLMStateTransition."""
        return (
            f"<SLMStateTransition(node_id='{self.node_id}', "
            f"{self.from_state} -> {self.to_state})>"
        )


class SLMDeployment(Base):
    """
    Deployment tracking for role deployments and updates.

    Tracks deployment operations including strategy, progress, and results.
    """
    __tablename__ = 'slm_deployments'

    id = Column(Integer, primary_key=True)
    role_name = Column(String(100), nullable=False, index=True)

    # Deployment configuration
    target_nodes = Column(JSON, default=list)  # List of node names/IDs
    strategy = Column(SQLEnum(DeploymentStrategy), nullable=False)
    strategy_params = Column(JSON)  # Strategy configuration parameters

    # Deployment state
    status = Column(String(50), nullable=False, index=True)  # queued, running, success, failed
    current_step = Column(String(100))
    progress = Column(Integer, default=0)  # 0-100 percentage

    # Execution tracking
    initiated_by = Column(String(100))
    ansible_run_id = Column(String(36), index=True)
    log_path = Column(String(500))
    error_message = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    rollback_at = Column(DateTime)  # When rollback occurred

    def __repr__(self):
        """Return string representation of SLMDeployment."""
        return (
            f"<SLMDeployment(id={self.id}, role='{self.role_name}', "
            f"status='{self.status}')>"
        )


class SLMMaintenanceWindow(Base):
    """
    Scheduled maintenance windows for nodes.

    Tracks planned maintenance operations with scheduling and approval workflow.
    """
    __tablename__ = 'slm_maintenance_windows'

    id = Column(Integer, primary_key=True)
    node_id = Column(String(36), ForeignKey('slm_nodes.id', ondelete='CASCADE'), nullable=False, index=True)

    # Maintenance details
    maintenance_type = Column(SQLEnum(MaintenanceType), nullable=False)
    reason = Column(Text, nullable=False)

    # Scheduling
    scheduled_start = Column(DateTime, nullable=False)
    scheduled_end = Column(DateTime, nullable=False)
    actual_start = Column(DateTime)
    actual_end = Column(DateTime)

    # Approval workflow
    requested_by = Column(String(100))
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    status = Column(String(50), default='pending', nullable=False, index=True)
    executed = Column(Boolean, default=False)  # Whether maintenance was executed

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        """Return string representation of SLMMaintenanceWindow."""
        return (
            f"<SLMMaintenanceWindow(id={self.id}, node_id='{self.node_id}', "
            f"type='{self.maintenance_type}', status='{self.status}')>"
        )
