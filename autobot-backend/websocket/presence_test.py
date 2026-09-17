# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for PresenceManager and presence WebSocket handler.

Issue #3282: collaborative multi-user support — shared sessions and workspaces.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from websocket.presence import PresenceManager, _handle_presence_message, presence_websocket_handler

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


# ====================================================================
# Activity persistence tests (#16460)
# ====================================================================


def _mock_session_factory(mock_db: AsyncMock) -> MagicMock:
    """A get_async_session_factory() replacement yielding `mock_db` via `async with`."""
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = mock_db
    session_cm.__aexit__.return_value = None
    return MagicMock(return_value=session_cm)


@pytest.mark.asyncio
async def test_activity_broadcast_persists_a_collaboration_event() -> None:
    """An 'activity' kind broadcast is persisted as a CollaborationEvent."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    user_id = str(uuid.uuid4())
    message = {
        "type": "broadcast",
        "payload": {"kind": "activity", "username": "alice", "activity": {"type": "chat"}},
    }

    with (
        patch("websocket.presence.get_async_session_factory", return_value=_mock_session_factory(mock_db)),
        patch("websocket.presence.presence_manager") as mock_pm,
    ):
        mock_pm.broadcast_to_session = AsyncMock()
        await _handle_presence_message(_make_ws(), "sess-1", user_id, message)

    mock_db.add.assert_called_once()
    event = mock_db.add.call_args.args[0]
    assert event.kind == "activity"
    assert event.session_id == "sess-1"
    assert str(event.user_id) == user_id
    assert event.username == "alice"
    mock_db.commit.assert_awaited_once()
    mock_pm.broadcast_to_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_presence_update_broadcast_is_not_persisted() -> None:
    """Only 'activity' events are persisted -- 'presence_update' is transient."""
    message = {"type": "broadcast", "payload": {"kind": "presence_update", "status": "online"}}

    with (
        patch("websocket.presence.get_async_session_factory") as mock_get_factory,
        patch("websocket.presence.presence_manager") as mock_pm,
    ):
        mock_pm.broadcast_to_session = AsyncMock()
        await _handle_presence_message(_make_ws(), "sess-1", "user-A", message)

    mock_get_factory.assert_not_called()
    mock_pm.broadcast_to_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_activity_persistence_failure_does_not_block_broadcast() -> None:
    """A DB failure while persisting must never break live delivery."""
    message = {"type": "broadcast", "payload": {"kind": "activity", "username": "alice"}}

    with (
        patch("websocket.presence.get_async_session_factory", side_effect=SQLAlchemyError("boom")),
        patch("websocket.presence.presence_manager") as mock_pm,
    ):
        mock_pm.broadcast_to_session = AsyncMock()
        await _handle_presence_message(_make_ws(), "sess-1", "user-A", message)

    mock_pm.broadcast_to_session.assert_awaited_once()
