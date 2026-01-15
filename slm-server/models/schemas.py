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

from .database import NodeStatus, DeploymentStatus, BackupStatus


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
