# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for Issue #14340 — the shared-link viewer rendered every

shared session empty.

``get_session_messages`` returns records in the *stored* shape (``sender``/
``text``), which ``_load_session_data``'s filter and mapping asked for under
keys (``role``/``content``) the stored shape has never carried. The
membership test was therefore ``None in {"user", "assistant"}`` for every
record, so the comprehension always produced an empty list — a well-formed,
empty ``200`` response indistinguishable from a session shared before
anything was said.

These tests write fixtures with the real writer (``MessagesMixin.add_message``,
via the same in-memory harness ``chat_history/add_message_call_sites_test.py``
uses) and call the real endpoint helper, ``_load_session_data`` — a
hand-written record carrying ``role``/``content`` directly would pass against
the broken code too, so it would not catch this.
"""

import asyncio
import types
from typing import Any, Dict, List

from api.chat_shared_links import _load_session_data
from chat_history.messages import MessagesMixin


class _RecordingHistory(MessagesMixin):
    """Real add_message/get_session_messages pair over an in-memory store."""

    def __init__(self) -> None:
        self.history: List[Dict[str, Any]] = []
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self.sessions.get(session_id, []))

    async def save_session(self, session_id: str, messages: List[Dict[str, Any]], **_: Any) -> bool:
        self.sessions[session_id] = list(messages)
        return True


def _fake_request(manager: _RecordingHistory) -> types.SimpleNamespace:
    """A Request stand-in exposing only what get_chat_history_manager reads."""
    state = types.SimpleNamespace(chat_history_manager=manager)
    app = types.SimpleNamespace(state=state)
    return types.SimpleNamespace(app=app)


def _link(session_id: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(session_id=session_id, has_password=False)


def test_stored_shape_user_and_assistant_records_render_with_bodies() -> None:
    manager = _RecordingHistory()

    async def seed() -> None:
        await manager.add_message(sender="user", text="how do I deploy?", session_id="shared-1")
        await manager.add_message(sender="assistant", text="run code-sync", session_id="shared-1")

    asyncio.run(seed())

    result = asyncio.run(_load_session_data(_link("shared-1"), _fake_request(manager)))

    messages = result["data"]["messages"]
    assert len(messages) == 2
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert [m["content"] for m in messages] == ["how do I deploy?", "run code-sync"]


def test_the_writer_really_does_use_the_stored_shape_keys() -> None:
    """Precondition: cannot pass if the mismatch is already absent."""
    manager = _RecordingHistory()
    asyncio.run(manager.add_message(sender="user", text="hi", session_id="shared-precond"))

    stored = asyncio.run(manager.get_session_messages("shared-precond", limit=500))

    assert "role" not in stored[0]
    assert "content" not in stored[0]
    assert stored[0]["sender"] == "user"
    assert stored[0]["text"] == "hi"


def test_non_conversational_speakers_stay_excluded_from_the_public_view() -> None:
    """The filter's intent — keep terminal/workflow-state records out of a
    public share — must survive resolving the key mismatch."""
    manager = _RecordingHistory()

    async def seed() -> None:
        await manager.add_message(sender="user", text="run ls", session_id="shared-2")
        await manager.add_message(sender="terminal", text="$ ls -la", session_id="shared-2")
        await manager.add_message(sender="workflow-error", text="step failed", session_id="shared-2")

    asyncio.run(seed())

    result = asyncio.run(_load_session_data(_link("shared-2"), _fake_request(manager)))

    roles = {m["role"] for m in result["data"]["messages"]}
    assert roles == {"user"}


def test_a_session_with_no_messages_still_renders_empty_without_error() -> None:
    manager = _RecordingHistory()

    result = asyncio.run(_load_session_data(_link("shared-empty"), _fake_request(manager)))

    assert result["data"]["messages"] == []
