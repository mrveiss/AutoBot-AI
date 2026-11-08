# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Author: mrveiss
"""External MCP calls carry the verified caller into the audit row (#20709)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ai_lines import VERIFIED_USER_KEY
from services.mcp_dispatch import MCPDispatcher
from services.mcp_external_bridge import MCPExternalBridge, _ExternalToolEntry

_TOOL = {"name": "search", "bridge": "external", "endpoint": "", "input_schema": {}}


def _bridge() -> MCPExternalBridge:
    bridge = MCPExternalBridge()
    bridge._registry = {
        "search": _ExternalToolEntry(
            server_uri="https://mcp-a.example.com/mcp",
            original_name="search",
            guard_egress=False,
            extra_headers={},
            allowed_roles=["admin", "user"],
        )
    }
    return bridge


def _client() -> AsyncMock:
    client = AsyncMock()
    client.call_tool = AsyncMock(return_value={"ok": True})
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


async def _dispatch_external(user_id, arguments=None) -> AsyncMock:
    """Run MCPDispatcher.dispatch through the real bridge; return the audit_log double."""
    audit = AsyncMock()
    dispatcher = MCPDispatcher()
    with (
        patch.object(MCPDispatcher, "_ensure_cache_fresh", AsyncMock()),
        patch.object(MCPDispatcher, "_would_deny", return_value=None),
        patch.object(MCPDispatcher, "find_tool", return_value=_TOOL),
        patch("services.mcp_external_bridge.get_mcp_external_bridge", return_value=_bridge()),
        patch("services.mcp_external_bridge._get_mcp_client_class", return_value=lambda uri, **_: _client()),
        patch("services.audit_logger.audit_log", audit),
        patch("chat_workflow.cot_events.emit_tool_call"),
        patch("chat_workflow.cot_events.emit_tool_result"),
    ):
        result = await dispatcher.dispatch("search", arguments or {}, role="user", user_id=user_id)
    assert result["success"] is True
    return audit


@pytest.mark.asyncio
async def test_external_call_audit_row_names_the_real_user():
    audit = await _dispatch_external("alice")
    audit.assert_awaited_once()
    kwargs = audit.await_args.kwargs
    assert kwargs["user_id"] == "alice"
    assert kwargs["details"]["actor_type"] == "user"


@pytest.mark.asyncio
async def test_call_with_no_user_records_the_explicit_system_actor():
    audit = await _dispatch_external(None)
    kwargs = audit.await_args.kwargs
    assert kwargs["user_id"] == "system"
    assert kwargs["details"]["actor_type"] == "system"


@pytest.mark.asyncio
async def test_a_tool_argument_cannot_choose_the_user():
    audit = await _dispatch_external("alice", {"user_id": "mallory", "verified_user_id": "mallory"})
    assert audit.await_args.kwargs["user_id"] == "alice"


@pytest.mark.asyncio
async def test_chat_path_forwards_only_the_verified_context_user_and_session():
    from chat_workflow.tool_handler import _try_mcp_dispatch

    dispatcher = MagicMock()
    dispatcher.ensure_loaded = AsyncMock()
    dispatcher.find_tool = MagicMock(return_value=_TOOL)
    dispatcher.dispatch = AsyncMock(return_value={"success": True, "result": "r", "bridge": "external"})
    ctx = SimpleNamespace(context={VERIFIED_USER_KEY: "alice", "user_id": "mallory"})
    call = {"name": "search", "arguments": {"user_id": "mallory"}}
    with (
        patch("services.mcp_dispatch.get_mcp_dispatcher", return_value=dispatcher),
        patch("chat_workflow.tool_handler.enforce_ai_line", AsyncMock(return_value=None)),
        patch("chat_workflow.tool_handler._run_before_tool_execute_hook", AsyncMock(return_value=None)),
        patch("chat_workflow.tool_handler._emit_after_tool_execute", AsyncMock(return_value="r")),
    ):
        await _try_mcp_dispatch("search", call, [], role="user", session_id="sess-1", ctx=ctx)
    kwargs = dispatcher.dispatch.await_args.kwargs
    assert kwargs["user_id"] == "alice"
    assert kwargs["session_id"] == "sess-1"
