# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reconcile colon-style RBAC seed rows to the canonical dot vocabulary (#10458).

Follow-up of #10221 / PR #10455. PR #10455 made the code layer generate
``SYSTEM_PERMISSIONS`` / ``SYSTEM_ROLES`` from the canonical dot-style
``Permission`` enum / ``ROLE_PERMISSIONS`` (``autobot_shared/auth/permissions``).
Fresh installs now seed the dot vocabulary correctly, but databases already
seeded with the OLD colon-style rows (``users:read``, ``admin:access``,
``chat:use`` …) and the old three-role set (``admin``/``user``/``readonly`` —
no ``operator``/``analyst``/``editor``) need a one-time data reconciliation.

This is **seed-data reconciliation only** — runtime RBAC always used the dot
``ROLE_PERMISSIONS`` and was never broken (per #10221). The desired end-state is
the ``permissions``/``roles``/``role_permissions`` rows for the *system* set
(``roles.org_id IS NULL``) matching the canonical seed exactly.

Why a full rebuild rather than per-row renames
----------------------------------------------
The colon→dot map is many-to-one (``users:create`` / ``users:update`` /
``users:delete`` all fold into ``admin.users.write``; ``admin:access`` /
``admin:organization`` both fold into ``admin.system``). In-place UPDATE of
``permissions.name`` would collide on the unique ``name`` index. So we instead
(1) seed every canonical permission, (2) rebuild the system-role grants from the
canonical ``SYSTEM_ROLES`` map, then (3) drop obsolete colon-only permission
rows — ``role_permissions`` rows are removed first so none are orphaned.

The canonical permission / role definitions and the explicit legacy colon→dot
mapping are pinned literally below. Migrations are frozen history: they must not
import ``SYSTEM_PERMISSIONS`` / ``ROLE_PERMISSIONS`` from model code, because a
later edit to that enum would silently change what this revision does. The
literals here are derived from ``autobot_shared/auth/permissions.py`` as of
PR #10455 and the pre-#10455 colon seed (commit ``c1a6c133c^``).

Idempotency
-----------
Every step is existence-checked: missing tables short-circuit, INSERTs guard on
``WHERE NOT EXISTS``, grant rebuild is delete-then-insert scoped to system roles,
and obsolete-row deletion is a no-op when the colon rows are already gone. Safe
to run on a fresh dot-seeded DB, an un-migrated colon DB, or a half-migrated one.

Revision ID: 20260623_062
Revises: 20260621_061
Create Date: 2026-06-23
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_table

# revision identifiers, used by Alembic.
revision: str = "20260623_062"
down_revision: Union[str, None] = "20260621_061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Canonical permission catalogue — pinned literally (see module docstring).
# (name, resource, action, description). Mirrors _build_system_permissions()
# in autobot_shared/auth/permissions.py as of PR #10455. Descriptions match
# _perm_description(): "<Action> <resource>" for dot names; the single-segment
# allow_shell_execute degenerates to "Allow_shell_execute allow_shell_execute".
# ---------------------------------------------------------------------------
CANONICAL_PERMISSIONS: list[tuple[str, str, str, str]] = [
    ("api.read", "api", "read", "Read api"),
    ("api.write", "api", "write", "Write api"),
    ("api.admin", "api", "admin", "Admin api"),
    ("knowledge.read", "knowledge", "read", "Read knowledge"),
    ("knowledge.write", "knowledge", "write", "Write knowledge"),
    ("knowledge.delete", "knowledge", "delete", "Delete knowledge"),
    ("knowledge.manage", "knowledge", "manage", "Manage knowledge"),
    ("analytics.view", "analytics", "view", "View analytics"),
    ("analytics.export", "analytics", "export", "Export analytics"),
    ("analytics.manage", "analytics", "manage", "Manage analytics"),
    ("analytics.logs", "analytics", "logs", "Logs analytics"),
    ("agent.view", "agent", "view", "View agent"),
    ("agent.execute", "agent", "execute", "Execute agent"),
    ("agent.manage", "agent", "manage", "Manage agent"),
    ("agent.terminal", "agent", "terminal", "Terminal agent"),
    ("workflow.view", "workflow", "view", "View workflow"),
    ("workflow.create", "workflow", "create", "Create workflow"),
    ("workflow.execute", "workflow", "execute", "Execute workflow"),
    ("workflow.manage", "workflow", "manage", "Manage workflow"),
    ("files.view", "files", "view", "View files"),
    ("files.download", "files", "download", "Download files"),
    ("files.upload", "files", "upload", "Upload files"),
    ("files.delete", "files", "delete", "Delete files"),
    ("files.manage", "files", "manage", "Manage files"),
    ("security.view", "security", "view", "View security"),
    ("security.audit", "security", "audit", "Audit security"),
    ("security.manage", "security", "manage", "Manage security"),
    ("admin.users.read", "admin.users", "read", "Read admin.users"),
    ("admin.users.write", "admin.users", "write", "Write admin.users"),
    ("admin.config.read", "admin.config", "read", "Read admin.config"),
    ("admin.config.write", "admin.config", "write", "Write admin.config"),
    ("admin.system", "admin", "system", "System admin"),
    ("mcp.read", "mcp", "read", "Read mcp"),
    ("mcp.execute", "mcp", "execute", "Execute mcp"),
    ("mcp.manage", "mcp", "manage", "Manage mcp"),
    ("batch.view", "batch", "view", "View batch"),
    ("batch.create", "batch", "create", "Create batch"),
    ("batch.execute", "batch", "execute", "Execute batch"),
    ("batch.manage", "batch", "manage", "Manage batch"),
    ("sandbox.view", "sandbox", "view", "View sandbox"),
    ("sandbox.execute", "sandbox", "execute", "Execute sandbox"),
    ("sandbox.manage", "sandbox", "manage", "Manage sandbox"),
    ("service.management", "service", "management", "Management service"),
    ("allow_shell_execute", "allow_shell_execute", "allow_shell_execute", "Allow_shell_execute allow_shell_execute"),
    # Legacy colon-style secrets vault permissions (#10088) — retained verbatim
    # in the canonical seed because secrets_authz uses composite names that are
    # not representable in the dot-style enum.
    ("secrets:team:read", "secrets", "team:read", "Read team-vault secrets"),
    ("secrets:team:write", "secrets", "team:write", "Write team-vault secrets"),
    ("secrets:team:share", "secrets", "team:share", "Share team-vault secrets"),
    ("secrets:team:revoke", "secrets", "team:revoke", "Revoke team-vault secret grants"),
    ("secrets:role:read", "secrets", "role:read", "Read role-vault secrets"),
    ("secrets:role:write", "secrets", "role:write", "Write role-vault secrets"),
    ("secrets:role:share", "secrets", "role:share", "Share role-vault secrets"),
    ("secrets:role:revoke", "secrets", "role:revoke", "Revoke role-vault secret grants"),
]

# Canonical system roles — (name, description, priority). Mirrors _ROLE_META /
# _build_system_roles() in autobot_shared/auth/permissions.py as of PR #10455.
CANONICAL_ROLES: list[tuple[str, str, int]] = [
    ("admin", "Full administrative access", 100),
    ("operator", "Operator access for day-to-day service management", 80),
    ("analyst", "Analytics and read-heavy access", 60),
    ("editor", "Content and knowledge editing access", 55),
    ("user", "Standard user access", 50),
    ("readonly", "Read-only access", 10),
]

# Canonical role -> permission-name grants (system roles). Mirrors SYSTEM_ROLES
# (ROLE_PERMISSIONS + legacy secrets:* extras for admin/user).
CANONICAL_ROLE_GRANTS: dict[str, list[str]] = {
    "admin": [
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
        "service.management", "allow_shell_execute",
        "secrets:team:read", "secrets:team:write", "secrets:team:share", "secrets:team:revoke",
        "secrets:role:read", "secrets:role:write", "secrets:role:share", "secrets:role:revoke",
    ],
    "operator": [
        "api.read", "api.write",
        "knowledge.read", "knowledge.write",
        "analytics.view", "analytics.export",
        "agent.view", "agent.execute",
        "workflow.view", "workflow.create", "workflow.execute",
        "files.view", "files.download", "files.upload",
        "mcp.read", "mcp.execute",
        "batch.view", "batch.create", "batch.execute",
        "sandbox.view", "sandbox.execute",
        "service.management",
    ],
    "analyst": [
        "api.read", "knowledge.read",
        "analytics.view", "analytics.export", "analytics.logs",
        "agent.view", "workflow.view",
        "files.view", "files.download",
        "security.view", "mcp.read", "batch.view",
    ],
    "editor": [
        "api.read", "api.write",
        "knowledge.read", "knowledge.write",
        "analytics.view", "agent.view",
        "workflow.view", "workflow.create",
        "files.view", "files.download", "files.upload",
        "mcp.read", "batch.view", "batch.create",
    ],
    "user": [
        "api.read", "knowledge.read", "analytics.view",
        "agent.view", "workflow.view",
        "files.view", "files.download",
        "mcp.read", "batch.view",
        "secrets:team:read", "secrets:team:write", "secrets:role:read", "secrets:role:write",
    ],
    "readonly": [
        "api.read", "knowledge.read", "analytics.view",
        "agent.view", "workflow.view", "files.view",
    ],
}

# Explicit legacy colon -> canonical dot mapping (documented; many-to-one).
# Source: pre-#10455 colon SYSTEM_PERMISSIONS (commit c1a6c133c^). Only the
# genuinely colon-style names appear here; secrets:* and service.management were
# already canonical and are NOT remapped. teams:* and chat:* have no dedicated
# dot permission — they fold into the closest canonical capability so existing
# grants are preserved before the obsolete rows are dropped.
COLON_TO_DOT: dict[str, str] = {
    "users:read": "admin.users.read",
    "users:create": "admin.users.write",
    "users:update": "admin.users.write",
    "users:delete": "admin.users.write",
    "teams:read": "admin.users.read",
    "teams:create": "admin.users.write",
    "teams:manage": "admin.users.write",
    "teams:delete": "admin.users.write",
    "knowledge:read": "knowledge.read",
    "knowledge:write": "knowledge.write",
    "knowledge:delete": "knowledge.delete",
    "chat:use": "api.write",
    "chat:history": "api.read",
    "files:view": "files.view",
    "files:upload": "files.upload",
    "files:download": "files.download",
    "files:delete": "files.delete",
    "settings:read": "admin.config.read",
    "settings:write": "admin.config.write",
    "admin:access": "admin.system",
    "admin:users": "admin.users.write",
    "admin:organization": "admin.system",
    "audit:read": "security.audit",
    "audit:write": "security.manage",
}

# Obsolete colon-style permission rows to drop after grants are rebuilt. These
# are exactly the legacy colon names that are NOT part of the canonical seed
# (i.e. every COLON_TO_DOT key — secrets:* / service.management are excluded by
# construction because they are canonical and never appeared as map keys).
OBSOLETE_COLON_PERMISSIONS: list[str] = sorted(COLON_TO_DOT.keys())


def _new_id() -> str:
    """Fresh UUID string for a new primary-key row."""
    return str(uuid.uuid4())


def _tables_present() -> bool:
    """True only when all RBAC tables this migration touches exist."""
    return all(has_table(t) for t in ("permissions", "roles", "role_permissions"))


def _seed_permissions(bind: sa.engine.Connection) -> None:
    """Insert any canonical permission rows that are missing (idempotent)."""
    for name, resource, action, description in CANONICAL_PERMISSIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO permissions (id, name, resource, action, description, created_at, updated_at)
                SELECT :id, :name, :resource, :action, :description, now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = :name)
                """
            ),
            {
                "id": _new_id(),
                "name": name,
                "resource": resource,
                "action": action,
                "description": description,
            },
        )


def _seed_roles(bind: sa.engine.Connection) -> None:
    """Insert any canonical system roles that are missing (idempotent).

    System roles are identified by ``org_id IS NULL`` (per the Role model).
    """
    for name, description, priority in CANONICAL_ROLES:
        bind.execute(
            sa.text(
                """
                INSERT INTO roles (id, org_id, name, description, is_system, priority, created_at, updated_at)
                SELECT :id, NULL, :name, :description, true, :priority, now(), now()
                WHERE NOT EXISTS (
                    SELECT 1 FROM roles WHERE name = :name AND org_id IS NULL
                )
                """
            ),
            {
                "id": _new_id(),
                "name": name,
                "description": description,
                "priority": priority,
            },
        )


def _rebuild_system_role_grants(bind: sa.engine.Connection) -> None:
    """Rebuild role_permissions for system roles to match the canonical map.

    Delete-then-insert, scoped to system roles (``roles.org_id IS NULL``); org
    roles and their custom grants are untouched.
    """
    for role_name, perm_names in CANONICAL_ROLE_GRANTS.items():
        role_id = bind.execute(
            sa.text("SELECT id FROM roles WHERE name = :name AND org_id IS NULL LIMIT 1"),
            {"name": role_name},
        ).scalar()
        if role_id is None:
            continue  # role absent on this DB — nothing to grant
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE role_id = :role_id"),
            {"role_id": role_id},
        )
        for perm_name in perm_names:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT :role_id, p.id FROM permissions p
                    WHERE p.name = :perm_name
                      AND NOT EXISTS (
                          SELECT 1 FROM role_permissions rp
                          WHERE rp.role_id = :role_id AND rp.permission_id = p.id
                      )
                    """
                ),
                {"role_id": role_id, "perm_name": perm_name},
            )


