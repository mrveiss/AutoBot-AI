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

    # === MCP bridges with no home in the categories above (#13228) ===
    # MCP tool access was governed by a substring blocklist of seven Redis
    # command names — default-allow, so every tool on every other bridge was
    # reachable by role="user". These give the remaining bridges a real
    # permission each, split read/execute so a browser *observation* and a
    # browser *click* are not the same grant.
    #
    # filesystem/knowledge/thinking bridges are NOT here: they map onto the
    # existing FILES_*, KNOWLEDGE_* and AGENT_EXECUTE members.
    MCP_BROWSER_READ = "mcp.browser.read"
    MCP_BROWSER_CONTROL = "mcp.browser.control"
    MCP_DATABASE_READ = "mcp.database.read"
    MCP_DATABASE_WRITE = "mcp.database.write"
    MCP_GIT_READ = "mcp.git.read"
    MCP_HTTP_READ = "mcp.http.read"
    MCP_HTTP_WRITE = "mcp.http.write"
    MCP_METRICS_READ = "mcp.metrics.read"
    MCP_DESKTOP_READ = "mcp.desktop.read"
    MCP_DESKTOP_CONTROL = "mcp.desktop.control"

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
    """Platform RBAC roles — the vocabulary that answers "what may this account do?".

    This is one of **three** unrelated vocabularies in the codebase that use the
    word "role", and they share string values with nothing at the type level
    keeping them apart (#14024). They are correctly separate concepts and are
    deliberately **not** merged; the hazard is that a value from the wrong one
    type-checks, passes tests, and reads correctly at a glance:

    ===================== ============================================= =========================================
    vocabulary            defined in                                    members
    ===================== ============================================= =========================================
    platform RBAC (here)  ``autobot_shared.auth.permissions.Role``      admin, superadmin, operator, analyst,
                                                                        editor, user, readonly
    company membership    ``llc.models.enums.MembershipRole``           owner, admin, member, guest, lead
    chat message role     ``ssot_constants.CategoryDefaults.ROLE_*``    user, assistant, system
    ===================== ============================================= =========================================

    Shared literals: ``"admin"`` with ``MembershipRole``, ``"user"`` with the
    chat constants. ``roles_do_not_collide_test.py`` asserts that overlap is
    exactly this and fails when a new value collides.

    Never substitute across the three. ``tools/tool_registry`` nearly tied an
    authorization decision to ``CategoryDefaults.ROLE_USER`` — a presentation
    constant that merely happens to hold ``"user"`` too (#13934).

    ``SUPERADMIN`` (#13854/#12786) is administrative — it is admitted by
    ``require_role`` at 17 endpoints and by :func:`is_admin_role` — and holds
    **no** granular permissions. See ``ROLE_PERMISSIONS`` for why.
    """

    ADMIN = "admin"
    SUPERADMIN = "superadmin"
    OPERATOR = "operator"
    ANALYST = "analyst"
    EDITOR = "editor"
    USER = "user"
    READONLY = "readonly"


# The roles that answer "is this role administrative?" -- declared as *enum
# members*, not as loose strings (#13854).
#
# It used to be ``frozenset({"admin", "superadmin"})``, a literal set naming a
# role that was not in the enum above. That shape had a specific hazard, named
# on #13854: because ``role_has_permission`` short-circuited on it, **adding a
# member to this frozenset silently granted that member every permission in the
# system**, shell execution included, with no edit to ROLE_PERMISSIONS and no
# review of the security layer. A predicate ("is this administrative?") was
# doubling as a permission source, which is not what it is for.
#
# Deriving it from the enum closes that structurally. A role cannot be named
# here unless it is a Role member, and a Role member cannot exist without a
# ROLE_PERMISSIONS entry (asserted by ``test_permission_parity`` and by
# ``roles_are_canonical_test``), so its grants are always written down in the
# one place a reader looks -- and adding one is an edit a reviewer sees.
#
# This lives here rather than in autobot-backend's auth_rbac because that module
# imports auth_middleware, which needs this answer too -- importing it back the
# other way closes a cycle (#12786).
_ADMINISTRATIVE_ROLES: frozenset = frozenset({Role.ADMIN, Role.SUPERADMIN})

# The string form, for the many callers that hold a raw role string. Derived, so
# the two can never drift.
ADMIN_ROLES: frozenset = frozenset(role.value for role in _ADMINISTRATIVE_ROLES)


