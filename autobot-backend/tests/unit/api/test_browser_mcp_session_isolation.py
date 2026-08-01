# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-conversation browser session isolation (#11539).

The browser worker (autobot-browser-worker/playwright-server.js) now keys one
isolated Playwright BrowserContext per session_id instead of a single global
page shared by every conversation/user (session/cookie bleed). These tests
prove the *backend* half of that contract: ``send_to_browser_vm`` and its
callers (the ``/mcp/*`` HTTP handlers and the chat-workflow tool dispatcher)
put the caller's conversation/session id on the wire on every call, and two
different conversations produce two distinct ``session_id`` values in the
payload sent to the Browser VM — which is exactly what the worker uses to
route to (and isolate) the right BrowserContext / cookie jar.

True end-to-end cookie-jar isolation is proven on the JS side, in
autobot-browser-worker/tests/session-store.test.js (the worker has no Python
runtime).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.browser_mcp import DEFAULT_BROWSER_SESSION_ID, send_to_browser_vm
from tests.unit.api._fake_http_client import fake_http_client as _fake_http_client


@pytest.mark.asyncio
async def test_send_to_browser_vm_puts_session_id_on_the_wire():
    """Explicit session_id must appear verbatim in the /automation payload."""
    calls: list = []
    with patch("api.browser_mcp.get_http_client", return_value=_fake_http_client(calls)):
        await send_to_browser_vm("navigate", {"url": "https://github.com"}, session_id="conversation-A")

    assert len(calls) == 1
    assert calls[0]["url"].endswith("/automation")
    assert calls[0]["payload"]["session_id"] == "conversation-A"
    assert calls[0]["payload"]["action"] == "navigate"


@pytest.mark.asyncio
async def test_send_to_browser_vm_defaults_session_id_when_omitted():
    """A caller with no session_id falls back to the shared default bucket
    (#11539 backfill requirement: a lone conversation's behavior is unchanged)."""
    calls: list = []
    with patch("api.browser_mcp.get_http_client", return_value=_fake_http_client(calls)):
        await send_to_browser_vm("navigate", {"url": "https://github.com"})

    assert calls[0]["payload"]["session_id"] == DEFAULT_BROWSER_SESSION_ID == "default"


@pytest.mark.asyncio
async def test_two_conversations_route_to_distinct_session_ids_on_the_wire():
    """SECURITY (#11539): two concurrent conversations must never share a
    session_id on the wire — that id is what the worker uses to select an
    isolated BrowserContext, so distinct ids here is the backend-side
    guarantee that conversation A's cookie jar cannot be reused by B.
    """
    calls: list = []
    with patch("api.browser_mcp.get_http_client", return_value=_fake_http_client(calls)):
        await send_to_browser_vm("navigate", {"url": "https://bank.example.com/login"}, session_id="conversation-A")
        await send_to_browser_vm("navigate", {"url": "https://bank.example.com/login"}, session_id="conversation-B")

    session_ids = [c["payload"]["session_id"] for c in calls]
    assert session_ids == ["conversation-A", "conversation-B"]
    assert session_ids[0] != session_ids[1]


@pytest.mark.asyncio
async def test_handle_browser_tool_threads_chat_session_id_to_browser_vm():
    """The chat-workflow dispatch path (_handle_browser_tool) must forward its
    session_id straight through to send_to_browser_vm — this is the actual
    call site hit by every browser tool invocation from a live conversation.
    """
    from chat_workflow.tool_handler import ToolHandlerMixin

    handler = ToolHandlerMixin.__new__(ToolHandlerMixin)  # no __init__ side effects needed
    tool_call = {"name": "navigate", "params": {"url": "https://github.com"}, "description": "go"}
    execution_results: list = []

    mock_send = AsyncMock(return_value={"success": True, "result": {}})
    with (
        patch("api.browser_mcp.send_to_browser_vm", mock_send),
        patch("chat_workflow.tool_handler._emit_before_tool_execute", AsyncMock(return_value=True)),
        patch("chat_workflow.tool_handler._emit_after_tool_execute", AsyncMock(side_effect=lambda *a, **k: a[1])),
    ):
        async for _msg in handler._handle_browser_tool(tool_call, execution_results, session_id="conversation-A"):
            pass

    mock_send.assert_awaited_once()
    _args, kwargs = mock_send.call_args
    assert kwargs["session_id"] == "conversation-A"
    assert execution_results[0]["status"] == "success"


@pytest.mark.asyncio
async def test_handle_browser_tool_defaults_session_id_when_blank():
    """An empty session_id (no conversation context) still falls back to the
    shared default bucket rather than sending session_id="" to the worker."""
    from chat_workflow.tool_handler import ToolHandlerMixin

    handler = ToolHandlerMixin.__new__(ToolHandlerMixin)
    tool_call = {"name": "navigate", "params": {"url": "https://github.com"}, "description": "go"}
    execution_results: list = []

    mock_send = AsyncMock(return_value={"success": True, "result": {}})
    with (
        patch("api.browser_mcp.send_to_browser_vm", mock_send),
        patch("chat_workflow.tool_handler._emit_before_tool_execute", AsyncMock(return_value=True)),
        patch("chat_workflow.tool_handler._emit_after_tool_execute", AsyncMock(side_effect=lambda *a, **k: a[1])),
    ):
        async for _msg in handler._handle_browser_tool(tool_call, execution_results, session_id=""):
            pass

    _args, kwargs = mock_send.call_args
    assert kwargs["session_id"] == DEFAULT_BROWSER_SESSION_ID