def _drop_obsolete_colon_permissions(bind: sa.engine.Connection) -> None:
    """Remove obsolete colon permission rows and any leftover grants.

    The FK on ``role_permissions.permission_id`` is ``ON DELETE CASCADE``, but we
    delete the join rows explicitly first so the intent is clear and the step is
    safe regardless of FK configuration — no row is left orphaned.
    """
    for name in OBSOLETE_COLON_PERMISSIONS:
        bind.execute(
            sa.text(
                """
                DELETE FROM role_permissions
                WHERE permission_id IN (SELECT id FROM permissions WHERE name = :name)
                """
            ),
            {"name": name},
        )
        bind.execute(
            sa.text("DELETE FROM permissions WHERE name = :name"),
            {"name": name},
        )


def upgrade() -> None:
    if not _tables_present():
        return  # RBAC tables not provisioned on this DB — nothing to reconcile
    bind = op.get_bind()
    _seed_permissions(bind)
    _seed_roles(bind)
    _rebuild_system_role_grants(bind)
    _drop_obsolete_colon_permissions(bind)


# ---------------------------------------------------------------------------
# Downgrade — best-effort reverse to the pre-#10455 colon seed.
# ---------------------------------------------------------------------------
# Pre-#10455 colon permission catalogue: (name, resource, action, description).
LEGACY_COLON_PERMISSIONS: list[tuple[str, str, str, str]] = [
    ("users:read", "users", "read", "View users"),
    ("users:create", "users", "create", "Create users"),
    ("users:update", "users", "update", "Update users"),
    ("users:delete", "users", "delete", "Delete users"),
    ("teams:read", "teams", "read", "View teams"),
    ("teams:create", "teams", "create", "Create teams"),
    ("teams:manage", "teams", "manage", "Manage team members"),
    ("teams:delete", "teams", "delete", "Delete teams"),
    ("knowledge:read", "knowledge", "read", "View knowledge base"),
    ("knowledge:write", "knowledge", "write", "Add/edit knowledge"),
    ("knowledge:delete", "knowledge", "delete", "Delete knowledge entries"),
    ("chat:use", "chat", "use", "Use chat functionality"),
    ("chat:history", "chat", "history", "View chat history"),
    ("files:view", "files", "view", "View files"),
    ("files:upload", "files", "upload", "Upload files"),
    ("files:download", "files", "download", "Download files"),
    ("files:delete", "files", "delete", "Delete files"),
    ("settings:read", "settings", "read", "View settings"),
    ("settings:write", "settings", "write", "Modify settings"),
    ("admin:access", "admin", "access", "Access admin panel"),
    ("admin:users", "admin", "users", "Manage all users"),
    ("admin:organization", "admin", "organization", "Manage organization"),
    ("audit:read", "audit", "read", "View audit logs"),
    ("audit:write", "audit", "write", "Manage audit logs (cleanup)"),
]

