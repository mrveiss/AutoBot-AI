# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Raw Redis read tools cannot reach KB facts as a non-admin; admin reads of them are audited (#21605).

The guard class at the bottom fails when a tool is granted to non-admins with a ``key``/``pattern``
argument but the router does not run the read-scope check before dispatch.
"""

import inspect
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.redis_mcp import router as router_module
from api.redis_mcp.rbac import TOOL_ACCESS_MATRIX, ToolAccess, validate_read_scope
from api.redis_mcp.router import RedisToolCallRequest, call_redis_mcp_tool

USER = {"user_id": "u1", "role": "user"}
ADMIN = {"user_id": "a1", "role": "admin"}
FACT = "fact:abc"
AGENT_KEY = "autobot:agent:note"
KEY_TOOLS = {
    "redis_get": {"key": FACT},
    "redis_hget": {"key": FACT, "field": "content"},
    "redis_hgetall": {"key": FACT},
    "redis_scan_keys": {"pattern": "fact:*"},
}


async def _call(user, tool, args, handler_result=None):
    handler = AsyncMock(return_value=handler_result or {"ok": True})
    with patch.dict(router_module._TOOL_HANDLERS, {tool: handler}):
        out = await call_redis_mcp_tool(RedisToolCallRequest(tool_name=tool, arguments=args), user)
    return out, handler


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", sorted(KEY_TOOLS))
async def test_non_admin_key_outside_namespace_is_403_and_never_read(tool):
    handler = AsyncMock()
    with patch.dict(router_module._TOOL_HANDLERS, {tool: handler}):
        with pytest.raises(HTTPException) as exc:
            await call_redis_mcp_tool(RedisToolCallRequest(tool_name=tool, arguments=KEY_TOOLS[tool]), USER)
    assert exc.value.status_code == 403
    handler.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", sorted(KEY_TOOLS))
@pytest.mark.parametrize("database", ["knowledge", "facts"])
async def test_non_admin_knowledge_database_is_403_even_in_namespace(tool, database):
    args = dict(KEY_TOOLS[tool], database=database)
    args["pattern" if tool == "redis_scan_keys" else "key"] = AGENT_KEY + ("*" if tool == "redis_scan_keys" else "")
    handler = AsyncMock()
    with patch.dict(router_module._TOOL_HANDLERS, {tool: handler}):
        with pytest.raises(HTTPException) as exc:
            await call_redis_mcp_tool(RedisToolCallRequest(tool_name=tool, arguments=args), USER)
    assert exc.value.status_code == 403
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_admin_can_still_read_the_agent_namespace():
    out, handler = await _call(USER, "redis_get", {"key": AGENT_KEY})
    assert out == {"ok": True}
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_knowledge_read_is_audited_before_the_read():
    audit = AsyncMock(return_value=True)
    with patch("knowledge.root_read.audit_admin_read", audit):
        _, handler = await _call(ADMIN, "redis_hgetall", {"key": FACT, "database": "knowledge"})
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "a1"
    assert audit.await_args.args[1]["database"] == "knowledge"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_knowledge_read_is_withheld_when_the_audit_fails():
    with patch("knowledge.root_read.audit_admin_read", AsyncMock(return_value=False)):
        handler = AsyncMock()
        with patch.dict(router_module._TOOL_HANDLERS, {"redis_hgetall": handler}):
            with pytest.raises(HTTPException) as exc:
                await call_redis_mcp_tool(
                    RedisToolCallRequest(
                        tool_name="redis_hgetall",
                        arguments={"key": FACT, "database": "knowledge"},
                    ),
                    ADMIN,
                )
    assert exc.value.status_code == 503
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_read_of_an_ordinary_database_is_not_audited():
    audit = AsyncMock(return_value=True)
    with patch("knowledge.root_read.audit_admin_read", audit):
        await _call(ADMIN, "redis_get", {"key": "any:key"})
    audit.assert_not_awaited()


class TestRawReadGuard:
    """A raw tool granted to non-admins must pass through the read-scope check (#21605 AC3)."""

    def test_router_runs_the_read_scope_check_before_dispatch(self):
        source = inspect.getsource(router_module.call_redis_mcp_tool)
        assert source.index("_enforce_read_scope") < source.index("handler(args)")

    def test_every_user_readable_key_tool_is_confined(self):
        granted = [t for t, (user, _) in TOOL_ACCESS_MATRIX.items() if user is ToolAccess.READ]
        for tool in set(granted) & set(KEY_TOOLS):
            ok, _ = validate_read_scope(KEY_TOOLS[tool], is_admin=False)
            assert not ok, f"{tool} is readable by non-admins outside the agent namespace"

    def test_every_handler_taking_a_key_argument_is_covered_by_the_scope_check(self):
        """A new tool whose wrapper reads args['key'|'pattern'] is confined by name of the argument."""
        from api.redis_mcp.rbac import _READ_KEY_ARGS

        for tool, wrapper in router_module._TOOL_HANDLERS.items():
            used = {
                a
                for a in ("key", "keys", "pattern")
                if f'args["{a}"]' in inspect.getsource(wrapper) or f'args.get("{a}"' in inspect.getsource(wrapper)
            }
            if TOOL_ACCESS_MATRIX[tool][0] is ToolAccess.READ:
                assert used <= set(_READ_KEY_ARGS), f"{tool} reads {used - set(_READ_KEY_ARGS)} outside the scoped args"
