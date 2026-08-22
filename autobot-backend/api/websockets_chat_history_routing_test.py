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

These tests exercise the *real* producer path through to a real
``MessagesMixin``-backed session store, not a hand-fed dict shaped to match
what the fix happens to check.

Issue #14814 moved that path: chat history used to be written from inside the
WebSocket broadcast callback, which meant nothing was persisted at all when no
client was attached. Persistence now hangs off the event manager's publish-time
hook (``_persist_event_to_chat_history``), so these tests drive *that* — the
#14342 session-routing guarantee is unchanged, only its location moved.
"""

import asyncio
from typing import Any, Dict, List
from unittest.mock import patch

from api.websockets import _persist_event_to_chat_history
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


async def _persist_with(manager: "_RecordingHistory", event: dict) -> None:
    """Run the production persistence hook against ``manager``.

    The hook resolves the process-wide manager itself, so the seam under test is
    that resolution plus the routing below it — the same code path a published
    event takes in production.
    """
    with patch(
        "utils.resource_factory.ResourceFactory.get_initialized_chat_history_manager",
        return_value=manager,
    ):
        await _persist_event_to_chat_history(event)


def test_tool_output_event_round_trips_through_its_own_session() -> None:
    """A tool-output event raised on a session is readable back through
    get_session_messages for that session — the real websocket entry point,
    not the internal dispatch helper."""
    manager = _RecordingHistory()

    asyncio.run(
        _persist_with(
            manager,
            {
                "type": "tool_output",
                "payload": {"output": "command finished", "session_id": "session-a"},
            },
        )
    )

    stored = asyncio.run(manager.get_session_messages("session-a", limit=500))
    assert len(stored) == 1
    assert stored[0]["sender"] == "tool-output"
    assert "command finished" in stored[0]["text"]
    # Never written to the manager's internal default bucket.
    assert manager.history == []


def test_tool_output_event_not_visible_from_a_different_session() -> None:
    """An event raised on session-a must not leak into session-b's history."""
    manager = _RecordingHistory()

    asyncio.run(
        _persist_with(
            manager,
            {
                "type": "tool_output",
                "payload": {"output": "secret result", "session_id": "session-a"},
            },
        )
    )

    other_session = asyncio.run(manager.get_session_messages("session-b", limit=500))
    assert other_session == []


def test_workflow_error_event_without_session_id_falls_back_to_default_bucket() -> None:
    """A genuinely session-less event (no session_id in its payload) keeps its
    prior behaviour instead of raising — the fallback the fix must preserve."""
    manager = _RecordingHistory()

    asyncio.run(
        _persist_with(
            manager,
            {
                "type": "workflow_failed",
                "payload": {"workflow_id": "wf-1", "error": "boom"},
            },
        )
    )

    assert len(manager.history) == 1
    assert manager.history[0]["sender"] == "workflow-error"


def test_event_is_persisted_with_no_websocket_client_attached() -> None:
    """#14814: persistence must not be a side effect of delivery.

    This is the regression that motivated moving the write out of
    ``broadcast_event``: with no client connected there was no callback, so no
    broadcast, so nothing was ever written. No WebSocket exists in this test at
    all — the event must still land.
    """
    manager = _RecordingHistory()

    asyncio.run(
        _persist_with(
            manager,
            {
                "type": "llm_response",
                "payload": {"response": "answered offline", "session_id": "session-z"},
            },
        )
    )

    stored = asyncio.run(manager.get_session_messages("session-z", limit=500))
    assert len(stored) == 1, "nothing was persisted while no client was connected"
    assert "answered offline" in stored[0]["text"]
