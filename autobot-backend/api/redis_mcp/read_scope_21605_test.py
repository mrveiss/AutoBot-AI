# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Raw Redis read tools cannot reach KB facts as a non-admin; admin reads of them are audited (#21605).

The guard class at the bottom fails when a tool is granted to non-admins with a ``key``/``pattern``
argument but the router does not run the read-scope check before dispatch.
"""

import importlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.redis_mcp.rbac import SCOPED_READ_ARGS, TOOL_ACCESS_MATRIX, ToolAccess, validate_read_scope
from api.redis_mcp.router import RedisToolCallRequest, call_redis_mcp_tool, redis_mcp_tool_endpoint
from api.redis_mcp.tools import get_all_tools

# The package re-exports `router` (an APIRouter), so `from api.redis_mcp import router` is not the module.
router_module = importlib.import_module("api.redis_mcp.router")

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


VECTOR_TOOLS = ("redis_vector_search", "redis_hybrid_search", "redis_vector_index_info")


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", VECTOR_TOOLS)
async def test_non_admin_index_outside_agent_prefix_is_403_and_never_read(tool):
    handler = AsyncMock()
    with patch.dict(router_module._TOOL_HANDLERS, {tool: handler}):
        with pytest.raises(HTTPException) as exc:
            await call_redis_mcp_tool(
                RedisToolCallRequest(tool_name=tool, arguments={"index_name": "idx:knowledge"}), USER
            )
    assert exc.value.status_code == 403
    handler.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", VECTOR_TOOLS)
async def test_non_admin_default_and_agent_index_are_allowed(tool):
    for args in ({}, {"index_name": "idx:agent_memory"}):
        out, handler = await _call(USER, tool, args)
        assert out == {"ok": True}
        handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_read_of_a_non_agent_index_is_audited():
    audit = AsyncMock(return_value=True)
    with patch("knowledge.root_read.audit_admin_read", audit):
        await _call(ADMIN, "redis_vector_search", {"index_name": "idx:knowledge"})
    audit.assert_awaited_once()
    assert audit.await_args.args[1]["index"] == "idx:knowledge"


@pytest.mark.asyncio
async def test_per_tool_endpoint_enforces_the_read_scope_before_the_handler():
    """Behavioural: the registry route /mcp/{tool} reaches the same check, and the handler never runs."""
    handler = AsyncMock()
    with patch.dict(router_module._TOOL_HANDLERS, {"redis_hgetall": handler}):
        with pytest.raises(HTTPException) as exc:
            await redis_mcp_tool_endpoint("redis_hgetall", RedisToolCallRequest(arguments={"key": FACT}), USER)
    assert exc.value.status_code == 403
    handler.assert_not_awaited()


def _schema_args(tool) -> set[str]:
    return set((tool.input_schema or {}).get("properties", {}))


class TestRawReadGuard:
    """Derived from the tools' declared input schemas, so a new tool is covered without editing this file (#21605, #21740).

    Limit: it recognises a key-bearing argument by name (``key``, ``keys``, ``pattern``, ``index_name`` or any
    argument containing ``key``/``pattern``/``index``); a differently named argument must be added to
    ``SCOPED_READ_ARGS`` by whoever adds the tool.
    """

    def _user_reachable_tools(self):
        return [t for t in get_all_tools() if TOOL_ACCESS_MATRIX[t.name][0] is not ToolAccess.BLOCKED]

    def test_every_key_like_schema_argument_of_a_user_readable_tool_is_scoped(self):
        for tool in self._user_reachable_tools():
            like = {a for a in _schema_args(tool) if any(w in a for w in ("key", "pattern", "index", "prefix"))}
            assert like <= SCOPED_READ_ARGS | {"keys"}, f"{tool.name}: {like - SCOPED_READ_ARGS} not read-scoped"

    def test_every_user_readable_key_or_index_tool_is_denied_outside_the_scope(self):
        for tool in self._user_reachable_tools():
            props = _schema_args(tool)
            probe = {a: "outside:ns" for a in props & SCOPED_READ_ARGS}
            if probe:
                ok, _ = validate_read_scope(probe, is_admin=False)
                assert not ok, f"{tool.name} is readable by non-admins outside the agent scope"

    def test_every_vector_tool_declares_an_index_argument_that_is_scoped(self):
        for name in VECTOR_TOOLS:
            tool = next(t for t in get_all_tools() if t.name == name)
            assert "index_name" in _schema_args(tool)


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["fact:", ["autobot:agent:ok", "fact:"], "", []])
async def test_non_admin_cannot_create_an_index_over_a_non_agent_prefix(prefix):
    handler = AsyncMock()
    args = {"index_name": "idx:agent_x", "prefix": prefix}
    with patch.dict(router_module._TOOL_HANDLERS, {"redis_vector_create_index": handler}):
        with pytest.raises(HTTPException) as exc:
            await call_redis_mcp_tool(RedisToolCallRequest(tool_name="redis_vector_create_index", arguments=args), USER)
    assert exc.value.status_code == 403
    handler.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, ""])
async def test_non_admin_explicit_empty_index_is_denied(value):
    ok, _ = validate_read_scope({"index_name": value}, is_admin=False)
    assert not ok


@pytest.mark.asyncio
async def test_non_admin_agent_prefix_index_creation_is_allowed():
    args = {"index_name": "idx:agent_x", "prefix": "autobot:agent:x:"}
    out, handler = await _call(USER, "redis_vector_create_index", args)
    assert out == {"ok": True}
    handler.assert_awaited_once()