def role_value(role: "Role | str | None") -> str:
    """The role string *role* denotes -- the one safe way to stringify a role (#14944).

    Every role lookup in this codebase keys on a string, and every one of them
    used to reach that string with ``str(role)``. For a ``(str, Enum)`` mixin
    that is **wrong**::

        str(Role.ADMIN)   == "Role.ADMIN"     # Enum.__str__ wins
        f"{Role.ADMIN}"   == "admin"          # mixin __format__ uses the value
        Role.ADMIN        == "admin"          # str.__eq__ -- True
        Role.ADMIN in ADMIN_ROLES             # True

    So a member behaves like its value under ``==``, under ``in``, and in an
    f-string, and *only* ``str()`` disagrees -- which is why every role resolver
    picked the one spelling that fails, and why nothing noticed. Note this is
    **not** fixed by a newer Python: ``enum.StrEnum`` (3.11+) would return the
    value, but ``Role`` is the ``(str, Enum)`` mixin shape, which keeps
    ``Enum.__str__``.

    Deliberately does **not** change case or strip whitespace. Callers differ --
    ``is_admin_role`` lowercases, ``canonical_role_permissions`` strips *and*
    lowercases -- and #13820 showed that applying a normalisation to one role
    source and not another creates a second identity for the same role that
    holds some grants and not others. This helper fixes the type coercion only;
    each caller keeps the normalisation it already had.

    A member of a **different** enum is rejected rather than coerced, and that is
    the point of doing this by ``isinstance`` rather than by ``.lower()``.
    ``MembershipRole`` and the chat-role constants share literals with this
    vocabulary (#14024, #13934), and every one of them is also a ``str``
    subclass -- so the obvious "fix", ``role.lower()``, quietly returns
    ``"admin"`` for ``MembershipRole.ADMIN`` and would admit a *company*
    membership role as a *platform* administrator. ``str()`` happened to reject
    that by accident; this rejects it on purpose, and loudly.

    A non-role type is likewise a programming error, not data: every caller
    passes a ``str`` or ``None`` off an authenticated session. Returning False
    for an object nobody meant to pass would answer an authorization question
    that was never asked.
    """
    if role is None:
        return ""
    if isinstance(role, Role):
        return role.value
    if isinstance(role, Enum):
        raise TypeError(
            f"{type(role).__name__}.{role.name} is not a platform role -- "
            f"autobot_shared.auth.permissions.Role is the platform RBAC vocabulary (#14024)"
        )
    if isinstance(role, str):
        return role
    raise TypeError(f"role must be a Role, str or None, not {type(role).__name__}")


def is_admin_role(role: "Role | str | None") -> bool:
    """Return True when *role* is administrative (admin or superadmin).

    Use this instead of ``role == "admin"`` for imperative checks that cannot
    use the require_role() dependency -- e.g. helpers that must also permit
    self-access, or that pass an ``is_admin`` flag further down.

    Case-insensitive, matching require_role(), which lowercases both sides.

    Accepts a ``Role`` member as well as a raw string (#14944). It previously
    called ``str(role)``, which yields ``"Role.ADMIN"`` for a member and so
    reported an administrator as non-administrative -- a failure in the unsafe
    direction, because ``api/user_management/users.py`` and ``llc/api/companies.py``
    feed the result into an ``is_platform_admin`` flag passed further down.
    ``require_role`` already guarded this case; this closes the asymmetry.

    Raises ``TypeError`` for anything that is neither -- see :func:`role_value`.
    """
    return role_value(role).lower() in ADMIN_ROLES


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
        # #13228: per-bridge MCP grants — mirrors this role's MCP_READ/MCP_EXECUTE level.
        Permission.MCP_BROWSER_READ,
        Permission.MCP_DATABASE_READ,
        Permission.MCP_GIT_READ,
        Permission.MCP_HTTP_READ,
        Permission.MCP_METRICS_READ,
        Permission.MCP_DESKTOP_READ,
        Permission.MCP_BROWSER_CONTROL,
        Permission.MCP_DATABASE_WRITE,
        Permission.MCP_HTTP_WRITE,
        Permission.MCP_DESKTOP_CONTROL,
    ],
    # superadmin holds NO granular permissions. This is deliberate, it is the
    # decision #13854 asked for, and it is written as an explicit empty entry
    # rather than an omission so that a reader who looks here finds an answer
    # instead of a gap (#13854, #12786).
    #
    # What superadmin IS: an administrative *predicate*. It is admitted by
    # ``require_role("admin", "superadmin")`` at 17 endpoints and by
    # ``is_admin_role`` at the imperative checks that cannot use a dependency.
    # Those are unchanged by this entry.
    #
    # What it is NOT: a permission holder. Granting it admin's set would have
    # added 54 permissions — ``admin.system``, ``security.manage``,
    # ``admin.users.write`` and ``allow_shell_execute`` among them — none of
    # which it held through the SecurityLayer gate before. #13820 measured that
    # expansion and refused to let it ride along inside a resolver fix; nothing
    # since has decided to widen the role, so this change does not either. An
    # authorization change is a separate, deliberate act.
    #
    # The effect is that superadmin now resolves the SAME WAY through every
    # path — Role(), ROLE_PERMISSIONS, canonical_role_permissions,
    # SecurityLayer.check_permission, role_has_permission and SYSTEM_ROLES all
    # say "administrative, zero granular grants". Before this it resolved four
    # different ways, including allow-all at one gate and deny-all at another.
    #
    # If superadmin should instead be operational, the change is one line here:
    #     Role.SUPERADMIN: list(ROLE_PERMISSIONS[Role.ADMIN]),
    # It is an authorization expansion and needs a security review and a data
    # migration for the ``roles`` table, which an empty entry does not.
    Role.SUPERADMIN: [],
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
        # #13228: per-bridge MCP grants — mirrors this role's MCP_READ/MCP_EXECUTE level.
        Permission.MCP_BROWSER_READ,
        Permission.MCP_DATABASE_READ,
        Permission.MCP_GIT_READ,
        Permission.MCP_HTTP_READ,
        Permission.MCP_METRICS_READ,
        Permission.MCP_DESKTOP_READ,
        Permission.MCP_BROWSER_CONTROL,
        Permission.MCP_DATABASE_WRITE,
        Permission.MCP_HTTP_WRITE,
        Permission.MCP_DESKTOP_CONTROL,
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
        # #13228: per-bridge MCP grants — mirrors this role's MCP_READ/MCP_EXECUTE level.
        Permission.MCP_BROWSER_READ,
        Permission.MCP_DATABASE_READ,
        Permission.MCP_GIT_READ,
        Permission.MCP_HTTP_READ,
        Permission.MCP_METRICS_READ,
        Permission.MCP_DESKTOP_READ,
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
        # #13228: per-bridge MCP grants — mirrors this role's MCP_READ/MCP_EXECUTE level.
        Permission.MCP_BROWSER_READ,
        Permission.MCP_DATABASE_READ,
        Permission.MCP_GIT_READ,
        Permission.MCP_HTTP_READ,
        Permission.MCP_METRICS_READ,
        Permission.MCP_DESKTOP_READ,
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
        # #13228: per-bridge MCP grants — mirrors this role's MCP_READ/MCP_EXECUTE level.
        Permission.MCP_BROWSER_READ,
        Permission.MCP_DATABASE_READ,
        Permission.MCP_GIT_READ,
        Permission.MCP_HTTP_READ,
        Permission.MCP_METRICS_READ,
        Permission.MCP_DESKTOP_READ,
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
# Role -> permission lookup (#14420)
# ---------------------------------------------------------------------------

