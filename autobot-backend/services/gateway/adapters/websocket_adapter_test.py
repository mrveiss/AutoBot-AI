# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pins WebSocketAdapter's inbound and outbound behaviour (#15024).

The adapter moved from the retired ``channel_adapters`` package into ``adapters``;
these tests fix the wire format on both sides of the move.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket
from starlette.websockets import WebSocketState

from services.gateway.adapters import BaseChannelAdapter, WebSocketAdapter
from services.gateway.types import ChannelMessage, ChannelType, GatewayMessageType, GatewaySession


def _session() -> GatewaySession:
    return GatewaySession(session_id="s1", user_id="u1", channel=ChannelType.WEBSOCKET)


def _socket(state: WebSocketState = WebSocketState.CONNECTED) -> MagicMock:
    ws = MagicMock(spec=WebSocket)
    ws.client_state = state
    ws.send_json = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


def test_websocket_adapter_is_a_channel_adapter_for_the_websocket_channel() -> None:
    adapter = WebSocketAdapter()
    assert isinstance(adapter, BaseChannelAdapter)
    assert adapter.channel_type is ChannelType.WEBSOCKET


@pytest.mark.asyncio
async def test_inbound_dict_and_json_string_parse_identically() -> None:
    adapter, raw = WebSocketAdapter(), {"type": "voice", "data": "hello", "metadata": {"k": 1}}
    from_dict = await adapter.receive_message(raw, _session())
    from_str = await adapter.receive_message(json.dumps(raw), _session())
    for msg in (from_dict, from_str):
        assert msg.message_type is GatewayMessageType.USER_VOICE
        assert msg.content == "hello" and msg.metadata == {"k": 1}
        assert msg.session_id == "s1" and msg.channel is ChannelType.WEBSOCKET


@pytest.mark.asyncio
async def test_inbound_defaults_and_rejections() -> None:
    adapter = WebSocketAdapter()
    plain = await adapter.receive_message({"message": "hi"}, _session())
    assert plain.message_type is GatewayMessageType.USER_TEXT and plain.content == "hi"
    assert await adapter.receive_message("{not json", _session()) is None
    assert await adapter.receive_message(42, _session()) is None


@pytest.mark.asyncio
async def test_outbound_wire_format() -> None:
    adapter, ws = WebSocketAdapter(), _socket()
    msg = ChannelMessage(
        session_id="s1",
        channel=ChannelType.WEBSOCKET,
        message_type=GatewayMessageType.AGENT_TEXT,
        content="reply",
        metadata={"m": 2},
    )
    assert await adapter.send_message(msg, _session(), ws) is True
    sent = ws.send_json.call_args.args[0]
    assert sent == {
        "type": "llm_response",
        "data": {"content": "reply"},
        "message_id": msg.message_id,
        "timestamp": msg.created_at.isoformat(),
        "metadata": {"m": 2},
    }


@pytest.mark.asyncio
async def test_outbound_refuses_a_bad_or_closed_connection() -> None:
    adapter = WebSocketAdapter()
    msg = ChannelMessage(session_id="s1", channel=ChannelType.WEBSOCKET, message_type=GatewayMessageType.AGENT_TEXT)
    assert await adapter.send_message(msg, _session(), object()) is False
    closed = _socket(WebSocketState.DISCONNECTED)
    assert await adapter.send_message(msg, _session(), closed) is False
    closed.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_connect_heartbeat_disconnect_lifecycle() -> None:
    adapter, ws = WebSocketAdapter(), _socket()
    with pytest.raises(ValueError):
        await adapter.connect(_session(), {})
    assert await adapter.connect(_session(), {"websocket": ws}) is ws
    ws.accept.assert_awaited_once()
    assert await adapter.handle_heartbeat(_session(), ws) is True
    assert ws.send_json.call_args.args[0]["type"] == "heartbeat"
    assert await adapter.handle_heartbeat(_session(), None) is False
    await adapter.disconnect(_session(), ws)
    ws.close.assert_awaited_once()
