# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Canonical Permission/Role definitions for AutoBot (#6511).

Single source of truth for all permission names and role-to-permission mappings
shared by autobot-backend and autobot-slm-backend.  Before this module existed,
``Permission`` and ``Role`` lived only in ``autobot-backend/auth_rbac.py``; the
SLM backend used bare permission strings from the database that were never
cross-checked against the main backend's enum values, creating security drift.

Adding a new permission
-----------------------
1. Add a member to ``Permission`` here.
2. Grant it to the appropriate roles in ``ROLE_PERMISSIONS``.
3. Both backends automatically see the change on next deploy — no second edit.

Removing or renaming a permission
----------------------------------
Search for callers of the old name across both backends before deleting.
"""

from enum import Enum
from typing import Dict, List


class Permission(str, Enum):
    """All API permissions in the system.

    Naming convention: CATEGORY_RESOURCE_ACTION
    - CATEGORY: functional area (API, KNOWLEDGE, ANALYTICS, …)
    - RESOURCE: specific resource being accessed
    - ACTION: READ, WRITE, EXECUTE, DELETE, MANAGE
    """

    # === API Core ===
    API_READ = "api.read"
    API_WRITE = "api.write"
    API_ADMIN = "api.admin"

    # === Knowledge Base ===
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_WRITE = "knowledge.write"
    KNOWLEDGE_DELETE = "knowledge.delete"
    KNOWLEDGE_MANAGE = "knowledge.manage"

    # === Analytics ===
    ANALYTICS_VIEW = "analytics.view"
    ANALYTICS_EXPORT = "analytics.export"
    ANALYTICS_MANAGE = "analytics.manage"
    ANALYTICS_LOGS = "analytics.logs"

    # === Agent ===
    AGENT_VIEW = "agent.view"
    AGENT_EXECUTE = "agent.execute"
    AGENT_MANAGE = "agent.manage"
    AGENT_TERMINAL = "agent.terminal"

    # === Workflow ===
    WORKFLOW_VIEW = "workflow.view"
    WORKFLOW_CREATE = "workflow.create"
    WORKFLOW_EXECUTE = "workflow.execute"
    WORKFLOW_MANAGE = "workflow.manage"

    # === File Operations ===
    FILES_VIEW = "files.view"
    FILES_DOWNLOAD = "files.download"
    FILES_UPLOAD = "files.upload"
    FILES_DELETE = "files.delete"
    FILES_MANAGE = "files.manage"

    # === Security ===
    SECURITY_VIEW = "security.view"
    SECURITY_AUDIT = "security.audit"
    SECURITY_MANAGE = "security.manage"

    # === System Administration ===
    ADMIN_USERS_READ = "admin.users.read"
    ADMIN_USERS_WRITE = "admin.users.write"
    ADMIN_CONFIG_READ = "admin.config.read"
    ADMIN_CONFIG_WRITE = "admin.config.write"
    ADMIN_SYSTEM = "admin.system"

    # === MCP (Model Context Protocol) ===
    MCP_READ = "mcp.read"
    MCP_EXECUTE = "mcp.execute"
    MCP_MANAGE = "mcp.manage"

    # === Batch Jobs ===
    BATCH_VIEW = "batch.view"
    BATCH_CREATE = "batch.create"
    BATCH_EXECUTE = "batch.execute"
    BATCH_MANAGE = "batch.manage"

    # === Sandbox ===
    SANDBOX_VIEW = "sandbox.view"
    SANDBOX_EXECUTE = "sandbox.execute"
    SANDBOX_MANAGE = "sandbox.manage"

    # === Service Lifecycle Manager ===
    SERVICE_MANAGEMENT = "service.management"

    # === Shell Execution (dangerous — no single-user bypass allowed) ===
    SHELL_EXECUTE = "allow_shell_execute"


class Role(str, Enum):
    """Standard roles in the AutoBot system."""

    ADMIN = "admin"
    OPERATOR = "operator"
    ANALYST = "analyst"
    EDITOR = "editor"
    USER = "user"
    READONLY = "readonly"


# Canonical role-to-permission mappings.
# Both autobot-backend (auth_rbac.py) and autobot-slm-backend import this dict
# so that a permission added here is enforced by both services automatically.
ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.ADMIN: [
        Permission.API_READ,
        Permission.API_WRITE,
        Permission.API_ADMIN,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.KNOWLEDGE_DELETE,
        Permission.KNOWLEDGE_MANAGE,
        Permission.ANALYTICS_VIEW,
        Permission.ANALYTICS_EXPORT,
        Permission.ANALYTICS_MANAGE,
        Permission.ANALYTICS_LOGS,
        Permission.AGENT_VIEW,
        Permission.AGENT_EXECUTE,
        Permission.AGENT_MANAGE,
        Permission.AGENT_TERMINAL,
        Permission.WORKFLOW_VIEW,
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_EXECUTE,
        Permission.WORKFLOW_MANAGE,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.FILES_UPLOAD,
        Permission.FILES_DELETE,
        Permission.FILES_MANAGE,
        Permission.SECURITY_VIEW,
        Permission.SECURITY_AUDIT,
        Permission.SECURITY_MANAGE,
        Permission.ADMIN_USERS_READ,
        Permission.ADMIN_USERS_WRITE,
        Permission.ADMIN_CONFIG_READ,
        Permission.ADMIN_CONFIG_WRITE,
        Permission.ADMIN_SYSTEM,
        Permission.MCP_READ,
        Permission.MCP_EXECUTE,
        Permission.MCP_MANAGE,
        Permission.BATCH_VIEW,
        Permission.BATCH_CREATE,
        Permission.BATCH_EXECUTE,
        Permission.BATCH_MANAGE,
        Permission.SANDBOX_VIEW,
        Permission.SANDBOX_EXECUTE,
        Permission.SANDBOX_MANAGE,
        Permission.SERVICE_MANAGEMENT,
        Permission.SHELL_EXECUTE,
    ],
    Role.OPERATOR: [
        Permission.API_READ,
        Permission.API_WRITE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.ANALYTICS_VIEW,
        Permission.ANALYTICS_EXPORT,
        Permission.AGENT_VIEW,
        Permission.AGENT_EXECUTE,
        Permission.WORKFLOW_VIEW,
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_EXECUTE,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.FILES_UPLOAD,
        Permission.MCP_READ,
        Permission.MCP_EXECUTE,
        Permission.BATCH_VIEW,
        Permission.BATCH_CREATE,
        Permission.BATCH_EXECUTE,
        Permission.SANDBOX_VIEW,
        Permission.SANDBOX_EXECUTE,
        Permission.SERVICE_MANAGEMENT,
    ],
    Role.ANALYST: [
        Permission.API_READ,
        Permission.KNOWLEDGE_READ,
        Permission.ANALYTICS_VIEW,
        Permission.ANALYTICS_EXPORT,
        Permission.ANALYTICS_LOGS,
        Permission.AGENT_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.SECURITY_VIEW,
        Permission.MCP_READ,
        Permission.BATCH_VIEW,
    ],
    Role.EDITOR: [
        Permission.API_READ,
        Permission.API_WRITE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.ANALYTICS_VIEW,
        Permission.AGENT_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.WORKFLOW_CREATE,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.FILES_UPLOAD,
        Permission.MCP_READ,
        Permission.BATCH_VIEW,
        Permission.BATCH_CREATE,
    ],
    Role.USER: [
        Permission.API_READ,
        Permission.KNOWLEDGE_READ,
        Permission.ANALYTICS_VIEW,
        Permission.AGENT_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.MCP_READ,
        Permission.BATCH_VIEW,
    ],
    Role.READONLY: [
        Permission.API_READ,
        Permission.KNOWLEDGE_READ,
        Permission.ANALYTICS_VIEW,
        Permission.AGENT_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.FILES_VIEW,
    ],
}


# ---------------------------------------------------------------------------
# DB seeding helpers — generated from canonical sources above so a single edit
# to Permission / ROLE_PERMISSIONS propagates automatically to both.
# ---------------------------------------------------------------------------

# Legacy colon-style secrets vault permissions required by secrets_authz policy
# (#10088).  Not represented in the Permission enum (colon composite names) but
# must appear in SYSTEM_PERMISSIONS and relevant SYSTEM_ROLES entries.
_SECRETS_VAULT_LEGACY: List[tuple] = [
    ("secrets:team:read", "secrets", "team:read", "Read team-vault secrets"),
    ("secrets:team:write", "secrets", "team:write", "Write team-vault secrets"),
    ("secrets:team:share", "secrets", "team:share", "Share team-vault secrets"),
    ("secrets:team:revoke", "secrets", "team:revoke", "Revoke team-vault secret grants"),
    ("secrets:role:read", "secrets", "role:read", "Read role-vault secrets"),
    ("secrets:role:write", "secrets", "role:write", "Write role-vault secrets"),
    ("secrets:role:share", "secrets", "role:share", "Share role-vault secrets"),
    ("secrets:role:revoke", "secrets", "role:revoke", "Revoke role-vault secret grants"),
]

_SECRETS_ADMIN_PERMS: List[str] = [row[0] for row in _SECRETS_VAULT_LEGACY]
_SECRETS_USER_PERMS: List[str] = [
    "secrets:team:read",
    "secrets:team:write",
    "secrets:role:read",
    "secrets:role:write",
]


def _perm_description(perm: Permission) -> str:
    """Generate a human-readable description from a dot-style permission value."""
    parts = perm.value.split(".")
    resource = ".".join(parts[:-1]) if len(parts) > 1 else perm.value
    action = parts[-1] if len(parts) > 1 else perm.value
    return f"{action.capitalize()} {resource}"


def _build_system_permissions() -> List[tuple]:
    """Generate SYSTEM_PERMISSIONS from the canonical Permission enum.

    Each entry: (name, resource, action, description).
    The 'name' field equals the Permission enum value (dot-style), making it
    the primary key used by DB seeding and parity tests.  Legacy colon-style
    secrets:* entries are appended because the secrets_authz policy uses names
    not representable in the dot-style enum (#10088).
    """
    rows: List[tuple] = []
    for perm in Permission:
        parts = perm.value.split(".")
        resource = ".".join(parts[:-1]) if len(parts) > 1 else perm.value
        action = parts[-1] if len(parts) > 1 else perm.value
        rows.append((perm.value, resource, action, _perm_description(perm)))
    rows.extend(_SECRETS_VAULT_LEGACY)
    return rows


_ROLE_META: Dict[Role, Dict] = {
    Role.ADMIN: {"description": "Full administrative access", "priority": 100},
    Role.OPERATOR: {"description": "Operator access for day-to-day service management", "priority": 80},
    Role.ANALYST: {"description": "Analytics and read-heavy access", "priority": 60},
    Role.EDITOR: {"description": "Content and knowledge editing access", "priority": 55},
    Role.USER: {"description": "Standard user access", "priority": 50},
    Role.READONLY: {"description": "Read-only access", "priority": 10},
}


def _build_system_roles() -> Dict[str, Dict]:
    """Generate SYSTEM_ROLES from ROLE_PERMISSIONS.

    Each role entry carries every dot-style permission from ROLE_PERMISSIONS plus
    the legacy colon-style secrets:* permissions required by secrets_authz (#10088).
    Priority and description come from _ROLE_META.
    """
    result: Dict[str, Dict] = {}
    for role, perms in ROLE_PERMISSIONS.items():
        dot_perms = [p.value if isinstance(p, Permission) else p for p in perms]
        if role is Role.ADMIN:
            extra = _SECRETS_ADMIN_PERMS
        elif role is Role.USER:
            extra = _SECRETS_USER_PERMS
        else:
            extra = []
        meta = _ROLE_META.get(role, {"description": role.value, "priority": 0})
        result[role.value] = {
            "description": meta["description"],
            "priority": meta["priority"],
            "permissions": dot_perms + extra,
        }
    return result


# Default system permissions for database seeding — generated from the canonical
# Permission enum so it is always in sync.  Tuple layout: (name, resource, action, description).
SYSTEM_PERMISSIONS: List[tuple] = _build_system_permissions()

# Default system roles with their permissions for database seeding — generated
# from ROLE_PERMISSIONS so a single edit propagates here automatically.
# Issue #744: Guest role REMOVED — security vulnerability; unauthenticated
# requests must be rejected, not assigned guest permissions.
SYSTEM_ROLES: Dict[str, Dict] = _build_system_roles()
