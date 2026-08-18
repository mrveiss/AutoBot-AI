# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for PermissionEnforcementExtension — issue #3009, #14420."""

import pytest

from autobot_shared.auth.permissions import Permission
from middleware.base import HookContext
from middleware.builtin.permission_enforcement import (  # nosemgrep: extension-no-sibling-import — test file importing the unit under test; not a production cross-extension coupling
    PermissionEnforcementExtension,
    _role_satisfies,
)

# #14420: `_role_satisfies` now checks caller role against the canonical
# Permission/Role mapping (autobot_shared.auth.permissions) rather than the
# old ad hoc "public"/"authenticated"/"operator"/"admin" tier ladder, which
# nothing in the registry ever produced. These are real dot-style values a
# tool can declare via `required_permission`.
_WRITE_PERM = Permission.MCP_DATABASE_WRITE.value  # granted to operator+, not user
_ADMIN_ONLY_PERM = Permission.ADMIN_SYSTEM.value  # granted to admin only
_READ_PERM = Permission.API_READ.value  # granted to readonly+


class TestRoleSatisfies:
    """Unit tests for the internal _role_satisfies helper."""

    def test_readonly_holds_a_read_permission(self):
        assert _role_satisfies("readonly", _READ_PERM) is True

    def test_unauthenticated_holds_no_permission(self):
        assert _role_satisfies(None, _READ_PERM) is False

    def test_user_lacks_a_write_permission(self):
        assert _role_satisfies("user", _WRITE_PERM) is False

    def test_operator_holds_a_write_permission(self):
        assert _role_satisfies("operator", _WRITE_PERM) is True

    def test_admin_holds_every_permission(self):
        assert _role_satisfies("admin", _WRITE_PERM) is True
        assert _role_satisfies("admin", _ADMIN_ONLY_PERM) is True

    def test_superadmin_holds_every_permission(self):
        """`superadmin` is administrative but not a `Role` enum member (#12704/#12717)."""
        assert _role_satisfies("superadmin", _ADMIN_ONLY_PERM) is True

    def test_operator_lacks_an_admin_only_permission(self):
        assert _role_satisfies("operator", _ADMIN_ONLY_PERM) is False

    def test_unrecognised_role_holds_no_permission(self):
        """An unrecognised role string fails closed rather than being permitted."""
        assert _role_satisfies("not-a-real-role", _READ_PERM) is False


class TestPermissionEnforcementExtension:
    def setup_method(self):
        self.ext = PermissionEnforcementExtension()

    # ------------------------------------------------------------------
    # Extension metadata
    # ------------------------------------------------------------------

    def test_name(self):
        assert self.ext.name == "permission_enforcement"

    def test_priority_is_zero(self):
        assert self.ext.priority == 0

    def test_fails_closed(self):
        """#14420: an unexpected error deciding permission must not read as allow."""
        assert self.ext.fail_closed is True

    # ------------------------------------------------------------------
    # Undeclared tools (no tool_permission set) — refused by default (#14523)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_undeclared_tool_with_a_role_is_refused(self):
        """#14523: no tool_permission means undeclared, and undeclared is refused
        even for an otherwise-known caller — a role cannot make up for a tool
        that never declared what it needs."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("user_role", "user")
        with pytest.raises(PermissionError, match="no declared permission"):
            await self.ext.on_before_tool_execute(ctx)

    @pytest.mark.asyncio
    async def test_undeclared_tool_with_no_role_is_refused(self):
        """#14523: no tool_permission and no user_role — still refused, not allowed."""
        ctx = HookContext(session_id="s1", message="test")
        with pytest.raises(PermissionError, match="no declared permission"):
            await self.ext.on_before_tool_execute(ctx)

    @pytest.mark.asyncio
    async def test_undeclared_tool_is_refused_even_for_admin(self):
        """#14523: undeclared denies unconditionally, before any role is even
        consulted — an admin role does not grant access to a tool nobody has
        judged what permission it needs."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("user_role", "admin")
        with pytest.raises(PermissionError, match="no declared permission"):
            await self.ext.on_before_tool_execute(ctx)

    # ------------------------------------------------------------------
    # Declared permission, caller lacks it
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_unauthenticated_caller_blocked(self):
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", _READ_PERM)
        with pytest.raises(PermissionError, match=_READ_PERM):
            await self.ext.on_before_tool_execute(ctx)

    @pytest.mark.asyncio
    async def test_user_blocked_from_write_permission(self):
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", _WRITE_PERM)
        ctx.set("user_role", "user")
        with pytest.raises(PermissionError, match="user"):
            await self.ext.on_before_tool_execute(ctx)

    @pytest.mark.asyncio
    async def test_operator_blocked_from_admin_only_permission(self):
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", _ADMIN_ONLY_PERM)
        ctx.set("user_role", "operator")
        with pytest.raises(PermissionError):
            await self.ext.on_before_tool_execute(ctx)

    # ------------------------------------------------------------------
    # Declared permission, caller holds it
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_operator_allowed_for_write_permission(self):
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", _WRITE_PERM)
        ctx.set("user_role", "operator")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_admin_allowed_for_admin_only_permission(self):
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", _ADMIN_ONLY_PERM)
        ctx.set("user_role", "admin")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    # ------------------------------------------------------------------
    # Error message content
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_error_message_includes_required_permission_and_role(self):
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", _ADMIN_ONLY_PERM)
        ctx.set("user_role", "user")
        with pytest.raises(PermissionError) as exc_info:
            await self.ext.on_before_tool_execute(ctx)
        assert _ADMIN_ONLY_PERM in str(exc_info.value)
        assert "user" in str(exc_info.value)
