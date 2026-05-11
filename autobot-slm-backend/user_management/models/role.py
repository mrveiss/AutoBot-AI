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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user_management.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from user_management.models.organization import Organization
    from user_management.models.user import User


class Permission(Base, TimestampMixin):
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
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    description: Mapped[Optional[str]] = mapped_column(
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


class Role(Base, TimestampMixin):
    """
    Role model.

    Roles can be:
    - System roles (org_id is None): Available to all organizations
    - Organization roles (org_id is set): Custom roles for specific org
    """

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Nullable org_id means system role
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[Optional[str]] = mapped_column(
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
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
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


class UserRole(Base, TimestampMixin):
    """
    User-Role assignment table.

    Links users to roles (many-to-many).
    """

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Who assigned this role
    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
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


# Default system permissions — names use the canonical dot-notation from
# autobot_shared.auth.permissions.Permission (GH #6511).
# Old colon-notation aliases are kept for backward compatibility so that
# existing DB rows remain valid; new code must use the dot-notation values.
SYSTEM_PERMISSIONS = [
    # User / admin management
    ("admin.users.read", "admin.users", "read", "View users"),
    ("admin.users.write", "admin.users", "write", "Create/update/delete users"),
    ("admin.config.read", "admin.config", "read", "View configuration"),
    ("admin.config.write", "admin.config", "write", "Modify configuration"),
    ("admin.system", "admin", "system", "Full system administration"),
    # Team management
    ("teams.read", "teams", "read", "View teams"),
    ("teams.create", "teams", "create", "Create teams"),
    ("teams.manage", "teams", "manage", "Manage team members"),
    ("teams.delete", "teams", "delete", "Delete teams"),
    # Knowledge base
    ("knowledge.read", "knowledge", "read", "View knowledge base"),
    ("knowledge.write", "knowledge", "write", "Add/edit knowledge"),
    ("knowledge.delete", "knowledge", "delete", "Delete knowledge entries"),
    ("knowledge.manage", "knowledge", "manage", "Manage knowledge base"),
    # Analytics
    ("analytics.view", "analytics", "view", "View analytics"),
    ("analytics.export", "analytics", "export", "Export analytics data"),
    ("analytics.manage", "analytics", "manage", "Manage analytics"),
    ("analytics.logs", "analytics", "logs", "View analytics logs"),
    # Agents
    ("agent.view", "agent", "view", "View agents"),
    ("agent.execute", "agent", "execute", "Execute agents"),
    ("agent.manage", "agent", "manage", "Manage agents"),
    ("agent.terminal", "agent", "terminal", "Agent terminal access"),
    # Workflows
    ("workflow.view", "workflow", "view", "View workflows"),
    ("workflow.create", "workflow", "create", "Create workflows"),
    ("workflow.execute", "workflow", "execute", "Execute workflows"),
    ("workflow.manage", "workflow", "manage", "Manage workflows"),
    # Chat
    ("chat.use", "chat", "use", "Use chat functionality"),
    ("chat.history", "chat", "history", "View chat history"),
    # Files
    ("files.view", "files", "view", "View files"),
    ("files.upload", "files", "upload", "Upload files"),
    ("files.download", "files", "download", "Download files"),
    ("files.delete", "files", "delete", "Delete files"),
    ("files.manage", "files", "manage", "Manage files"),
    # Settings
    ("settings.read", "settings", "read", "View settings"),
    ("settings.write", "settings", "write", "Modify settings"),
    # Security
    ("security.view", "security", "view", "View security information"),
    ("security.audit", "security", "audit", "View security audit"),
    ("security.manage", "security", "manage", "Manage security"),
    # API
    ("api.read", "api", "read", "API read access"),
    ("api.write", "api", "write", "API write access"),
    ("api.admin", "api", "admin", "API admin access"),
    # MCP
    ("mcp.read", "mcp", "read", "MCP read access"),
    ("mcp.execute", "mcp", "execute", "MCP execute access"),
    ("mcp.manage", "mcp", "manage", "Manage MCP"),
    # Batch
    ("batch.view", "batch", "view", "View batch jobs"),
    ("batch.create", "batch", "create", "Create batch jobs"),
    ("batch.execute", "batch", "execute", "Execute batch jobs"),
    ("batch.manage", "batch", "manage", "Manage batch jobs"),
    # Sandbox
    ("sandbox.view", "sandbox", "view", "View sandbox"),
    ("sandbox.execute", "sandbox", "execute", "Execute in sandbox"),
    ("sandbox.manage", "sandbox", "manage", "Manage sandbox"),
    # Audit logs
    ("audit.read", "audit", "read", "View audit logs"),
    ("audit.write", "audit", "write", "Manage audit logs (cleanup)"),
    # Shell (dangerous)
    ("allow_shell_execute", "shell", "execute", "Execute shell commands"),
]

# Default system roles with their permissions (GH #6511: aligned with
# autobot_shared.auth.permissions.ROLE_PERMISSIONS).
SYSTEM_ROLES = {
    "admin": {
        "description": "Full administrative access",
        "priority": 100,
        "permissions": [
            "api.read", "api.write", "api.admin",
            "knowledge.read", "knowledge.write", "knowledge.delete", "knowledge.manage",
            "analytics.view", "analytics.export", "analytics.manage", "analytics.logs",
            "agent.view", "agent.execute", "agent.manage", "agent.terminal",
            "workflow.view", "workflow.create", "workflow.execute", "workflow.manage",
            "files.view", "files.download", "files.upload", "files.delete", "files.manage",
            "security.view", "security.audit", "security.manage",
            "admin.users.read", "admin.users.write", "admin.config.read", "admin.config.write", "admin.system",
            "mcp.read", "mcp.execute", "mcp.manage",
            "batch.view", "batch.create", "batch.execute", "batch.manage",
            "sandbox.view", "sandbox.execute", "sandbox.manage",
            "chat.use", "chat.history",
            "teams.read", "teams.create", "teams.manage", "teams.delete",
            "audit.read", "audit.write",
            "settings.read", "settings.write",
            "allow_shell_execute",
        ],
    },
    "operator": {
        "description": "Operator — can execute but not manage",
        "priority": 75,
        "permissions": [
            "api.read", "api.write",
            "knowledge.read", "knowledge.write",
            "analytics.view", "analytics.export",
            "agent.view", "agent.execute",
            "workflow.view", "workflow.create", "workflow.execute",
            "files.view", "files.download", "files.upload",
            "mcp.read", "mcp.execute",
            "batch.view", "batch.create", "batch.execute",
            "sandbox.view", "sandbox.execute",
            "chat.use", "chat.history",
            "teams.read",
            "settings.read",
        ],
    },
    "analyst": {
        "description": "Analyst — read/view + analytics export",
        "priority": 60,
        "permissions": [
            "api.read",
            "knowledge.read",
            "analytics.view", "analytics.export", "analytics.logs",
            "agent.view",
            "workflow.view",
            "files.view", "files.download",
            "security.view",
            "mcp.read",
            "batch.view",
            "chat.history",
            "audit.read",
            "settings.read",
        ],
    },
    "editor": {
        "description": "Editor — create and modify content",
        "priority": 65,
        "permissions": [
            "api.read", "api.write",
            "knowledge.read", "knowledge.write",
            "analytics.view",
            "agent.view",
            "workflow.view", "workflow.create",
            "files.view", "files.download", "files.upload",
            "mcp.read",
            "batch.view", "batch.create",
            "chat.use", "chat.history",
            "settings.read",
        ],
    },
    "user": {
        "description": "Standard user access",
        "priority": 50,
        "permissions": [
            "api.read",
            "knowledge.read", "knowledge.write",
            "analytics.view",
            "agent.view",
            "workflow.view",
            "files.view", "files.download", "files.upload",
            "mcp.read",
            "batch.view",
            "chat.use", "chat.history",
            "teams.read",
            "settings.read",
        ],
    },
    "readonly": {
        "description": "Read-only access",
        "priority": 10,
        "permissions": [
            "api.read",
            "knowledge.read",
            "analytics.view",
            "agent.view",
            "workflow.view",
            "files.view", "files.download",
            "chat.history",
            "teams.read",
            "settings.read",
        ],
    },
    # Issue #744: Guest role REMOVED - security vulnerability
    # Unauthenticated requests must be rejected, not assigned guest permissions
}
