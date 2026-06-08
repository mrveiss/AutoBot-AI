# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Role and Permission Models

Implements database-driven RBAC (Role-Based Access Control).
"""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from autobot_shared.auth.permissions import SYSTEM_PERMISSIONS, SYSTEM_ROLES
from user_management.models.base import Base

if TYPE_CHECKING:
    from user_management.models.organization import Organization
    from user_management.models.user import User


class Permission(Base):
    """
    Permission model.

    Represents a specific action that can be performed on a resource.
    Permissions are system-wide (not organization-specific).

    Examples:
        - users:read, users:write, users:delete
        - teams:read, teams:manage
        - knowledge:read, knowledge:write
        - admin:access
    """

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Resource and action for programmatic access
    resource: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Relationships
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="permission",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Permission(name={self.name}, resource={self.resource}, action={self.action})>"

    @classmethod
    def make_name(cls, resource: str, action: str) -> str:
        """Generate permission name from resource and action."""
        return f"{resource}:{action}"


class Role(Base):
    """
    Role model.

    Roles can be:
    - System roles (org_id is None): Available to all organizations
    - Organization roles (org_id is set): Custom roles for specific org
    """

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Nullable org_id means system role
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # System roles cannot be modified/deleted by users
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Role priority for display ordering
    priority: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="roles",
    )

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
    )

    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="role",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        scope = "system" if self.is_system else f"org:{self.org_id}"
        return f"<Role(name={self.name}, scope={scope})>"

    @property
    def is_organization_role(self) -> bool:
        """Check if this is an organization-specific role."""
        return self.org_id is not None

    def has_permission(self, permission_name: str) -> bool:
        """Check if this role has a specific permission."""
        return any(rp.permission.name == permission_name for rp in self.role_permissions)

    def get_permissions(self) -> list[str]:
        """Get list of permission names for this role."""
        return [rp.permission.name for rp in self.role_permissions]


class RolePermission(Base):
    """
    Role-Permission mapping table.

    Links roles to permissions (many-to-many).
    """

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Relationships
    role: Mapped["Role"] = relationship(
        "Role",
        back_populates="role_permissions",
    )

    permission: Mapped["Permission"] = relationship(
        "Permission",
        back_populates="role_permissions",
    )

    def __repr__(self) -> str:
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"


class UserRole(Base):
    """
    User-Role assignment table.

    Links users to roles (many-to-many).
    """

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Who assigned this role
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="user_roles",
        foreign_keys=[user_id],
    )

    role: Mapped["Role"] = relationship(
        "Role",
        back_populates="user_roles",
    )

    def __repr__(self) -> str:
        return f"<UserRole(user_id={self.user_id}, role_id={self.role_id})>"


# Re-exported from autobot_shared for backward compatibility.
# Single source of truth lives in autobot_shared.auth.permissions.
__all__ = [
    "SYSTEM_PERMISSIONS",
    "SYSTEM_ROLES",
]
