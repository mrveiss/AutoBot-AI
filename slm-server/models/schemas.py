# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Pydantic Schemas

Request and response models for the SLM API.
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .database import NodeStatus, DeploymentStatus, BackupStatus, ServiceStatus


# =============================================================================
# Authentication Schemas
# =============================================================================


class TokenRequest(BaseModel):
    """Login request."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserCreate(BaseModel):
    """User creation request."""

    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8)
    is_admin: bool = False


class UserResponse(BaseModel):
    """User response (excludes password)."""

    id: int
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


# =============================================================================
# Node Schemas
# =============================================================================


class NodeCreate(BaseModel):
    """Node registration request."""

    hostname: str
    ip_address: str
    roles: List[str] = Field(default_factory=list)
    ssh_user: Optional[str] = "autobot"
    ssh_port: Optional[int] = 22
    ssh_password: Optional[str] = None
    auth_method: Optional[str] = "password"
    import_existing: bool = False
    auto_enroll: bool = False


class NodeUpdate(BaseModel):
    """Node update request."""

    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    status: Optional[NodeStatus] = None
    roles: Optional[List[str]] = None


class NodeResponse(BaseModel):
    """Node response."""

    id: int
    node_id: str
    hostname: str
    ip_address: str
    status: str
    roles: List[str]
    ssh_user: Optional[str] = "autobot"
    ssh_port: Optional[int] = 22
    auth_method: Optional[str] = "key"
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    last_heartbeat: Optional[datetime] = None
    agent_version: Optional[str] = None
    os_info: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NodeListResponse(BaseModel):
    """Paginated node list."""

    nodes: List[NodeResponse]
    total: int
    page: int
    per_page: int


class HeartbeatRequest(BaseModel):
    """Agent heartbeat request."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    agent_version: Optional[str] = None
    os_info: Optional[str] = None
    extra_data: Dict = Field(default_factory=dict)


class EnrollRequest(BaseModel):
    """Node enrollment request with SSH credentials."""

    ssh_password: Optional[str] = None


# =============================================================================
# Deployment Schemas
# =============================================================================


class DeploymentCreate(BaseModel):
    """Deployment request."""

    node_id: str
    roles: List[str]
    extra_data: Dict = Field(default_factory=dict)


class DeploymentResponse(BaseModel):
    """Deployment response."""

    id: int
    deployment_id: str
    node_id: str
    roles: List[str]
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    triggered_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeploymentListResponse(BaseModel):
    """Paginated deployment list."""

    deployments: List[DeploymentResponse]
    total: int
    page: int
    per_page: int


# =============================================================================
# Backup Schemas
# =============================================================================


class BackupCreate(BaseModel):
    """Backup request."""

    node_id: str
    service_type: str = "redis"


class BackupResponse(BaseModel):
    """Backup response."""

    id: int
    backup_id: str
    node_id: str
    service_type: str
    backup_path: Optional[str] = None
    status: str
    size_bytes: int
    checksum: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# Settings Schemas
# =============================================================================


class SettingUpdate(BaseModel):
    """Setting update request."""

    value: str
    description: Optional[str] = None


class SettingResponse(BaseModel):
    """Setting response."""

    id: int
    key: str
    value: Optional[str] = None
    value_type: str
    description: Optional[str] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# Role Schemas
# =============================================================================


class RoleInfo(BaseModel):
    """Available role information."""

    name: str
    description: str
    category: str
    dependencies: List[str] = Field(default_factory=list)
    variables: Dict = Field(default_factory=dict)
    tools: List[str] = Field(default_factory=list)


class RoleListResponse(BaseModel):
    """List of available roles."""

    roles: List[RoleInfo]


# =============================================================================
# Health Schemas
# =============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    uptime_seconds: float
    database: str
    nodes_online: int
    nodes_total: int


class SystemMetrics(BaseModel):
    """System metrics response."""

    cpu_percent: float
    memory_percent: float
    disk_percent: float
    load_average: List[float]


# =============================================================================
# Connection Test Schemas
# =============================================================================


class ConnectionTestRequest(BaseModel):
    """SSH connection test request."""

    ip_address: str
    ssh_user: str = "autobot"
    ssh_port: int = 22
    auth_method: str = "password"
    password: Optional[str] = None


