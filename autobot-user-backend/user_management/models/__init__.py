# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SQLAlchemy Models for User Management System

All models use UUID primary keys and include:
- Created/updated timestamps
- Soft delete support where applicable
- Multi-tenancy via org_id foreign key
"""

from backend.user_management.models.base import Base, TenantMixin, TimestampMixin
from backend.user_management.models.organization import Organization
from backend.user_management.models.user import User
from backend.user_management.models.team import Team, TeamMembership
from backend.user_management.models.role import Permission, Role, RolePermission, UserRole
from backend.user_management.models.api_key import APIKey
from backend.user_management.models.sso import SSOProvider, UserSSOLink
from backend.user_management.models.mfa import UserMFA
from backend.user_management.models.audit import AuditLog

__all__ = [
    "Base",
    "TenantMixin",
    "TimestampMixin",
    "Organization",
    "User",
    "Team",
    "TeamMembership",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "APIKey",
    "SSOProvider",
    "UserSSOLink",
    "UserMFA",
    "AuditLog",
]