# role -> the dot-style permission *values* it holds, built once so a caller
# checking many tools does not rebuild a set per call.
_ROLE_PERMISSION_VALUES: Dict[Role, frozenset] = {
    role: frozenset(p.value for p in perms) for role, perms in ROLE_PERMISSIONS.items()
}


def role_has_permission(role: "Role | str | None", permission: str) -> bool:
    """Return True when *role* holds *permission* (a dot-style Permission value).

    This is the canonical role/permission check other lookups (e.g.
    ``services.mcp_dispatch._would_deny``) already hand-roll against
    ``ROLE_PERMISSIONS`` — added here so a second consumer (#14420's
    ``PermissionEnforcementExtension``) does not need its own copy.

    Every role is answered from ``ROLE_PERMISSIONS`` and nowhere else. There is
    no administrative short-circuit: this used to return True for anything
    :func:`is_admin_role` accepted, which quietly made ``ADMIN_ROLES`` — a
    predicate — the most permissive permission source in the system, and put
    this function in direct contradiction with
    ``SecurityLayer.check_permission``, which denied superadmin the very
    permissions this granted it (#13854).

    Removing it costs ``admin`` nothing: ``ROLE_PERMISSIONS[Role.ADMIN]``
    contains every member of ``Permission`` (asserted in
    ``roles_are_canonical_test``), so the short-circuit never decided an admin
    call. It changes exactly one role — ``superadmin``, from allow-all to the
    empty set its ROLE_PERMISSIONS entry declares.

    An absent, unrecognised, or unmapped role is denied — this fails closed
    rather than defaulting to permissive for a role this module cannot resolve.
    A ``Role`` member with no ROLE_PERMISSIONS entry likewise denies instead of
    raising ``KeyError`` at request time, which a bare subscript here did.

    A ``Role`` **member** resolves the same as its value (#14944). This used to
    build ``Role(str(role).lower())``, which for a member is ``Role("role.admin")``
    -- a ``ValueError``, caught, and denied. A wrongly-typed argument still
    raises ``TypeError`` rather than being denied: see :func:`role_value`.
    """
    # Resolve the type FIRST, then test the resolved string for emptiness --
    # the same order as ``_normalise_role`` and ``canonical_role_permissions``.
    # A leading ``if not role`` would swallow a falsy non-role (0, [], {}, False)
    # into a quiet False while its siblings raise, which is the inconsistency
    # #14944 set out to remove rather than reproduce.
    resolved = role_value(role)
    if not resolved:
        return False
    try:
        role_enum = Role(resolved.lower())
    except ValueError:
        return False
    return permission in _ROLE_PERMISSION_VALUES.get(role_enum, frozenset())


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
    # Priority stated explicitly: the ``_ROLE_META.get`` fallback below would
    # otherwise hand superadmin priority 0, sorting the most privileged role in
    # the system BELOW readonly (10). 110 keeps the ordering honest — it is
    # administrative at every gate that admits admin. The empty permission list
    # in ROLE_PERMISSIONS is what limits it; priority is not a grant.
    Role.SUPERADMIN: {"description": "Administrative role; holds no granular permissions (#13854)", "priority": 110},
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