class ConnectionTestResponse(BaseModel):
    """SSH connection test response."""

    success: bool
    message: str
    latency_ms: Optional[float] = None
    os_info: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# Certificate Schemas
# =============================================================================


class CertificateResponse(BaseModel):
    """Certificate status response."""

    cert_id: str
    node_id: str
    serial_number: Optional[str] = None
    subject: Optional[str] = None
    issuer: Optional[str] = None
    not_before: Optional[datetime] = None
    not_after: Optional[datetime] = None
    fingerprint: Optional[str] = None
    status: str
    days_until_expiry: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CertificateActionResponse(BaseModel):
    """Certificate action response."""

    action: str
    success: bool
    message: str
    cert_id: Optional[str] = None


# =============================================================================
# Node Event Schemas
# =============================================================================


class NodeEventResponse(BaseModel):
    """Node event response."""

    event_id: str
    node_id: str
    event_type: str
    severity: str
    message: str
    details: Dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class NodeEventListResponse(BaseModel):
    """Paginated event list."""

    events: List[NodeEventResponse]
    total: int


# =============================================================================
# Update Schemas
# =============================================================================


class UpdateInfoResponse(BaseModel):
    """Update info response."""

    update_id: str
    node_id: Optional[str] = None
    package_name: str
    current_version: Optional[str] = None
    available_version: str
    severity: str
    description: Optional[str] = None
    is_applied: bool
    applied_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateCheckResponse(BaseModel):
    """Update check response."""

    updates: List[UpdateInfoResponse]
    total: int


class UpdateApplyRequest(BaseModel):
    """Update apply request."""

    node_id: str
    update_ids: List[str]


class UpdateApplyResponse(BaseModel):
    """Update apply response."""

    success: bool
    message: str
    job_id: Optional[str] = None
    applied_updates: List[str] = Field(default_factory=list)
    failed_updates: List[str] = Field(default_factory=list)


class UpdateJobResponse(BaseModel):
    """Update job status response for polling."""

    job_id: str
    node_id: str
    status: str
    update_ids: List[str] = Field(default_factory=list)
    progress: int = 0
    current_step: Optional[str] = None
    total_steps: int = 0
    completed_steps: int = 0
    error: Optional[str] = None
    output: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateJobListResponse(BaseModel):
    """List of update jobs."""

    jobs: List[UpdateJobResponse]
    total: int


# =============================================================================
# Replication Schemas
# =============================================================================


class ReplicationCreate(BaseModel):
    """Replication request."""

    source_node_id: str
    target_node_id: str
    service_type: str = "redis"


class ReplicationResponse(BaseModel):
    """Replication response."""

    id: int
    replication_id: str
    source_node_id: str
    target_node_id: str
    service_type: str
    status: str
    sync_position: Optional[str] = None
    lag_bytes: int
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReplicationListResponse(BaseModel):
    """Paginated replication list."""

    replications: List[ReplicationResponse]
    total: int


# =============================================================================
# Backup Schemas (extended)
# =============================================================================


class BackupListResponse(BaseModel):
    """Paginated backup list."""

    backups: List[BackupResponse]
    total: int


class BackupRestoreResponse(BaseModel):
    """Backup restore response."""

    success: bool
    message: str
    job_id: Optional[str] = None


# =============================================================================
# Data Verification Schemas
# =============================================================================


class DataVerifyRequest(BaseModel):
    """Data verification request."""

    node_id: str
    service_type: str = "redis"


class DataVerifyResponse(BaseModel):
    """Data verification response."""

    is_healthy: bool
    service_type: str
    details: Dict = Field(default_factory=dict)
    checks: List[Dict] = Field(default_factory=list)


# =============================================================================
# Action Response Schema
# =============================================================================


class ActionResponse(BaseModel):
    """Generic action response."""

    action: str
    success: bool
    message: str
    resource_id: Optional[str] = None


# =============================================================================
# Service Schemas (Issue #728)
# =============================================================================