# Pre-#10455 colon role grants (admin/user/readonly only; the colon seed had no
# operator/analyst/editor). Source: SYSTEM_ROLES at commit c1a6c133c^.
LEGACY_ROLE_GRANTS: dict[str, list[str]] = {
    "admin": [
        "users:read", "users:create", "users:update", "users:delete",
        "teams:read", "teams:create", "teams:manage", "teams:delete",
        "knowledge:read", "knowledge:write", "knowledge:delete",
        "chat:use", "chat:history",
        "files:view", "files:upload", "files:download", "files:delete",
        "settings:read", "settings:write",
        "admin:access", "admin:users", "admin:organization",
        "audit:read", "audit:write",
        "secrets:team:read", "secrets:team:write", "secrets:team:share", "secrets:team:revoke",
        "secrets:role:read", "secrets:role:write", "secrets:role:share", "secrets:role:revoke",
        "service.management",
    ],
    "user": [
        "users:read", "teams:read",
        "knowledge:read", "knowledge:write",
        "chat:use", "chat:history",
        "files:view", "files:upload", "files:download",
        "settings:read",
        "secrets:team:read", "secrets:team:write", "secrets:role:read", "secrets:role:write",
    ],
    "readonly": [
        "users:read", "teams:read", "knowledge:read", "chat:history",
        "files:view", "files:download", "settings:read",
    ],
}

