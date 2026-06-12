# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for PermissionEnforcementExtension — issue #3009."""

import pytest

from middleware.base import HookContext
from middleware.builtin.permission_enforcement import (  # nosemgrep: extension-no-sibling-import — test file importing the unit under test; not a production cross-extension coupling
    PermissionEnforcementExtension,
    _role_satisfies,
)


class TestRoleSatisfies:
    """Unit tests for the internal _role_satisfies helper."""

    def test_public_always_allowed(self):
        assert _role_satisfies(None, "public") is True
        assert _role_satisfies("user", "public") is True
        assert _role_satisfies("admin", "public") is True

    def test_authenticated_requires_user_level(self):
        assert _role_satisfies("user", "authenticated") is True
        assert _role_satisfies("editor", "authenticated") is True
        assert _role_satisfies("admin", "authenticated") is True

    def test_authenticated_blocks_unauthenticated(self):
        assert _role_satisfies(None, "authenticated") is False

    def test_operator_requires_operator_level(self):
        assert _role_satisfies("operator", "operator") is True
        assert _role_satisfies("admin", "operator") is True

    def test_operator_blocks_user(self):
        assert _role_satisfies("user", "operator") is False
        assert _role_satisfies(None, "operator") is False

    def test_admin_requires_admin(self):
        assert _role_satisfies("admin", "admin") is True
        assert _role_satisfies("system", "admin") is True

    def test_admin_blocks_operator(self):
        assert _role_satisfies("operator", "admin") is False


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

    # ------------------------------------------------------------------
    # Legacy tools (no tool_permission set) — backward compat
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_legacy_tool_no_permission_allowed(self):
        """Tools without tool_permission (legacy) are allowed through."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("user_role", "user")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_legacy_tool_no_role_no_permission_allowed(self):
        """No tool_permission and no user_role — legacy, allowed."""
        ctx = HookContext(session_id="s1", message="test")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    # ------------------------------------------------------------------
    # Public permission
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_public_tool_unauthenticated_allowed(self):
        """Public tools work without authentication."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "public")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_public_tool_any_role_allowed(self):
        """Public tools work for any role."""
        for role in ("user", "editor", "operator", "admin"):
            ctx = HookContext(session_id="s1", message="test")
            ctx.set("tool_permission", "public")
            ctx.set("user_role", role)
            result = await self.ext.on_before_tool_execute(ctx)
            assert result is None, f"Expected None for role={role}"

    # ------------------------------------------------------------------
    # Authenticated permission
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_authenticated_tool_user_role_allowed(self):
        """Authenticated tools work for any logged-in user."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "authenticated")
        ctx.set("user_role", "user")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticated_tool_unauthenticated_blocked(self):
        """Authenticated tools block unauthenticated callers."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "authenticated")
        with pytest.raises(PermissionError, match="authenticated"):
            await self.ext.on_before_tool_execute(ctx)

    # ------------------------------------------------------------------
    # Admin permission
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_admin_tool_blocked_for_user(self):
        """Admin tools are blocked for regular users."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "admin")
        ctx.set("user_role", "user")
        with pytest.raises(PermissionError, match="admin"):
            await self.ext.on_before_tool_execute(ctx)

    @pytest.mark.asyncio
    async def test_admin_tool_allowed_for_admin(self):
        """Admin tools work for admin users."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "admin")
        ctx.set("user_role", "admin")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    # ------------------------------------------------------------------
    # Operator permission
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_operator_tool_blocked_for_user(self):
        """Operator tools are blocked for regular users."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "operator")
        ctx.set("user_role", "user")
        with pytest.raises(PermissionError):
            await self.ext.on_before_tool_execute(ctx)

    @pytest.mark.asyncio
    async def test_operator_tool_allowed_for_operator(self):
        """Operator tools work for operator users."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "operator")
        ctx.set("user_role", "operator")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_operator_tool_allowed_for_admin(self):
        """Operator tools work for admin (higher privilege)."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "operator")
        ctx.set("user_role", "admin")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    # ------------------------------------------------------------------
    # Error message content
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_error_message_includes_required_permission(self):
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "admin")
        ctx.set("user_role", "user")
        with pytest.raises(PermissionError) as exc_info:
            await self.ext.on_before_tool_execute(ctx)
        assert "admin" in str(exc_info.value)
        assert "user" in str(exc_info.value)