class ServiceResponse(BaseModel):
    """Service status response."""

    id: int
    node_id: str
    service_name: str
    status: str
    category: str = "system"  # autobot or system
    enabled: bool
    description: Optional[str] = None
    active_state: Optional[str] = None
    sub_state: Optional[str] = None
    main_pid: Optional[int] = None
    memory_bytes: Optional[int] = None
    last_checked: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServiceListResponse(BaseModel):
    """Service list response."""

    services: List[ServiceResponse]
    total: int


class ServiceActionRequest(BaseModel):
    """Service action request."""

    action: str = Field(..., description="start, stop, or restart")


class ServiceActionResponse(BaseModel):
    """Service action response."""

    action: str
    service_name: str
    node_id: str
    success: bool
    message: str
    job_id: Optional[str] = None


class ServiceLogsRequest(BaseModel):
    """Service logs request."""

    lines: int = Field(default=100, ge=1, le=1000)
    since: Optional[str] = None  # e.g., "1h", "30m", "2d"


class ServiceLogsResponse(BaseModel):
    """Service logs response."""

    service_name: str
    node_id: str
    logs: str
    lines_returned: int


class RestartAllServicesRequest(BaseModel):
    """Request to restart all services on a node (Issue #725)."""

    category: Optional[str] = Field(
        None,
        pattern="^(autobot|system|all)$",
        description="Category of services to restart. 'all' or null restarts all services.",
    )
    exclude_services: List[str] = Field(
        default_factory=list,
        description="List of service names to exclude from restart",
    )


class RestartAllServicesResponse(BaseModel):
    """Response from restart all services operation (Issue #725)."""

    node_id: str
    success: bool
    message: str
    total_services: int
    successful_restarts: int
    failed_restarts: int
    results: List[Dict] = Field(
        default_factory=list,
        description="Per-service restart results: [{service_name, success, message}]",
    )
    slm_agent_restarted: bool = Field(
        False,
        description="Whether SLM agent was restarted (done last)",
    )


class ServiceCategoryUpdate(BaseModel):
    """Request to update service category."""

    category: str = Field(..., pattern="^(autobot|system)$")


class FleetServiceStatus(BaseModel):
    """Service status across the fleet."""

    service_name: str
    category: str = "system"  # autobot or system
    nodes: List[Dict]  # [{node_id, hostname, status}]
    running_count: int
    stopped_count: int
    failed_count: int
    total_nodes: int


class FleetServicesResponse(BaseModel):
    """Aggregated service status across fleet."""

    services: List[FleetServiceStatus]
    total_services: int


# =============================================================================
# Maintenance Window Schemas
# =============================================================================


class MaintenanceWindowCreate(BaseModel):
    """Maintenance window creation request."""

    node_id: Optional[str] = None  # null = all nodes
    start_time: datetime
    end_time: datetime
    reason: Optional[str] = None
    auto_drain: bool = False
    suppress_alerts: bool = True
    suppress_remediation: bool = True


class MaintenanceWindowUpdate(BaseModel):
    """Maintenance window update request."""

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    reason: Optional[str] = None
    auto_drain: Optional[bool] = None
    suppress_alerts: Optional[bool] = None
    suppress_remediation: Optional[bool] = None
    status: Optional[str] = None


class MaintenanceWindowResponse(BaseModel):
    """Maintenance window response."""

    id: int
    window_id: str
    node_id: Optional[str] = None
    start_time: datetime
    end_time: datetime
    reason: Optional[str] = None
    auto_drain: bool
    suppress_alerts: bool
    suppress_remediation: bool
    status: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MaintenanceWindowListResponse(BaseModel):
    """Paginated maintenance window list."""

    windows: List[MaintenanceWindowResponse]
    total: int


# =============================================================================
# Blue-Green Deployment Schemas (Issue #726 Phase 3)
# =============================================================================


class BlueGreenCreate(BaseModel):
    """Blue-green deployment creation request."""

    blue_node_id: str = Field(..., description="Source node (current production)")
    green_node_id: str = Field(..., description="Target node (will receive roles)")
    roles: List[str] = Field(..., description="Roles to migrate from blue to green")
    deployment_type: str = Field(default="upgrade", description="upgrade, migration, or failover")
    health_check_url: Optional[str] = None
    health_check_interval: int = Field(default=10, ge=5, le=60)
    health_check_timeout: int = Field(default=300, ge=60, le=1800)
    auto_rollback: bool = True
    purge_on_complete: bool = True
    # Post-deployment health monitoring (Issue #726 Phase 3)
    post_deploy_monitor_duration: int = Field(
        default=1800, ge=0, le=7200, description="Seconds to monitor after deployment (0=disabled)"
    )
    health_failure_threshold: int = Field(
        default=3, ge=1, le=10, description="Consecutive health failures before rollback"
    )


