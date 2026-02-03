# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Models Package

Database models and Pydantic schemas for the SLM.
"""

from .database import (
    Base,
    Node,
    NodeStatus,
    Deployment,
    DeploymentStatus,
    Backup,
    BackupStatus,
    Setting,
    User,
)
from .schemas import (
    TokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    NodeCreate,
    NodeUpdate,
    NodeResponse,
    NodeListResponse,
    HeartbeatRequest,
    DeploymentCreate,
    DeploymentResponse,
    DeploymentListResponse,
    BackupCreate,
    BackupResponse,
    SettingUpdate,
    SettingResponse,
    RoleInfo,
    RoleListResponse,
    HealthResponse,
    SystemMetrics,
)

__all__ = [
    # Database models
    "Base",
    "Node",
    "NodeStatus",
    "Deployment",
    "DeploymentStatus",
    "Backup",
    "BackupStatus",
    "Setting",
    "User",
    # Auth schemas
    "TokenRequest",
    "TokenResponse",
    "UserCreate",
    "UserResponse",
    # Node schemas
    "NodeCreate",
    "NodeUpdate",
    "NodeResponse",
    "NodeListResponse",
    "HeartbeatRequest",
    # Deployment schemas
    "DeploymentCreate",
    "DeploymentResponse",
    "DeploymentListResponse",
    # Backup schemas
    "BackupCreate",
    "BackupResponse",
    # Settings schemas
    "SettingUpdate",
    "SettingResponse",
    # Role schemas
    "RoleInfo",
    "RoleListResponse",
    # Health schemas
    "HealthResponse",
    "SystemMetrics",
]