# Dot permissions that existed only in the canonical (post-#10455) seed and were
# never part of the colon seed — removed on downgrade. (Every CANONICAL_PERMISSIONS
# name except the secrets:* legacy rows, which predate #10455 and stay.)
_CANONICAL_ONLY_DOT_PERMISSIONS: list[str] = [
    name for (name, _r, _a, _d) in CANONICAL_PERMISSIONS if not name.startswith("secrets:")
]


def downgrade() -> None:
    """Best-effort restore of the pre-#10455 colon seed.

    Re-seeds the colon permissions, rebuilds admin/user/readonly grants to the
    colon set, then drops the operator/analyst/editor roles and the canonical-only
    dot permission rows. Custom (org-scoped) roles are never touched. Idempotent
    and guarded the same way as upgrade.
    """
    if not _tables_present():
        return
    bind = op.get_bind()

    # 1. Re-seed legacy colon permissions (service.management / secrets:* already present).
    for name, resource, action, description in LEGACY_COLON_PERMISSIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO permissions (id, name, resource, action, description, created_at, updated_at)
                SELECT :id, :name, :resource, :action, :description, now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = :name)
                """
            ),
            {
                "id": _new_id(),
                "name": name,
                "resource": resource,
                "action": action,
                "description": description,
            },
        )

    # 2. Rebuild admin/user/readonly grants to the colon set.
    for role_name, perm_names in LEGACY_ROLE_GRANTS.items():
        role_id = bind.execute(
            sa.text("SELECT id FROM roles WHERE name = :name AND org_id IS NULL LIMIT 1"),
            {"name": role_name},
        ).scalar()
        if role_id is None:
            continue
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE role_id = :role_id"),
            {"role_id": role_id},
        )
        for perm_name in perm_names:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT :role_id, p.id FROM permissions p
                    WHERE p.name = :perm_name
                      AND NOT EXISTS (
                          SELECT 1 FROM role_permissions rp
                          WHERE rp.role_id = :role_id AND rp.permission_id = p.id
                      )
                    """
                ),
                {"role_id": role_id, "perm_name": perm_name},
            )

    # 3. Drop the roles the colon seed never had (cascades their grants).
    for role_name in ("operator", "analyst", "editor"):
        role_id = bind.execute(
            sa.text("SELECT id FROM roles WHERE name = :name AND org_id IS NULL LIMIT 1"),
            {"name": role_name},
        ).scalar()
        if role_id is None:
            continue
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE role_id = :role_id"),
            {"role_id": role_id},
        )
        bind.execute(
            sa.text("DELETE FROM roles WHERE id = :role_id"),
            {"role_id": role_id},
        )

    # 4. Drop canonical-only dot permission rows (grants removed first).
    for name in _CANONICAL_ONLY_DOT_PERMISSIONS:
        bind.execute(
            sa.text(
                """
                DELETE FROM role_permissions
                WHERE permission_id IN (SELECT id FROM permissions WHERE name = :name)
                """
            ),
            {"name": name},
        )
        bind.execute(
            sa.text("DELETE FROM permissions WHERE name = :name"),
            {"name": name},
        )