class BlueGreenResponse(BaseModel):
    """Blue-green deployment response."""

    id: int
    bg_deployment_id: str
    blue_node_id: str
    blue_roles: List[str]
    green_node_id: str
    green_original_roles: List[str]
    borrowed_roles: List[str]
    purge_on_complete: bool
    deployment_type: str
    health_check_url: Optional[str] = None
    health_check_interval: int
    health_check_timeout: int
    auto_rollback: bool
    # Post-deployment health monitoring (Issue #726 Phase 3)
    post_deploy_monitor_duration: int
    health_failure_threshold: int
    health_failures: int = 0
    monitoring_started_at: Optional[datetime] = None
    # Status tracking
    status: str
    progress_percent: int
    current_step: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    switched_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    rollback_at: Optional[datetime] = None
    triggered_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BlueGreenListResponse(BaseModel):
    """Paginated blue-green deployment list."""

    deployments: List[BlueGreenResponse]
    total: int
    page: int
    per_page: int


class BlueGreenActionResponse(BaseModel):
    """Blue-green action response."""

    action: str
    bg_deployment_id: str
    success: bool
    message: str
    status: Optional[str] = None


class RoleBorrowRequest(BaseModel):
    """Request to borrow roles temporarily."""

    source_node_id: str
    target_node_id: str
    roles: List[str]
    duration_minutes: int = Field(default=60, ge=5, le=1440)


class RoleBorrowResponse(BaseModel):
    """Role borrowing response."""

    success: bool
    message: str
    borrowed_roles: List[str]
    source_node_id: str
    target_node_id: str
    expires_at: Optional[datetime] = None


class RolePurgeRequest(BaseModel):
    """Request to purge roles from a node."""

    node_id: str
    roles: List[str]
    force: bool = False  # Force purge even if services are running


class RolePurgeResponse(BaseModel):
    """Role purge response."""

    success: bool
    message: str
    purged_roles: List[str]
    node_id: str
    services_stopped: List[str] = Field(default_factory=list)


class EligibleNodeResponse(BaseModel):
    """Node eligible for role borrowing."""

    node_id: str
    hostname: str
    ip_address: str
    current_roles: List[str]
    available_capacity: float  # 0-100, based on CPU/memory headroom
    status: str


class EligibleNodesResponse(BaseModel):
    """List of nodes eligible for role borrowing."""

    nodes: List[EligibleNodeResponse]
    total: int


# =============================================================================
# VNC Credential Schemas (Issue #725)
# =============================================================================


class VNCCredentialCreate(BaseModel):
    """Create VNC credential for a node."""

    vnc_type: str = Field(default="desktop", pattern="^(desktop|browser|custom)$")
    name: Optional[str] = Field(
        None, description="Optional friendly name for the credential"
    )
    password: str = Field(..., min_length=1, description="VNC password (will be encrypted)")
    port: Optional[int] = Field(None, ge=1, le=65535, description="websockify port")
    display_number: Optional[int] = Field(None, ge=0, le=99, description="X display number")
    vnc_port: Optional[int] = Field(
        None, ge=1, le=65535, description="Raw VNC port (auto-calculated if not provided)"
    )
    websockify_enabled: bool = Field(default=True, description="Enable websockify for noVNC")
    extra_data: Dict = Field(default_factory=dict, description="Additional configuration")


class VNCCredentialUpdate(BaseModel):
    """Update VNC credential."""

    password: Optional[str] = Field(None, min_length=1)
    port: Optional[int] = Field(None, ge=1, le=65535)
    display_number: Optional[int] = Field(None, ge=0, le=99)
    vnc_port: Optional[int] = Field(None, ge=1, le=65535)
    websockify_enabled: Optional[bool] = None
    is_active: Optional[bool] = None
    extra_data: Optional[Dict] = None


