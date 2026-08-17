# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RBAC denial reaches the real MCP dispatch call site (#14420).

Two independent gaps kept `PermissionEnforcementExtension` inert even once
correctly registered (#14280/#14414):

1. Nothing populated `HookContext.data["tool_permission"]` at any production
   call site — only the extension's own unit tests did, which is why its
   tests passed while the extension never ran.
2. A denial raised as `PermissionError` was swallowed by
   `Extension.on_hook`'s blanket `except Exception` into `None`, which
   `not any(result is False for result in results)` reads as allow.

These tests exercise `_try_mcp_dispatch` — the real call site — end to end,
not a hand-populated `HookContext`. That distinction is the point: a test
that only proves the extension's own logic would have passed before either
gap was closed.
"""

from unittest.mock import AsyncMock

import pytest

from chat_workflow.tool_handler import _try_mcp_dispatch
from middleware.builtin.permission_enforcement import PermissionEnforcementExtension
from middleware.manager import get_extension_manager, reset_extension_manager

_TOOL_NAME = "database_execute"
_TOOL_ENTRY = {
    "name": _TOOL_NAME,
    "bridge": "database_mcp",
    "endpoint": "/api/database/mcp/database_execute",
    "input_schema": {},
    # #13228 stage 1: declared on the registry entry by
    # autobot_shared.auth.mcp_tool_permissions.required_permission().
    "required_permission": "mcp.database.write",
}
_ARGUMENTS = {"query": "UPDATE accounts SET balance = balance + 1"}


class _StubDispatcher:
    """Stands in for MCPDispatcher — the registry lookup is what matters here,
    not the HTTP bridge call, which PermissionEnforcementExtension must
    short-circuit before it ever runs."""

    def __init__(self, tool_entry: dict):
        self._cache_loaded = True
        self._tool_cache = {tool_entry["name"]: tool_entry}
        self.dispatch = AsyncMock(return_value={"success": True, "result": "ran", "bridge": tool_entry["bridge"]})

    def find_tool(self, name: str):
        return self._tool_cache.get(name)

    async def refresh_tool_cache(self) -> int:  # pragma: no cover - cache pre-seeded
        return len(self._tool_cache)


@pytest.fixture(autouse=True)
def _reset_manager():
    reset_extension_manager()
    yield
    reset_extension_manager()


async def _dispatch(monkeypatch, role: str | None):
    get_extension_manager().register(PermissionEnforcementExtension())
    stub = _StubDispatcher(_TOOL_ENTRY)
    monkeypatch.setattr("services.mcp_dispatch.get_mcp_dispatcher", lambda: stub)

    result = await _try_mcp_dispatch(
        _TOOL_NAME,
        {"arguments": _ARGUMENTS},
        execution_results=[],
        role=role,
        session_id="sess-1",
    )
    return result, stub


class TestDenialReachesTheRealCallSite:
    @pytest.mark.asyncio
    async def test_a_caller_lacking_the_required_permission_is_denied(self, monkeypatch):
        """AC: denied end to end from `_try_mcp_dispatch`, not a hand-built ctx.

        `readonly` does not hold `mcp.database.write` in
        `autobot_shared.auth.permissions.ROLE_PERMISSIONS`.
        """
        result, stub = await _dispatch(monkeypatch, role="readonly")

        assert result.type == "error"
        assert result.metadata.get("cancelled_by_hook") is True
        # #14420 (review): the agent loop must be able to tell this apart
        # from an arbitrary hook veto, or it may retry forever.
        assert result.metadata.get("reason") == "permission_denied"
        stub.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_caller_holding_the_required_permission_is_allowed(self, monkeypatch):
        """`operator` holds `mcp.database.write` — this is the control case
        proving the extension discriminates, not merely always-denies."""
        result, stub = await _dispatch(monkeypatch, role="operator")

        assert result.type == "tool_result"
        stub.dispatch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_an_unauthenticated_caller_is_denied(self, monkeypatch):
        result, stub = await _dispatch(monkeypatch, role=None)

        assert result.type == "error"
        assert result.metadata.get("cancelled_by_hook") is True
        assert result.metadata.get("reason") == "permission_denied"
        stub.dispatch.assert_not_called()
