# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for Issue #13220 — metadata updates crashed on
``"metadata": null``.

``_build_message_dict`` writes ``"metadata": raw_data``, and ``raw_data``
defaults to ``None``, so most persisted messages carry the ``metadata`` key with
an explicit ``null`` value (8 of 12 on the reported live session). Both readers
tested *presence* rather than *value*:

- ``_message_matches_filter``: ``message.get("metadata", {})`` returns the
  explicit ``None`` — a ``dict.get`` default only applies when the key is
  **absent** — so ``None.get(key)`` raised
  ``'NoneType' object has no attribute 'get'``.
- ``_apply_metadata_updates``: ``"metadata" not in message`` is False when the
  key exists with a ``null`` value, so the guard passed and ``None.update()``
  raised.

``update_message_metadata`` swallows both, so approval status and tool markers
went missing silently.

Every test here uses a message with ``metadata`` **present and null** — not
merely absent — which is the case the old guards let through.

This is the third instance of the #12778/#12782 pattern: presence is not
usability, so guards must test the value.
"""

import asyncio
from typing import Any, Dict, List

from chat_history.messages import MessagesMixin

NULL_METADATA_MESSAGE: Dict[str, Any] = {
    "id": "11111111-2222-3333-4444-555555555555",
    "sender": "user",
    "text": "hello",
    "messageType": "default",
    "metadata": None,
    "timestamp": "2026-01-01 00:00:00",
    "sources": [],
}


class _RecordingHistory(MessagesMixin):
    """Exercises the real metadata mixin against an in-memory session store."""

    def __init__(self, sessions: Dict[str, List[Dict[str, Any]]]) -> None:
        self.history: List[Dict[str, Any]] = []
        self.sessions = sessions

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        return self.sessions.get(session_id, [])

    async def save_session(self, session_id: str, messages: List[Dict[str, Any]], **_: Any) -> bool:
        self.sessions[session_id] = messages
        return True


def test_filter_tolerates_metadata_present_and_null() -> None:
    """A null metadata value must not raise; it simply matches nothing."""
    manager = _RecordingHistory({})
    message = dict(NULL_METADATA_MESSAGE)

    assert manager._message_matches_filter(message, {"requires_approval": True}) is False
    # An empty filter matches everything, including a null-metadata message.
    assert manager._message_matches_filter(message, {}) is True


def test_apply_updates_replaces_null_metadata() -> None:
    """A null metadata value is replaced with a dict before updating."""
    manager = _RecordingHistory({})
    message = dict(NULL_METADATA_MESSAGE)
    assert "metadata" in message and message["metadata"] is None

    manager._apply_metadata_updates(message, {"approval_status": "approved"})

    assert message["metadata"] == {"approval_status": "approved"}


def test_apply_updates_preserves_existing_metadata() -> None:
    """Existing metadata keys survive an update — the fix must not clobber."""
    manager = _RecordingHistory({})
    message = dict(NULL_METADATA_MESSAGE, metadata={"terminal_session_id": "term-1"})

    manager._apply_metadata_updates(message, {"approval_status": "denied"})

    assert message["metadata"] == {
        "terminal_session_id": "term-1",
        "approval_status": "denied",
    }


def test_update_message_metadata_over_a_session_with_null_metadata() -> None:
    """The approval-status write succeeds when earlier messages have null metadata.

    Mirrors the live session in the report: the target message is preceded by
    messages persisted with ``"metadata": null``. Before the fix the filter
    raised on the very first of those and ``update_message_metadata`` returned
    False, so the approval status was never recorded.
    """
    target = {
        "id": "66666666-7777-8888-9999-000000000000",
        "sender": "assistant",
        "text": "Approve `ls -la`?",
        "messageType": "command_approval_request",
        "metadata": {"terminal_session_id": "term-1", "requires_approval": True},
        "timestamp": "2026-01-01 00:00:01",
        "sources": [],
    }
    sessions = {"session-13220": [dict(NULL_METADATA_MESSAGE), target]}
    manager = _RecordingHistory(sessions)

    updated = asyncio.run(
        manager.update_message_metadata(
            session_id="session-13220",
            metadata_filter={"terminal_session_id": "term-1", "requires_approval": True},
            metadata_updates={"approval_status": "approved", "approved_by": "alice"},
        )
    )

    assert updated is True
    stored = sessions["session-13220"][1]
    assert stored["metadata"]["approval_status"] == "approved"
    assert stored["metadata"]["approved_by"] == "alice"
    assert stored["metadata"]["requires_approval"] is True