class VNCCredentialResponse(BaseModel):
    """VNC credential response (excludes password for security)."""

    id: int
    credential_id: str
    node_id: str
    vnc_type: Optional[str] = None
    name: Optional[str] = None
    port: Optional[int] = None
    display_number: Optional[int] = None
    vnc_port: Optional[int] = None
    websockify_enabled: bool = True
    is_active: bool = True
    last_used: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # Computed connection URL (no password)
    websocket_url: Optional[str] = None

    model_config = {"from_attributes": True}


class VNCCredentialListResponse(BaseModel):
    """List of VNC credentials."""

    credentials: List[VNCCredentialResponse]
    total: int


class VNCConnectionInfo(BaseModel):
    """VNC connection info with secure token for password retrieval."""

    credential_id: str
    node_id: str
    vnc_type: str
    host: str  # Node IP address
    port: int
    display_number: int
    websocket_url: str
    # Short-lived token for password retrieval (one-time use)
    connection_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None


class VNCEndpointResponse(BaseModel):
    """VNC endpoint in fleet-wide listing."""

    credential_id: str
    node_id: str
    hostname: str
    ip_address: str
    vnc_type: str
    name: Optional[str] = None
    port: int
    websocket_url: str
    is_active: bool


class VNCEndpointsResponse(BaseModel):
    """List of all VNC endpoints across the fleet."""

    endpoints: List[VNCEndpointResponse]
    total: int


# =============================================================================
# TLS Certificate Schemas (Issue #725: mTLS support)
# =============================================================================


class TLSCredentialCreate(BaseModel):
    """Create TLS certificate credential for a node."""

    name: Optional[str] = Field(
        None, description="Optional friendly name (e.g., 'redis-server', 'api-client')"
    )
    ca_cert: str = Field(..., description="CA certificate (PEM format)")
    server_cert: str = Field(..., description="Server/client certificate (PEM format)")
    server_key: str = Field(..., description="Private key (PEM format, will be encrypted)")
    common_name: Optional[str] = Field(None, description="CN from certificate (auto-extracted if not provided)")
    expires_at: Optional[datetime] = Field(None, description="Expiration date (auto-extracted if not provided)")
    extra_data: Dict = Field(default_factory=dict, description="Additional configuration")


class TLSCredentialUpdate(BaseModel):
    """Update TLS certificate credential."""

    ca_cert: Optional[str] = Field(None, description="Updated CA certificate")
    server_cert: Optional[str] = Field(None, description="Updated server certificate")
    server_key: Optional[str] = Field(None, description="Updated private key")
    is_active: Optional[bool] = None
    extra_data: Optional[Dict] = None


class TLSCredentialResponse(BaseModel):
    """TLS credential response (excludes private key for security)."""

    id: int
    credential_id: str
    node_id: str
    name: Optional[str] = None
    common_name: Optional[str] = None
    expires_at: Optional[datetime] = None
    fingerprint: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    # Certificates (public data only)
    ca_cert: Optional[str] = None
    server_cert: Optional[str] = None
    # Private key NEVER returned

    model_config = {"from_attributes": True}


class TLSCredentialListResponse(BaseModel):
    """List of TLS credentials."""

    credentials: List[TLSCredentialResponse]
    total: int


class TLSCertificateInfo(BaseModel):
    """Parsed certificate information."""

    common_name: str
    subject: str
    issuer: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    fingerprint: str
    san: List[str] = Field(default_factory=list, description="Subject Alternative Names")


class TLSEndpointResponse(BaseModel):
    """TLS endpoint in fleet-wide listing."""

    credential_id: str
    node_id: str
    hostname: str
    ip_address: str
    name: Optional[str] = None
    common_name: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_active: bool
    days_until_expiry: Optional[int] = None


class TLSEndpointsResponse(BaseModel):
    """List of all TLS endpoints across the fleet."""

    endpoints: List[TLSEndpointResponse]
    total: int
    expiring_soon: int = Field(default=0, description="Certificates expiring within 30 days")


# =============================================================================
# Security Analytics Schemas (Issue #728: Security View)
# =============================================================================


