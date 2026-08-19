# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Permission Enforcement Extension — issue #3009.

Built-in extension that checks tool permission levels against user roles
before allowing tool execution. Wires into the BEFORE_TOOL_EXECUTE hook.

Issue #14523 (stage 3 of #13228): an undeclared tool — ``tool_permission`` is
``None`` on HookContext — is refused, not allowed through. Before this, a
missing ``tool_permission`` was read as "legacy tool, no schema declared" and
waved through unconditionally; that was the runtime half of the default-allow
#14521's security review flagged in
``autobot_shared.auth.mcp_tool_permissions.required_permission``. #14494 made
every tool the twelve governed bridges register today carry an exact
declaration (measured at #14523 time: 104 live tools, 0 undeclared), which is
what makes refusing ``None`` safe rather than breaking a working agent flow.

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

    #14523: a tool that does not set ``tool_permission`` on HookContext — an
    undeclared tool, per ``mcp_tool_permissions.required_permission`` — is
    refused, not allowed through. Before #14523 this was read as "legacy,
    no schema declared" and waved through unconditionally; #14494 proved
    every tool the twelve governed bridges register today carries a real
    declaration, so refusing the undeclared case no longer breaks a working
    call — it refuses exactly the tool that reached production without one.

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
                   ``"mcp.database.write"``). ``None`` means the tool is
                   undeclared and is refused (#14523) — every tool a governed
                   bridge registers today carries a real declaration, so this
                   should never fire for a working call.
                 - ``ctx.data["user_role"]``: caller's role string.
                   If absent the caller is treated as unauthenticated.

        Returns:
            None when the check passes (execution continues normally).

        Raises:
            PermissionError: When the caller lacks the required permission,
                or the tool is undeclared (``tool_permission`` is ``None``).
        """
        tool_permission = ctx.get("tool_permission")
        if tool_permission is None:
            # #14523: an undeclared tool is refused, not waved through as legacy.
            logger.warning(
                "Permission denied: tool '%s' has no declared permission (session=%s)",
                ctx.get("tool_name"),
                ctx.session_id,
            )
            raise PermissionError(
                f"Tool '{ctx.get('tool_name')}' has no declared permission — refused by default (#14523)"
            )

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
