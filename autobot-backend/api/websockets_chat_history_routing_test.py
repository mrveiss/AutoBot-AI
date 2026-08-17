# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for Issue #14342 — websocket-formatted chat events were

written to ``ChatHistoryManager``'s default (non-session) bucket because
``_add_to_chat_history`` never forwarded ``session_id`` to ``add_message``.
Nothing that serves a session (``get_session_messages``, ``load_session``)
ever reads that bucket, so every agent-step, tool-output, workflow and
thought event the websocket layer formatted was silently unreadable.

These tests exercise the *real* producer path — ``broadcast_event``, the
exact callback ``events/bus.py`` invokes for every published event — through
to a real ``MessagesMixin``-backed session store, not a hand-fed dict shaped
to match what the fix happens to check.
"""

import asyncio
from typing import Any, Dict, List

from api.websockets import _create_broadcast_event_handler
from chat_history.messages import MessagesMixin


class _RecordingHistory(MessagesMixin):
    """Exercises the real ``add_message``/``get_session_messages`` pair
    against an in-memory session store, mirroring
    ``chat_history/add_message_call_sites_test.py``."""

    def __init__(self) -> None:
        self.history: List[Dict[str, Any]] = []
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self.sessions.get(session_id, []))

    async def save_session(self, session_id: str, messages: List[Dict[str, Any]], **_: Any) -> bool:
        self.sessions[session_id] = list(messages)
        return True


class _FakeWebSocket:
    """Minimal stand-in for the real FastAPI WebSocket send path."""

    def __init__(self) -> None:
        self.sent: List[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


def test_tool_output_event_round_trips_through_its_own_session() -> None:
    """A tool-output event raised on a session is readable back through
    get_session_messages for that session — the real websocket entry point,
    not the internal dispatch helper."""
    manager = _RecordingHistory()
    websocket = _FakeWebSocket()

    async def run() -> None:
        broadcast_event = await _create_broadcast_event_handler(websocket, manager)
        await broadcast_event(
            {
                "type": "tool_output",
                "payload": {"output": "command finished", "session_id": "session-a"},
            }
        )

    asyncio.run(run())

    stored = asyncio.run(manager.get_session_messages("session-a", limit=500))
    assert len(stored) == 1
    assert stored[0]["sender"] == "tool-output"
    assert "command finished" in stored[0]["text"]
    # Never written to the manager's internal default bucket.
    assert manager.history == []


def test_tool_output_event_not_visible_from_a_different_session() -> None:
    """An event raised on session-a must not leak into session-b's history."""
    manager = _RecordingHistory()
    websocket = _FakeWebSocket()

    async def run() -> None:
        broadcast_event = await _create_broadcast_event_handler(websocket, manager)
        await broadcast_event(
            {
                "type": "tool_output",
                "payload": {"output": "secret result", "session_id": "session-a"},
            }
        )

    asyncio.run(run())

    other_session = asyncio.run(manager.get_session_messages("session-b", limit=500))
    assert other_session == []


def test_workflow_error_event_without_session_id_falls_back_to_default_bucket() -> None:
    """A genuinely session-less event (no session_id in its payload) keeps its
    prior behaviour instead of raising — the fallback the fix must preserve."""
    manager = _RecordingHistory()
    websocket = _FakeWebSocket()

    async def run() -> None:
        broadcast_event = await _create_broadcast_event_handler(websocket, manager)
        await broadcast_event(
            {
                "type": "workflow_failed",
                "payload": {"workflow_id": "wf-1", "error": "boom"},
            }
        )

    asyncio.run(run())

    assert len(manager.history) == 1
    assert manager.history[0]["sender"] == "workflow-error"