class AuditLogResponse(BaseModel):
    """Audit log entry response."""

    id: int
    log_id: str
    timestamp: datetime
    user_id: Optional[str] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None
    category: str
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    description: Optional[str] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    response_status: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    """Paginated audit log listing."""

    logs: List[AuditLogResponse]
    total: int
    page: int = 1
    per_page: int = 50


class SecurityEventResponse(BaseModel):
    """Security event response."""

    id: int
    event_id: str
    timestamp: datetime
    event_type: str
    severity: str
    category: Optional[str] = None
    source_ip: Optional[str] = None
    source_user: Optional[str] = None
    source_node_id: Optional[str] = None
    target_resource: Optional[str] = None
    target_node_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    threat_indicator: Optional[str] = None
    threat_score: Optional[float] = None
    mitre_technique: Optional[str] = None
    is_acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    is_resolved: bool = False
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SecurityEventCreate(BaseModel):
    """Create security event."""

    event_type: str
    severity: str = "low"
    category: Optional[str] = None
    source_ip: Optional[str] = None
    source_user: Optional[str] = None
    source_node_id: Optional[str] = None
    target_resource: Optional[str] = None
    target_node_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    threat_indicator: Optional[str] = None
    threat_score: Optional[float] = None
    mitre_technique: Optional[str] = None
    raw_data: Dict = Field(default_factory=dict)


class SecurityEventAcknowledge(BaseModel):
    """Acknowledge security event."""

    notes: Optional[str] = None


class SecurityEventResolve(BaseModel):
    """Resolve security event."""

    resolution_notes: str


class SecurityEventListResponse(BaseModel):
    """Paginated security event listing."""

    events: List[SecurityEventResponse]
    total: int
    page: int = 1
    per_page: int = 50
    unacknowledged_count: int = 0
    critical_count: int = 0


class SecurityPolicyResponse(BaseModel):
    """Security policy response."""

    id: int
    policy_id: str
    name: str
    description: Optional[str] = None
    category: str
    policy_type: str = "custom"
    rules: List = Field(default_factory=list)
    parameters: Dict = Field(default_factory=dict)
    applies_to_nodes: List = Field(default_factory=list)
    applies_to_roles: List = Field(default_factory=list)
    status: str = "draft"
    is_enforced: bool = False
    last_evaluated: Optional[datetime] = None
    compliance_score: Optional[float] = None
    violations_count: int = 0
    version: int = 1
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SecurityPolicyCreate(BaseModel):
    """Create security policy."""

    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    category: str = Field(..., min_length=1, max_length=64)
    policy_type: str = "custom"
    rules: List = Field(default_factory=list)
    parameters: Dict = Field(default_factory=dict)
    applies_to_nodes: List = Field(default_factory=list)
    applies_to_roles: List = Field(default_factory=list)
    status: str = "draft"
    is_enforced: bool = False


class SecurityPolicyUpdate(BaseModel):
    """Update security policy."""

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    category: Optional[str] = None
    rules: Optional[List] = None
    parameters: Optional[Dict] = None
    applies_to_nodes: Optional[List] = None
    applies_to_roles: Optional[List] = None
    status: Optional[str] = None
    is_enforced: Optional[bool] = None


class SecurityPolicyListResponse(BaseModel):
    """Paginated security policy listing."""

    policies: List[SecurityPolicyResponse]
    total: int
    page: int = 1
    per_page: int = 50


class SecurityOverviewResponse(BaseModel):
    """Security dashboard overview metrics."""

    security_score: float = Field(..., description="Overall security score (0-100)")
    active_threats: int = Field(default=0, description="Number of unresolved security events")
    failed_logins_24h: int = Field(default=0, description="Failed login attempts in last 24 hours")
    policy_violations: int = Field(default=0, description="Policy violations count")
    total_events_24h: int = Field(default=0, description="Total security events in 24h")
    critical_events: int = Field(default=0, description="Critical severity events")
    certificates_expiring: int = Field(default=0, description="Certificates expiring within 30 days")
    recent_events: List[SecurityEventResponse] = Field(default_factory=list)


class ThreatSummary(BaseModel):
    """Threat detection summary."""

    total_threats: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    acknowledged: int = 0
    resolved: int = 0
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_source_ip: Dict[str, int] = Field(default_factory=dict)
    trend_24h: List[Dict] = Field(default_factory=list, description="Hourly threat count")
