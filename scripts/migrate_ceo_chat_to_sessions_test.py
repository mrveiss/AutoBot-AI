# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the ceo_chat -> chat_history forward data migration (#12009).

Uses an in-memory FakeManager (duck-typed to ChatHistoryManager's
get_session/create_session/update_session_metadata/add_messages_batch) so
these tests exercise the migration logic without a real Postgres or
chat_history file store.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate_ceo_chat_to_sessions import (  # noqa: E402
    _build_migrated_message,
    _build_session_metadata,
    _migrate_thread,
    _role_for_author_type,
    _verify_counts,
    session_id_for_thread,
)


class FakeManager:
    """In-memory stand-in for ChatHistoryManager's session/message API."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []

    async def get_session(self, session_id: str):
        self.calls.append(f"get_session:{session_id}")
        return self.sessions.get(session_id)

    async def create_session(self, session_id: str, title: str | None = None, metadata: dict | None = None):
        self.calls.append(f"create_session:{session_id}")
        self.sessions[session_id] = {"id": session_id, "title": title, "metadata": {}, "messages": []}
        return self.sessions[session_id]

    async def update_session_metadata(self, session_id: str, metadata: dict) -> bool:
        self.calls.append(f"update_session_metadata:{session_id}")
        self.sessions[session_id]["metadata"].update(metadata)
        return True

    async def add_messages_batch(self, session_id: str, messages: list[dict]) -> bool:
        self.calls.append(f"add_messages_batch:{session_id}:{len(messages)}")
        self.sessions[session_id]["messages"].extend(messages)
        return True


def _make_thread(**overrides: Any) -> dict:
    thread = {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "title": "Q3 hiring plan",
        "resolved_entity_type": "sprint",
        "resolved_entity_id": uuid.uuid4(),
        "created_by_user_id": uuid.uuid4(),
        "created_at": datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 5, 12, 30, 0, tzinfo=timezone.utc),
    }
    thread.update(overrides)
    return thread


def _make_message(author_type: str, body: str, **overrides: Any) -> dict:
    msg = {
        "id": uuid.uuid4(),
        "thread_id": uuid.uuid4(),
        "author_type": author_type,
        "author_user_id": uuid.uuid4(),
        "body": body,
        "created_at": datetime(2026, 1, 5, 12, 5, 0, tzinfo=timezone.utc),
    }
    msg.update(overrides)
    return msg


# --------------------------------------------------------------------------
# author_type -> role mapping
# --------------------------------------------------------------------------


def test_role_for_author_type_human_is_user():
    assert _role_for_author_type("human") == "user"


def test_role_for_author_type_system_is_assistant():
    assert _role_for_author_type("system") == "assistant"


def test_role_for_author_type_unknown_defaults_to_user(caplog):
    with caplog.at_level("WARNING"):
        role = _role_for_author_type("robot")
    assert role == "user"
    assert "Unknown ceo_chat author_type" in caplog.text


# --------------------------------------------------------------------------
# deterministic session id / metadata / message shape
# --------------------------------------------------------------------------


def test_session_id_for_thread_is_deterministic():
    thread_id = uuid.uuid4()
    assert session_id_for_thread(thread_id) == f"ceochat-{thread_id}"
    assert session_id_for_thread(thread_id) == session_id_for_thread(thread_id)


def test_build_session_metadata_carries_owner_and_source_fields():
    thread = _make_thread()
    metadata = _build_session_metadata(thread, "alice")

    assert metadata["owner"] == "alice"
    assert metadata["username"] == "alice"
    assert metadata["company_id"] == str(thread["company_id"])
    assert metadata["resolved_entity_type"] == "sprint"
    assert metadata["resolved_entity_id"] == str(thread["resolved_entity_id"])
    assert metadata["migrated_from"] == "ceo_chat"
    assert metadata["source_thread_id"] == str(thread["id"])
    assert metadata["created_at"] == thread["created_at"].isoformat()


def test_build_session_metadata_handles_null_resolved_entity():
    thread = _make_thread(resolved_entity_id=None, resolved_entity_type=None)
    metadata = _build_session_metadata(thread, "alice")
    assert metadata["resolved_entity_id"] is None
    assert metadata["resolved_entity_type"] is None


def test_build_migrated_message_maps_role_text_and_timestamp():
    msg = _make_message("human", "What's the plan?")
    built = _build_migrated_message(msg)

    assert built["sender"] == "user"
    assert built["text"] == "What's the plan?"
    assert built["timestamp"] == "2026-01-05 12:05:00"
    assert built["authorId"] == str(msg["author_user_id"])
    assert built["sources"] == []


def test_build_migrated_message_system_maps_to_assistant():
    msg = _make_message("system", "Here is the plan.")
    built = _build_migrated_message(msg)
    assert built["sender"] == "assistant"


# --------------------------------------------------------------------------
# _migrate_thread: dry-run, real write, idempotency, ownerless skip
# --------------------------------------------------------------------------


async def test_migrate_thread_dry_run_reports_counts_without_writing():
    manager = FakeManager()
    thread = _make_thread()
    messages = [_make_message("human", "hi"), _make_message("system", "hello")]

    outcome, added = await _migrate_thread(manager, thread, messages, "alice", dry_run=True)

    assert outcome == "created"
    assert added == 2
    assert manager.sessions == {}
    assert manager.calls == [f"get_session:{session_id_for_thread(thread['id'])}"]


async def test_migrate_thread_creates_session_and_messages():
    manager = FakeManager()
    thread = _make_thread()
    messages = [_make_message("human", "hi"), _make_message("system", "hello")]

    outcome, added = await _migrate_thread(manager, thread, messages, "alice", dry_run=False)

    session_id = session_id_for_thread(thread["id"])
    assert outcome == "created"
    assert added == 2
    assert manager.sessions[session_id]["metadata"]["owner"] == "alice"
    assert len(manager.sessions[session_id]["messages"]) == 2
    assert manager.sessions[session_id]["messages"][0]["sender"] == "user"
    assert manager.sessions[session_id]["messages"][1]["sender"] == "assistant"


async def test_migrate_thread_is_idempotent_on_rerun():
    manager = FakeManager()
    thread = _make_thread()
    messages = [_make_message("human", "hi")]

    first = await _migrate_thread(manager, thread, messages, "alice", dry_run=False)
    second = await _migrate_thread(manager, thread, messages, "alice", dry_run=False)

    session_id = session_id_for_thread(thread["id"])
    assert first == ("created", 1)
    assert second == ("skipped_existing", 0)
    assert len(manager.sessions[session_id]["messages"]) == 1  # not duplicated


async def test_migrate_thread_skips_ownerless_without_writing():
    manager = FakeManager()
    thread = _make_thread(created_by_user_id=None)
    messages = [_make_message("human", "hi")]

    outcome, added = await _migrate_thread(manager, thread, messages, None, dry_run=False)

    assert outcome == "skipped_ownerless"
    assert added == 0
    assert manager.sessions == {}
    assert manager.calls == []  # no get_session/create_session calls at all


# --------------------------------------------------------------------------
# verification
# --------------------------------------------------------------------------


def test_verify_counts_passes_when_accounted_for():
    counts = {
        "thread_count": 3,
        "sessions_created": 2,
        "skipped_existing": 1,
        "skipped_ownerless": 0,
        "errors": 0,
        "messages_added": 5,
        "messages_expected": 5,
    }
    _verify_counts(counts)  # must not raise


def test_verify_counts_raises_on_thread_mismatch():
    counts = {
        "thread_count": 3,
        "sessions_created": 1,
        "skipped_existing": 0,
        "skipped_ownerless": 0,
        "errors": 0,
        "messages_added": 0,
        "messages_expected": 0,
    }
    try:
        _verify_counts(counts)
    except AssertionError as exc:
        assert "Thread accounting mismatch" in str(exc)
    else:
        raise AssertionError("expected AssertionError for thread mismatch")


def test_verify_counts_raises_on_message_mismatch():
    counts = {
        "thread_count": 1,
        "sessions_created": 1,
        "skipped_existing": 0,
        "skipped_ownerless": 0,
        "errors": 0,
        "messages_added": 1,
        "messages_expected": 2,
    }
    try:
        _verify_counts(counts)
    except AssertionError as exc:
        assert "Message count mismatch" in str(exc)
    else:
        raise AssertionError("expected AssertionError for message mismatch")
