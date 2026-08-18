# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Permission Enforcement Extension — issue #3009.

Built-in extension that checks tool permission levels against user roles
before allowing tool execution. Wires into the BEFORE_TOOL_EXECUTE hook.

Legacy tools that do not set ``tool_permission`` on HookContext are allowed
through unchanged so that existing callers are not broken.

Issue #14420: two gaps kept this extension inert even once it was correctly
registered on the live ``ExtensionManager`` singleton (#14280 / #14414):

1. Nothing populated ``tool_permission`` on the hook context. The value now
   comes from the MCP tool registry's ``required_permission`` (#13228 stage
   1, ``autobot_shared.auth.mcp_tool_permissions.required_permission``),
   forwarded through ``_emit_before_tool_execute`` at the real MCP dispatch
   call site (``chat_workflow.tool_handler._try_mcp_dispatch``).
2. The role check below used to compare against an ad hoc four-tier ladder
   ("public"/"authenticated"/"operator"/"admin") that nothing in the
   registry ever produced. It now delegates to the canonical Permission/Role
   mapping in ``autobot_shared.auth.permissions`` — the same source
   ``services.mcp_dispatch._would_deny`` already reads — instead of a second,
   disconnected permission model.
"""

from autobot_shared.auth.permissions import role_has_permission
from autobot_shared.logging_manager import get_logger
from middleware.base import Extension, HookContext

logger = get_logger(__name__)


def _role_satisfies(user_role: str | None, tool_permission: str) -> bool:
    """Return True if *user_role* holds *tool_permission*.

    Args:
        user_role: User's role string (e.g. ``"user"``, ``"admin"``).
                   ``None`` represents an unauthenticated caller.
        tool_permission: The dot-style ``Permission`` value the tool
                          requires (e.g. ``"mcp.database.write"``).

    Returns:
        True when the caller's role carries *tool_permission*, per the
        canonical ``ROLE_PERMISSIONS`` mapping.
    """
    return role_has_permission(user_role, tool_permission)


class PermissionEnforcementExtension(Extension):
    """Enforces per-operation tool permission levels before execution.

    Reads ``tool_permission`` and ``user_role`` from HookContext.data and
    raises ``PermissionError`` when the caller lacks sufficient privilege.

    Legacy tools that do not set ``tool_permission`` on HookContext are
    allowed through without any check (backward compatibility) — this
    matches how #13228 stage 1 marks a tool as undeclared rather than
    denied.

    Priority 0 ensures this extension runs before all others so that a
    permission denial short-circuits the entire tool-execution chain.

    ``fail_closed`` (#14420): an unexpected error while deciding a
    permission — not a deliberate ``PermissionError`` denial — must not be
    read as "allow" by ``Extension.on_hook``. Other extensions keep the
    default swallow-and-continue behaviour; this one does not, because its
    entire purpose is the deny decision.

    Usage::

        ext = PermissionEnforcementExtension()
        # Register with ExtensionManager so it fires on BEFORE_TOOL_EXECUTE
        manager.register(ext)
    """

    name = "permission_enforcement"
    priority = 0  # Runs first — before any other extension
    fail_closed = True

    async def on_before_tool_execute(self, ctx: HookContext) -> bool | None:
        """Check caller permission before tool execution.

        Args:
            ctx: Hook context.  Reads:
                 - ``ctx.data["tool_permission"]``: the dot-style
                   ``Permission`` value the tool requires (e.g.
                   ``"mcp.database.write"``). If absent the tool is
                   undeclared/legacy and allowed through.
                 - ``ctx.data["user_role"]``: caller's role string.
                   If absent the caller is treated as unauthenticated.

        Returns:
            None when the check passes (execution continues normally).

        Raises:
            PermissionError: When the caller lacks the required permission.
        """
        tool_permission = ctx.get("tool_permission")
        if tool_permission is None:
            # Undeclared/legacy tool — no permission schema declared; allow through
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
