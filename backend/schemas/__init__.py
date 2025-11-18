# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pydantic Schemas for FastAPI Request/Response Validation
"""

from backend.schemas.infrastructure import (
    DeploymentCreate,
    DeploymentResponse,
    HostCreate,
    HostResponse,
    HostUpdate,
    RoleResponse,
    StatisticsResponse,
)

__all__ = [
    "HostCreate",
    "HostResponse",
    "HostUpdate",
    "DeploymentCreate",
    "DeploymentResponse",
    "RoleResponse",
    "StatisticsResponse",
]
