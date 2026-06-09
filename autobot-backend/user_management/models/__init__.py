# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SQLAlchemy Models for User Management System

All models use UUID primary keys and include:
- Created/updated timestamps
- Soft delete support where applicable
- Multi-tenancy via org_id foreign key
"""

# Issue #898: Import backend.models AFTER local models to ensure
# user_management.models.base is fully initialized before activity
# models import from it, preventing the circular import metaclass
# conflict (#4300).
import models  # noqa: F401 - imports for side effects
from user_management.models.api_key import APIKey
from user_management.models.audit import AuditLog
from user_management.models.base import Base, TenantMixin, TimestampMixin
from user_management.models.mfa import UserMFA
from user_management.models.organization import Organization
from user_management.models.retention_policy import RetentionPolicy
from user_management.models.role import Permission, Role, RolePermission, UserRole
from user_management.models.sso import SSOProvider, UserSSOLink
from user_management.models.team import Team, TeamMembership
from user_management.models.user import User

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
    "RetentionPolicy",
]
