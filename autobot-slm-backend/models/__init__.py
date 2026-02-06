# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Models Package

Database models and Pydantic schemas for the SLM.
"""

from .database import (
    Backup,
    BackupStatus,
    Base,
    Deployment,
    DeploymentStatus,
    Node,
    NodeStatus,
    Setting,
    User,
)
from .schemas import (
    BackupCreate,
    BackupResponse,
    DeploymentCreate,
    DeploymentListResponse,
    DeploymentResponse,
    HealthResponse,
    HeartbeatRequest,
    NodeCreate,
    NodeListResponse,
    NodeResponse,
    NodeUpdate,
    RoleInfo,
    RoleListResponse,
    SettingResponse,
    SettingUpdate,
    SystemMetrics,
    TokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
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
