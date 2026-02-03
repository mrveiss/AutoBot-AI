# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Database Models

SQLAlchemy models for SLM state persistence.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models."""


class NodeStatus(str, enum.Enum):
    """Node status enumeration."""

    PENDING = "pending"
    ENROLLING = "enrolling"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class DeploymentStatus(str, enum.Enum):
    """Deployment status enumeration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class BackupStatus(str, enum.Enum):
    """Backup status enumeration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CodeStatus(str, enum.Enum):
    """Code version status (Issue #741)."""

    UP_TO_DATE = "up_to_date"
    OUTDATED = "outdated"
    UNKNOWN = "unknown"


class RoleStatus(str, enum.Enum):
    """Role detection status (Issue #779)."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    NOT_INSTALLED = "not_installed"


class SyncType(str, enum.Enum):
    """Code sync type (Issue #779)."""

    COMPONENT = "component"
    PACKAGE = "package"


class Node(Base):
    """Node model representing a managed machine."""

    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(64), unique=True, nullable=False, index=True)
    hostname = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=False)
    status = Column(String(20), default=NodeStatus.PENDING.value)
    roles = Column(JSON, default=list)

    # SSH connectivity
    ssh_user = Column(String(64), default="autobot")
    ssh_port = Column(Integer, default=22)
    auth_method = Column(String(20), default="key")

    # Health metrics
    cpu_percent = Column(Float, default=0.0)
    memory_percent = Column(Float, default=0.0)
    disk_percent = Column(Float, default=0.0)
    last_heartbeat = Column(DateTime, nullable=True)

    # Metadata
    agent_version = Column(String(20), nullable=True)
    os_info = Column(String(255), nullable=True)
    extra_data = Column(JSON, default=dict)

    # Code version tracking (Issue #741)
    code_version = Column(String(64), nullable=True)
    code_status = Column(String(20), default=CodeStatus.UNKNOWN.value)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Deployment(Base):
    """Deployment model for tracking role deployments."""

    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_id = Column(String(64), unique=True, nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    roles = Column(JSON, default=list)
    status = Column(String(20), default=DeploymentStatus.PENDING.value)

    # Execution details
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    playbook_output = Column(Text, nullable=True)

    # Metadata
    triggered_by = Column(String(64), nullable=True)
    extra_data = Column(JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Backup(Base):
    """Backup model for tracking backup operations."""

    __tablename__ = "backups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    backup_id = Column(String(64), unique=True, nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    service_type = Column(String(32), default="redis")
    backup_path = Column(String(512), nullable=True)
    status = Column(String(20), default=BackupStatus.PENDING.value)

    # Backup details
    size_bytes = Column(Integer, default=0)
    checksum = Column(String(64), nullable=True)
    error = Column(Text, nullable=True)

    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Setting(Base):
    """Settings model for storing configuration."""

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(20), default="string")  # string, int, bool, json
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    """User model for authentication."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


class EventType(str, enum.Enum):
    """Node event type enumeration."""

    STATE_CHANGE = "state_change"
    HEALTH_CHECK = "health_check"
    DEPLOYMENT_STARTED = "deployment_started"
    DEPLOYMENT_COMPLETED = "deployment_completed"
    DEPLOYMENT_FAILED = "deployment_failed"
    CERTIFICATE_ISSUED = "certificate_issued"
    CERTIFICATE_RENEWED = "certificate_renewed"
    CERTIFICATE_EXPIRING = "certificate_expiring"
    REMEDIATION_STARTED = "remediation_started"
    REMEDIATION_COMPLETED = "remediation_completed"
    ROLLBACK_STARTED = "rollback_started"
    ROLLBACK_COMPLETED = "rollback_completed"
    MANUAL_ACTION = "manual_action"


class EventSeverity(str, enum.Enum):
    """Event severity enumeration."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReplicationStatus(str, enum.Enum):
    """Replication status enumeration."""

    PENDING = "pending"
    SYNCING = "syncing"
    ACTIVE = "active"
    FAILED = "failed"
    STOPPED = "stopped"


class ServiceStatus(str, enum.Enum):
    """Systemd service status enumeration."""

    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ServiceCategory(str, enum.Enum):
    """Service category enumeration for filtering."""

    AUTOBOT = "autobot"
    SYSTEM = "system"


class NodeEvent(Base):
    """Node event log for tracking lifecycle events."""

    __tablename__ = "node_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    event_type = Column(String(32), nullable=False)
    severity = Column(String(16), default=EventSeverity.INFO.value)
    message = Column(Text, nullable=False)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class Certificate(Base):
    """Certificate tracking for mTLS."""

    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cert_id = Column(String(64), unique=True, nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    serial_number = Column(String(64), nullable=True)
    subject = Column(String(255), nullable=True)
    issuer = Column(String(255), nullable=True)
    not_before = Column(DateTime, nullable=True)
    not_after = Column(DateTime, nullable=True)
    fingerprint = Column(String(64), nullable=True)
    status = Column(String(20), default="pending")  # pending, active, expired, revoked
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Replication(Base):
    """Replication tracking for stateful services."""

    __tablename__ = "replications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    replication_id = Column(String(64), unique=True, nullable=False, index=True)
    source_node_id = Column(String(64), nullable=False)
    target_node_id = Column(String(64), nullable=False)
    service_type = Column(String(32), default="redis")
    status = Column(String(20), default=ReplicationStatus.PENDING.value)
    sync_position = Column(String(128), nullable=True)
    lag_bytes = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UpdateInfo(Base):
    """Available updates tracking."""

    __tablename__ = "update_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    update_id = Column(String(64), unique=True, nullable=False, index=True)
    node_id = Column(String(64), nullable=True, index=True)  # null = applies to all
    package_name = Column(String(128), nullable=False)
    current_version = Column(String(32), nullable=True)
    available_version = Column(String(32), nullable=False)
    severity = Column(String(16), default="low")  # low, medium, high, critical
    description = Column(Text, nullable=True)
    is_applied = Column(Boolean, default=False)
    applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UpdateJobStatus(str, enum.Enum):
    """Update job execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UpdateJob(Base):
    """Update job tracking for async update operations."""

    __tablename__ = "update_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), unique=True, nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    status = Column(String(20), default=UpdateJobStatus.PENDING.value)
    update_ids = Column(JSON, default=list)  # List of update_ids being applied
    progress = Column(Integer, default=0)  # 0-100
    current_step = Column(String(256), nullable=True)  # Current step description
    total_steps = Column(Integer, default=0)
    completed_steps = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    output = Column(Text, nullable=True)  # Command output/logs
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Service(Base):
    """Service tracking for systemd services on nodes."""

    __tablename__ = "services"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(64), nullable=False, index=True)
    service_name = Column(String(128), nullable=False)
    status = Column(String(20), default=ServiceStatus.UNKNOWN.value)
    category = Column(String(20), default=ServiceCategory.SYSTEM.value, index=True)
    enabled = Column(Boolean, default=False)  # starts on boot
    description = Column(String(512), nullable=True)
    active_state = Column(String(32), nullable=True)  # active, inactive, failed
    sub_state = Column(String(32), nullable=True)  # running, dead, exited
    main_pid = Column(Integer, nullable=True)
    memory_bytes = Column(Integer, nullable=True)
    last_checked = Column(DateTime, nullable=True)
    extra_data = Column(JSON, default=dict)

    # Service Discovery Fields (Issue #760)
    port = Column(Integer, nullable=True)  # e.g., 8001, 6379
    protocol = Column(String(10), default="http")  # http, https, ws, wss, redis, tcp
    endpoint_path = Column(String(256), nullable=True)  # e.g., "/api/health"
    is_discoverable = Column(Boolean, default=True)  # Include in discovery responses

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite unique constraint - one service record per node
    __table_args__ = (
        UniqueConstraint("node_id", "service_name", name="uq_node_service"),
    )


class NodeConfig(Base):
    """Per-node configuration with inheritance support (Issue #760).

    When node_id is NULL, the config is a global default.
    Resolution order: node-specific → global default → not found.
    """

    __tablename__ = "node_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(64), nullable=True, index=True)  # NULL = global default
    config_key = Column(String(128), nullable=False, index=True)
    config_value = Column(Text, nullable=True)
    value_type = Column(String(20), default="string")  # string, int, bool, json

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("node_id", "config_key", name="uq_node_config"),)


class ServiceConflict(Base):
    """Tracks services that cannot coexist on the same node (Issue #760).

    Examples: redis-server vs redis-stack-server (port 6379),
    apache2 vs nginx (port 80/443).
    """

    __tablename__ = "service_conflicts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_name_a = Column(String(128), nullable=False, index=True)
    service_name_b = Column(String(128), nullable=False, index=True)
    reason = Column(Text, nullable=True)  # e.g., "Both bind to port 6379"
    conflict_type = Column(String(32), default="port")  # port, dependency, resource

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "service_name_a", "service_name_b", name="uq_service_conflict"
        ),
    )


class Agent(Base):
    """AI Agent with LLM configuration (Issue #760 Phase 2).

    Each agent can have its own LLM provider configuration.
    One agent with is_default=True serves as fallback.
    """

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)

    # LLM Configuration
    llm_provider = Column(String(32), nullable=False)  # ollama, openai, anthropic
    llm_endpoint = Column(String(256), nullable=True)
    llm_model = Column(String(64), nullable=False)
    llm_api_key_encrypted = Column(Text, nullable=True)
    llm_timeout = Column(Integer, default=30)
    llm_temperature = Column(Float, default=0.7)
    llm_max_tokens = Column(Integer, nullable=True)

    # State
    is_default = Column(Boolean, default=False, index=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MaintenanceWindow(Base):
    """Maintenance window scheduling for nodes."""

    __tablename__ = "maintenance_windows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    window_id = Column(String(64), unique=True, nullable=False, index=True)
    node_id = Column(String(64), nullable=True, index=True)  # null = all nodes
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    reason = Column(String(512), nullable=True)
    auto_drain = Column(Boolean, default=False)  # drain services before maintenance
    suppress_alerts = Column(Boolean, default=True)  # suppress alerts during window
    suppress_remediation = Column(Boolean, default=True)  # suppress auto-remediation
    status = Column(
        String(20), default="scheduled"
    )  # scheduled, active, completed, cancelled
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BlueGreenStatus(str, enum.Enum):
    """Blue-green deployment status enumeration."""

    PENDING = "pending"
    BORROWING = "borrowing"  # Borrowing roles to green node
    DEPLOYING = "deploying"  # Deploying to green node
    VERIFYING = "verifying"  # Health verification
    SWITCHING = "switching"  # Traffic switch in progress
    ACTIVE = "active"  # Green is live, traffic switched
    MONITORING = "monitoring"  # Post-deployment health monitoring (Issue #726 Phase 3)
    ROLLING_BACK = "rolling_back"  # Rollback in progress
    ROLLED_BACK = "rolled_back"  # Reverted to blue
    COMPLETED = "completed"  # Successfully switched
    FAILED = "failed"  # Deployment failed


class BlueGreenDeployment(Base):
    """Blue-green deployment with role borrowing.

    Tracks zero-downtime deployments where:
    - Blue = current production node running the role
    - Green = standby node (e.g., NPU worker) temporarily running the role
    - Role borrowing allows any node to temporarily assume another role
    - Full purge on role release ensures clean slate
    """

    __tablename__ = "blue_green_deployments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bg_deployment_id = Column(String(64), unique=True, nullable=False, index=True)

    # Blue (source/current) node
    blue_node_id = Column(String(64), nullable=False, index=True)
    blue_roles = Column(JSON, default=list)  # Roles being migrated

    # Green (target/new) node
    green_node_id = Column(String(64), nullable=False, index=True)
    green_original_roles = Column(JSON, default=list)  # Original roles before borrowing

    # Borrowed roles tracking
    borrowed_roles = Column(JSON, default=list)  # Roles borrowed by green
    purge_on_complete = Column(Boolean, default=True)  # Clean slate on completion

    # Deployment configuration
    deployment_type = Column(
        String(32), default="upgrade"
    )  # upgrade, migration, failover
    health_check_url = Column(String(512), nullable=True)  # Optional health endpoint
    health_check_interval = Column(Integer, default=10)  # Seconds between checks
    health_check_timeout = Column(
        Integer, default=300
    )  # Max time for health verification
    auto_rollback = Column(Boolean, default=True)  # Rollback on health failure

    # Post-deployment health monitoring (Issue #726 Phase 3)
    post_deploy_monitor_duration = Column(
        Integer, default=1800
    )  # 30 min monitoring after switch
    health_failure_threshold = Column(
        Integer, default=3
    )  # Consecutive failures before rollback
    health_failures = Column(Integer, default=0)  # Current consecutive failure count
    monitoring_started_at = Column(DateTime, nullable=True)  # When monitoring started

    # Status tracking
    status = Column(String(32), default=BlueGreenStatus.PENDING.value)
    progress_percent = Column(Integer, default=0)
    current_step = Column(String(128), nullable=True)
    error = Column(Text, nullable=True)

    # Timestamps
    started_at = Column(DateTime, nullable=True)
    switched_at = Column(DateTime, nullable=True)  # When traffic switched to green
    completed_at = Column(DateTime, nullable=True)
    rollback_at = Column(DateTime, nullable=True)

    # Metadata
    triggered_by = Column(String(64), nullable=True)
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CredentialType(str, enum.Enum):
    """Credential type enumeration."""

    VNC = "vnc"
    SSH = "ssh"
    API_KEY = "api_key"
    DATABASE = "database"
    TLS = "tls"  # Issue #725: TLS certificates for mTLS


class NodeCredential(Base):
    """Encrypted credential storage for node services.

    Supports VNC, SSH, and other credential types with
    Fernet-encrypted sensitive fields.
    """

    __tablename__ = "node_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    credential_id = Column(String(64), unique=True, nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    credential_type = Column(String(32), nullable=False)  # vnc, ssh, api_key, etc.
    name = Column(String(128), nullable=True)  # Optional friendly name

    # Encrypted fields (Fernet)
    encrypted_password = Column(String(512), nullable=True)
    encrypted_data = Column(Text, nullable=True)  # Encrypted JSON blob

    # VNC-specific fields (non-sensitive, stored unencrypted)
    port = Column(Integer, nullable=True)  # websockify port
    vnc_type = Column(String(32), nullable=True)  # desktop, browser, custom
    display_number = Column(Integer, nullable=True)  # X display
    vnc_port = Column(Integer, nullable=True)  # Raw VNC port
    websockify_enabled = Column(Boolean, default=True)

    # TLS-specific fields (Issue #725: mTLS certificate storage)
    # Certs stored in encrypted_data as JSON: {"ca_cert", "server_cert", "server_key"}
    tls_common_name = Column(String(255), nullable=True)  # CN from certificate
    tls_expires_at = Column(DateTime, nullable=True)  # Certificate expiration
    tls_fingerprint = Column(String(64), nullable=True)  # SHA256 fingerprint

    # State
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite unique constraint - one credential per node/type/name combo
    __table_args__ = (
        UniqueConstraint(
            "node_id", "credential_type", "name", name="uq_node_cred_type_name"
        ),
    )


# =============================================================================
# Security Models (Issue #728: Security Analytics)
# =============================================================================


class AuditLogCategory(str, enum.Enum):
    """Audit log category enumeration."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CONFIGURATION = "configuration"
    DEPLOYMENT = "deployment"
    NODE_MANAGEMENT = "node_management"
    SERVICE_CONTROL = "service_control"
    SECURITY = "security"
    SYSTEM = "system"


class SecurityEventType(str, enum.Enum):
    """Security event type enumeration."""

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    SESSION_EXPIRED = "session_expired"
    BRUTE_FORCE_DETECTED = "brute_force_detected"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    POLICY_VIOLATION = "policy_violation"
    CERTIFICATE_EXPIRING = "certificate_expiring"
    CERTIFICATE_EXPIRED = "certificate_expired"
    SSH_KEY_ADDED = "ssh_key_added"
    SSH_KEY_REMOVED = "ssh_key_removed"
    FIREWALL_RULE_CHANGED = "firewall_rule_changed"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    MALWARE_DETECTED = "malware_detected"


class SecurityEventSeverity(str, enum.Enum):
    """Security event severity enumeration."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyStatus(str, enum.Enum):
    """Security policy status enumeration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"


class AuditLog(Base):
    """Audit log for tracking all user actions and system events."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    log_id = Column(String(64), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Actor information
    user_id = Column(String(64), nullable=True, index=True)
    username = Column(String(64), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)

    # Action details
    category = Column(String(32), nullable=False, index=True)
    action = Column(String(128), nullable=False)
    resource_type = Column(String(64), nullable=True)  # node, service, deployment, etc.
    resource_id = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)

    # Request/Response details
    request_method = Column(String(10), nullable=True)  # GET, POST, etc.
    request_path = Column(String(512), nullable=True)
    request_body = Column(JSON, nullable=True)  # Sanitized request body
    response_status = Column(Integer, nullable=True)
    response_time_ms = Column(Float, nullable=True)

    # Outcome
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    # Metadata
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class SecurityEvent(Base):
    """Security event tracking for threat detection and monitoring."""

    __tablename__ = "security_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Event classification
    event_type = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), default=SecurityEventSeverity.LOW.value, index=True)
    category = Column(String(32), nullable=True)

    # Source information
    source_ip = Column(String(45), nullable=True, index=True)
    source_user = Column(String(64), nullable=True)
    source_node_id = Column(String(64), nullable=True, index=True)

    # Target information
    target_resource = Column(String(128), nullable=True)
    target_node_id = Column(String(64), nullable=True)

    # Event details
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    raw_data = Column(JSON, default=dict)

    # Threat intelligence
    threat_indicator = Column(String(255), nullable=True)  # IOC, hash, IP, etc.
    threat_score = Column(Float, nullable=True)  # 0.0 - 1.0
    mitre_technique = Column(String(32), nullable=True)  # MITRE ATT&CK ID

    # Status
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(64), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(String(64), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SecurityPolicy(Base):
    """Security policy definitions for enforcement across the fleet."""

    __tablename__ = "security_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    policy_id = Column(String(64), unique=True, nullable=False, index=True)

    # Policy identification
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(
        String(64), nullable=False
    )  # authentication, access_control, network, etc.

    # Policy configuration
    policy_type = Column(String(32), default="custom")  # builtin, custom
    rules = Column(JSON, default=list)  # List of rule definitions
    parameters = Column(JSON, default=dict)  # Policy parameters

    # Scope
    applies_to_nodes = Column(JSON, default=list)  # Empty = all nodes
    applies_to_roles = Column(JSON, default=list)  # Empty = all roles

    # Status
    status = Column(String(16), default=PolicyStatus.DRAFT.value)
    is_enforced = Column(Boolean, default=False)

    # Compliance tracking
    last_evaluated = Column(DateTime, nullable=True)
    compliance_score = Column(Float, nullable=True)  # 0.0 - 100.0
    violations_count = Column(Integer, default=0)

    # Versioning
    version = Column(Integer, default=1)
    previous_version_id = Column(String(64), nullable=True)

    # Metadata
    created_by = Column(String(64), nullable=True)
    updated_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =============================================================================
# Code Sync Models (Issue #741: Phase 7 - Scheduled Updates)
# =============================================================================


class ScheduleTargetType(str, enum.Enum):
    """Schedule target type enumeration."""

    ALL = "all"
    SPECIFIC = "specific"
    TAG = "tag"


class UpdateSchedule(Base):
    """Scheduled code sync configuration.

    Allows administrators to configure automatic code updates at specific
    times using cron expressions for maintenance windows and automated rollouts.
    """

    __tablename__ = "update_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    cron_expression = Column(String(100), nullable=False)  # e.g., "0 2 * * *"
    enabled = Column(Boolean, default=True, nullable=False)

    # Target configuration
    target_type = Column(String(20), default=ScheduleTargetType.ALL.value)
    target_nodes = Column(JSON, nullable=True)  # List of node_ids or tag names

    # Sync options
    restart_strategy = Column(
        String(20), default="graceful"
    )  # graceful, immediate, manual
    restart_after_sync = Column(Boolean, default=True)

    # Execution tracking
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    last_run_status = Column(String(20), nullable=True)  # success, failed, partial
    last_run_message = Column(Text, nullable=True)

    # Metadata
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =============================================================================
# Role-Based Code Sync Models (Issue #779)
# =============================================================================


class Role(Base):
    """Role definition for code distribution (Issue #779)."""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=True)
    sync_type = Column(String(20), default=SyncType.COMPONENT.value)
    source_paths = Column(JSON, nullable=False, default=list)
    target_path = Column(String(255), nullable=False)
    systemd_service = Column(String(100), nullable=True)
    auto_restart = Column(Boolean, default=False)
    health_check_port = Column(Integer, nullable=True)
    health_check_path = Column(String(255), nullable=True)
    pre_sync_cmd = Column(Text, nullable=True)
    post_sync_cmd = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
