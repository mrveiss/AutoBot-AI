# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Voice and realtime tool calls resolve their AI line before they reach a transport (#18430).

Both HTTP entry points (``/api/voice/realtime/tools/call`` and ``/api/realtime/tools/call``) funnel through
``RealtimeMCPBridge.call_tool``, so the decision lives there once. The company is the authenticated caller's,
passed by the route, never an argument the model supplied.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.ai_lines import AiLine
from chat_workflow import approval_baseline as baseline
from services import ai_line_enforcement as enforcement
from services.realtime_mcp_bridge import RealtimeMCPBridge, _ToolEntry

COMPANY = str(uuid.UUID(int=18431))


def _bridge() -> RealtimeMCPBridge:
    bridge = RealtimeMCPBridge.__new__(RealtimeMCPBridge)
    bridge._registry = {"crm": _ToolEntry(server_id="srv", server_uri=None, original_name="crm")}
    return bridge


def _world(stored):
    async def _stored(_company, key):
        return stored.get(key), False

    return (
        patch.object(baseline, "fetch_slm_policy_json", AsyncMock(return_value=None)),
        patch.object(enforcement, "_stored", _stored),
        patch.object(enforcement, "_file_hold", AsyncMock(return_value=type("A", (), {"id": uuid.uuid4()})())),
        patch.object(enforcement, "audit_log", AsyncMock(return_value=True)),
        patch("services.realtime_mcp_bridge._audit_log", AsyncMock()),
    )


async def _call(stored, arguments, company=COMPANY):
    bridge = _bridge()
    transport = AsyncMock(return_value="sent")
    a, b, c, d, e = _world(stored)
    with a, b, c, d, e, patch.object(RealtimeMCPBridge, "_call_inprocess", transport):
        result = await bridge.call_tool("crm", arguments, user_id="u", company_id=company)
    return result, transport


@pytest.mark.asyncio
async def test_one_tool_three_actions_reach_the_transport_only_on_line_one():
    stored = {
        "crm:read": AiLine.AUTONOMOUS,
        "crm:send": AiLine.DRAFT_THEN_SEND,
        "crm:delete": AiLine.NEVER,
    }
    read, t_read = await _call(stored, {"action": "read"})
    send, t_send = await _call(stored, {"action": "send"})
    delete, t_delete = await _call(stored, {"action": "delete"})
    assert (read.is_error, send.is_error, delete.is_error) == (False, True, True)
    t_read.assert_awaited_once()
    t_send.assert_not_awaited()
    t_delete.assert_not_awaited()
    assert "requires approval" in send.content and "never touches" in delete.content


@pytest.mark.asyncio
@pytest.mark.parametrize("company", [None, "", "not-a-uuid"])
async def test_a_call_with_no_verified_company_never_reaches_the_transport(company):
    result, transport = await _call({"crm:read": AiLine.AUTONOMOUS}, {"action": "read"}, company=company)
    assert result.is_error is True and "verified company" in result.content
    transport.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_user_with_no_company_gets_line_two_for_a_voice_tool_call():
    """No company: the signed-in user's personal scope. Unset on an unknown tool is line 2, so it is held."""
    bridge = _bridge()
    transport = AsyncMock(return_value="sent")
    a, b, c, d, e = _world({})
    with a, b, c, d, e, patch.object(RealtimeMCPBridge, "_call_inprocess", transport):
        held = await bridge.call_tool("crm", {"action": "send"}, user_id=str(uuid.UUID(int=9)), company_id=None)
        forged = await bridge.call_tool(
            "crm", {"action": "send"}, user_id=str(uuid.UUID(int=9)), company_id="not-a-uuid"
        )
    transport.assert_not_awaited()
    assert "requires approval" in held.content and "verified company or user" in forged.content
