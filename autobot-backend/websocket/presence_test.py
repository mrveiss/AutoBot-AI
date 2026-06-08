# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for PresenceManager and presence WebSocket handler.

Issue #3282: collaborative multi-user support — shared sessions and workspaces.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from websocket.presence import PresenceManager, presence_websocket_handler

# ====================================================================
# PresenceManager Unit Tests
# ====================================================================


@pytest.fixture
def manager() -> PresenceManager:
    """Fresh PresenceManager for each test."""
    return PresenceManager()


def _make_ws() -> MagicMock:
    """Create a mock WebSocket with async send_text."""
    ws = MagicMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_registers_user(manager: PresenceManager) -> None:
    """Connecting a user adds them to the session."""
    ws = _make_ws()
    await manager.connect("sess-1", "user-A", ws)

    online = await manager.get_online_users("sess-1")
    assert "user-A" in online


@pytest.mark.asyncio
async def test_connect_broadcasts_join_to_others(manager: PresenceManager) -> None:
    """A second user connecting gets broadcast to the first user."""
    ws_a = _make_ws()
    ws_b = _make_ws()

    await manager.connect("sess-1", "user-A", ws_a)
    await manager.connect("sess-1", "user-B", ws_b)

    # user-A should have received the user_joined broadcast for user-B
    calls = [call.args[0] for call in ws_a.send_text.call_args_list]
    events = [json.loads(c) for c in calls]
    join_events = [e for e in events if e.get("type") == "user_joined"]
    assert any(e["user_id"] == "user-B" for e in join_events)


@pytest.mark.asyncio
async def test_disconnect_removes_user(manager: PresenceManager) -> None:
    """Disconnecting removes user from online list."""
    ws = _make_ws()
    await manager.connect("sess-1", "user-A", ws)
    await manager.disconnect(ws)

    online = await manager.get_online_users("sess-1")
    assert "user-A" not in online


@pytest.mark.asyncio
async def test_disconnect_broadcasts_leave(manager: PresenceManager) -> None:
    """When a user disconnects, remaining users receive user_left event."""
    ws_a = _make_ws()
    ws_b = _make_ws()

    await manager.connect("sess-1", "user-A", ws_a)
    await manager.connect("sess-1", "user-B", ws_b)
    ws_a.send_text.reset_mock()
    ws_b.send_text.reset_mock()

    await manager.disconnect(ws_a)

    calls = [call.args[0] for call in ws_b.send_text.call_args_list]
    events = [json.loads(c) for c in calls]
    leave_events = [e for e in events if e.get("type") == "user_left"]
    assert any(e["user_id"] == "user-A" for e in leave_events)


@pytest.mark.asyncio
async def test_disconnect_unknown_websocket_is_noop(manager: PresenceManager) -> None:
    """Disconnecting an untracked WebSocket does not raise."""
    ws = _make_ws()
    await manager.disconnect(ws)  # Must not raise


@pytest.mark.asyncio
async def test_get_online_users_empty_session(manager: PresenceManager) -> None:
    """Getting online users for a session with no connections returns empty list."""
    result = await manager.get_online_users("nonexistent")
    assert result == []


@pytest.mark.asyncio
async def test_send_to_user_success(manager: PresenceManager) -> None:
    """send_to_user delivers message to all connections for that user."""
    ws1 = _make_ws()
    ws2 = _make_ws()
    await manager.connect("sess-1", "user-A", ws1)
    # user-B joins so ws1's join-broadcast doesn't skew counts
    ws_other = _make_ws()
    await manager.connect("sess-1", "user-B", ws_other)

    # Reset call counts before the targeted send
    ws1.send_text.reset_mock()
    ws2.send_text.reset_mock()

    # Register second connection for user-A *without* going through connect()
    # to avoid broadcast side-effects; directly inject into manager state.
    manager._sessions["sess-1"]["user-A"].add(ws2)
    manager._connection_map[ws2] = ("sess-1", "user-A")

    count = await manager.send_to_user("sess-1", "user-A", {"type": "ping"})

    assert count == 2
    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_to_user_absent_returns_zero(manager: PresenceManager) -> None:
    """send_to_user for a user not in session returns 0."""
    count = await manager.send_to_user("sess-1", "ghost", {"type": "ping"})
    assert count == 0


@pytest.mark.asyncio
async def test_broadcast_to_session_reaches_all(manager: PresenceManager) -> None:
    """broadcast_to_session delivers to every connected user."""
    ws_a = _make_ws()
    ws_b = _make_ws()
    await manager.connect("sess-1", "user-A", ws_a)
    await manager.connect("sess-1", "user-B", ws_b)
    ws_a.send_text.reset_mock()
    ws_b.send_text.reset_mock()

    await manager.broadcast_to_session("sess-1", {"type": "test"})

    ws_a.send_text.assert_awaited_once()
    ws_b.send_text.assert_awaited_once()


# ====================================================================
# presence_websocket_handler Tests
# ====================================================================


@pytest.mark.asyncio
async def test_handler_sends_presence_sync_on_connect() -> None:
    """Handler sends presence_sync immediately after connection."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.send_text = AsyncMock()

    from fastapi import WebSocketDisconnect

    # After presence_sync, disconnect immediately
    ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

    with patch("websocket.presence.presence_manager") as mock_pm:
        mock_pm.connect = AsyncMock()
        mock_pm.disconnect = AsyncMock()
        mock_pm.get_online_users = AsyncMock(return_value=["user-X"])

        await presence_websocket_handler(ws, "sess-1", "user-X")

    ws.send_json.assert_awaited()
    sent = ws.send_json.call_args_list[0].args[0]
    assert sent["type"] == "presence_sync"
    assert "user-X" in sent["online_users"]


@pytest.mark.asyncio
async def test_handler_responds_to_ping() -> None:
    """Handler sends pong in response to ping message."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.send_text = AsyncMock()

    from fastapi import WebSocketDisconnect

    ping_json = json.dumps({"type": "ping"})
    ws.receive_text = AsyncMock(side_effect=[ping_json, WebSocketDisconnect()])

    with patch("websocket.presence.presence_manager") as mock_pm:
        mock_pm.connect = AsyncMock()
        mock_pm.disconnect = AsyncMock()
        mock_pm.get_online_users = AsyncMock(return_value=[])

        await presence_websocket_handler(ws, "sess-1", "user-A")

    pong_calls = [call.args[0] for call in ws.send_json.call_args_list if call.args[0].get("type") == "pong"]
    assert len(pong_calls) == 1
