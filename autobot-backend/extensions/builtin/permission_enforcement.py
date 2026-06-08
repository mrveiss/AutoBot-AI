# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Permission Enforcement Extension — issue #3009.

Built-in extension that checks tool permission levels against user roles
before allowing tool execution. Wires into the BEFORE_TOOL_EXECUTE hook.

Legacy tools that do not set ``tool_permission`` on HookContext are allowed
through unchanged so that existing callers are not broken.
"""

from autobot_shared.logging_manager import get_logger
from extensions.base import Extension, HookContext

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Role / permission maps
# ---------------------------------------------------------------------------

# Role hierarchy — higher index = more privilege.
# Roles not in this map default to 0 (public / unauthenticated level).
_ROLE_LEVELS: dict[str, int] = {
    "public": 0,
    "readonly": 1,
    "user": 2,
    "editor": 3,
    "analyst": 3,
    "operator": 4,
    "admin": 5,
    "system": 5,
}

# Minimum role level required for each tool permission tier.
_PERMISSION_MIN_LEVEL: dict[str, int] = {
    "public": 0,
    "authenticated": 2,  # requires at least "user" level
    "operator": 4,
    "admin": 5,
}


def _role_satisfies(user_role: str | None, tool_permission: str) -> bool:
    """Return True if *user_role* meets the *tool_permission* requirement.

    Args:
        user_role: User's role string (e.g. ``"user"``, ``"admin"``).
                   ``None`` represents an unauthenticated caller.
        tool_permission: Required permission tier (e.g. ``"public"``, ``"admin"``).

    Returns:
        True when the caller has sufficient privilege.
    """
    if tool_permission == "public":
        return True

    if user_role is None:
        # Unauthenticated — only public tools are permitted
        return False

    user_level = _ROLE_LEVELS.get(user_role.lower(), 0)
    required_level = _PERMISSION_MIN_LEVEL.get(tool_permission.lower(), 5)
    return user_level >= required_level


class PermissionEnforcementExtension(Extension):
    """Enforces per-operation tool permission levels before execution.

    Reads ``tool_permission`` and ``user_role`` from HookContext.data and
    raises ``PermissionError`` when the caller lacks sufficient privilege.

    Legacy tools that do not set ``tool_permission`` on HookContext are
    allowed through without any check (backward compatibility).

    Priority 0 ensures this extension runs before all others so that a
    permission denial short-circuits the entire tool-execution chain.

    Usage::

        ext = PermissionEnforcementExtension()
        # Register with ExtensionManager so it fires on BEFORE_TOOL_EXECUTE
        manager.register(ext)
    """

    name = "permission_enforcement"
    priority = 0  # Runs first — before any other extension

    async def on_before_tool_execute(self, ctx: HookContext) -> bool | None:
        """Check caller permission before tool execution.

        Args:
            ctx: Hook context.  Reads:
                 - ``ctx.data["tool_permission"]``: required permission tier
                   (``"public"``, ``"authenticated"``, ``"operator"``,
                   ``"admin"``).  If absent the tool is treated as legacy and
                   allowed through.
                 - ``ctx.data["user_role"]``: caller's role string.
                   If absent the caller is treated as unauthenticated.

        Returns:
            None when the check passes (execution continues normally).

        Raises:
            PermissionError: When the caller lacks the required permission.
        """
        tool_permission = ctx.get("tool_permission")
        if tool_permission is None:
            # Legacy tool — no permission schema declared; allow through
            return None

        user_role = ctx.get("user_role")

        if not _role_satisfies(user_role, tool_permission):
            logger.warning(
                "Permission denied: tool requires '%s', user has role '%s' " "(session=%s)",
                tool_permission,
                user_role,
                ctx.session_id,
            )
            raise PermissionError(f"Tool requires '{tool_permission}' permission, " f"user has role '{user_role}'")

        logger.debug(
            "Permission granted: tool_permission='%s' user_role='%s' session=%s",
            tool_permission,
            user_role,
            ctx.session_id,
        )
        return None  # Allow execution
