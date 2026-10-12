# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for Issue #13293 — repair chat:session:* turns damaged by #13214.

Before #13214 merged, a completed streamed reply was computed and shown to
the user but never persisted to ``chat:session:{id}``: the batch that
``_persist_workflow_messages`` wrote held only non-streaming side messages, so
a plain conversational turn wrote an empty batch and the session reads back
with the user's message and no assistant reply.

The reply survives in the legacy per-turn transcript
(``data/conversation_transcripts/{id}.json``), which ``_persist_conversation``
wrote regardless of the bug until #18293 retired it. ``chat_sessions`` is the
system of record; the transcript is the read-only legacy witness this module
backfills from. ``chat:conversation:{id}`` is no longer read: since #18293 it is
re-projected from ``chat_sessions``, so it cannot hold a reply that store lacks.

These tests prove ``repair_session``/``compute_backfilled_messages`` correctly
reconstructs damaged sessions from the transcript, correctly identifies a
"damaged" turn by scanning its full message window (not just the next slot —
a healthy tool-using turn is ``[user, system, assistant]`` and must not be
misjudged damaged), and leaves already-healthy sessions/turns untouched.

This is a repair PATH, not a live run: every test below uses a real
``MessagesMixin``-backed in-memory store and a ``tmp_path``-scoped transcript
directory — nothing here touches Redis or the production filesystem.
"""

import json
from typing import Any, Dict, List

import pytest

import chat_history.session_reply_backfill as backfill_module
from chat_history.messages import MessagesMixin
from chat_history.session_reply_backfill import (
    compute_backfilled_messages,
    repair_session,
)

SESSION_ID = "sess-13293"


def _user(text: str) -> Dict[str, Any]:
    return {"sender": "user", "text": text, "messageType": "default"}


def _assistant(text: str, sender: str = "assistant", **metadata: Any) -> Dict[str, Any]:
    return {"sender": sender, "text": text, "messageType": "response", "metadata": metadata}


def _system(text: str) -> Dict[str, Any]:
    return {"sender": "system", "text": text, "messageType": "terminal_output", "metadata": {}}


def _build_message(text: str) -> Dict[str, Any]:
    """Stand-in for chat_mgr._build_message_dict used directly by the pure-logic tests."""
    return {"sender": "assistant", "text": text, "messageType": "response", "sources": []}


class TestComputeBackfilledMessagesPureLogic:
    """No I/O — proves the matching/insertion algorithm in isolation."""

    def test_missing_reply_is_backfilled_from_matching_pair(self):
        session_messages = [_user("What is the deploy status?")]
        conversation_pairs = [{"user": "What is the deploy status?", "assistant": "All green."}]

        repaired, count = compute_backfilled_messages(session_messages, conversation_pairs, _build_message)

        assert count == 1
        assert [m["sender"] for m in repaired] == ["user", "assistant"]
        assert repaired[1]["text"] == "All green."

    def test_healthy_turn_is_left_untouched(self):
        """A user turn already followed by an assistant reply is never touched."""
        session_messages = [_user("hi"), _assistant("hello there")]
        conversation_pairs = [{"user": "hi", "assistant": "hello there"}]

        repaired, count = compute_backfilled_messages(session_messages, conversation_pairs, _build_message)

        assert count == 0
        assert repaired == session_messages

    def test_healthy_tool_turn_with_system_entry_is_not_double_posted(self):
        """#13303 review finding: [user, system, assistant] must NOT be judged damaged.

        A next-slot-only check sees repaired[i+1] == "system" (not "assistant")
        and wrongly inserts a duplicate reply. The fix scans the whole turn
        window (up to the next user message) for ANY assistant entry.
        """
        session_messages = [
            _user("what is uptime?"),
            _system("uptime: 3 days"),
            _assistant("Uptime is 3 days."),
        ]
        conversation_pairs = [{"user": "what is uptime?", "assistant": "Uptime is 3 days."}]

        repaired, count = compute_backfilled_messages(session_messages, conversation_pairs, _build_message)

        assert count == 0
        assert repaired == session_messages

    def test_damaged_tool_turn_is_backfilled_after_the_system_entry(self):
        """A genuinely damaged tool turn ([user, system], no reply) is backfilled

        AFTER the system entry, not immediately after the user message —
        preserving the tool-output-then-reply order the turn actually has.
        """
        session_messages = [_user("what is uptime?"), _system("uptime: 3 days")]
        conversation_pairs = [{"user": "what is uptime?", "assistant": "Uptime is 3 days."}]

        repaired, count = compute_backfilled_messages(session_messages, conversation_pairs, _build_message)

        assert count == 1
        assert [m["sender"] for m in repaired] == ["user", "system", "assistant"]
        assert repaired[2]["text"] == "Uptime is 3 days."

    def test_multiple_damaged_turns_are_each_backfilled_in_order(self):
        session_messages = [_user("first question"), _user("second question")]
        conversation_pairs = [
            {"user": "first question", "assistant": "first answer"},
            {"user": "second question", "assistant": "second answer"},
        ]

        repaired, count = compute_backfilled_messages(session_messages, conversation_pairs, _build_message)

        assert count == 2
        assert [m["text"] for m in repaired] == [
            "first question",
            "first answer",
            "second question",
            "second answer",
        ]

    def test_mixed_session_only_damaged_turn_is_backfilled(self):
        """One turn survived (pre-existing reply), the other didn't — only the second is touched."""
        session_messages = [
            _user("first question"),
            _assistant("first answer"),
            _user("second question"),
        ]
        conversation_pairs = [
            {"user": "first question", "assistant": "first answer"},
            {"user": "second question", "assistant": "second answer"},
        ]

        repaired, count = compute_backfilled_messages(session_messages, conversation_pairs, _build_message)

        assert count == 1
        assert [m["text"] for m in repaired] == [
            "first question",
            "first answer",
            "second question",
            "second answer",
        ]

    def test_no_matching_conversation_pair_leaves_turn_damaged(self):
        """chat:conversation:*/transcript has nothing for this turn — nothing to backfill from."""
        session_messages = [_user("orphaned question")]
        conversation_pairs = [{"user": "unrelated question", "assistant": "unrelated answer"}]

        repaired, count = compute_backfilled_messages(session_messages, conversation_pairs, _build_message)

        assert count == 0
        assert repaired == session_messages

    def test_repeated_identical_user_text_consumes_pairs_in_order(self):
        """Two damaged turns with identical text must not both grab the same pair."""
        session_messages = [_user("status?"), _user("status?")]
        conversation_pairs = [
            {"user": "status?", "assistant": "answer one"},
            {"user": "status?", "assistant": "answer two"},
        ]

        repaired, count = compute_backfilled_messages(session_messages, conversation_pairs, _build_message)

        assert count == 2
        assert [m["text"] for m in repaired] == ["status?", "answer one", "status?", "answer two"]

    def test_empty_conversation_pairs_is_a_no_op(self):
        session_messages = [_user("hello")]
        repaired, count = compute_backfilled_messages(session_messages, [], _build_message)
        assert count == 0
        assert repaired == session_messages

    def test_idempotent_second_pass_backfills_nothing_more(self):
        """Running the repair twice must not duplicate the reply it just inserted."""
        session_messages = [_user("what is uptime?"), _system("uptime: 3 days")]
        conversation_pairs = [{"user": "what is uptime?", "assistant": "Uptime is 3 days."}]

        once, count_once = compute_backfilled_messages(session_messages, conversation_pairs, _build_message)
        twice, count_twice = compute_backfilled_messages(once, conversation_pairs, _build_message)

        assert count_once == 1
        assert count_twice == 0
        assert once == twice


class _InMemoryChatHistory(MessagesMixin):
    """In-memory chat-history store.

    Subclasses the REAL ``MessagesMixin`` (as ``streamed_reply_persistence_test.py``
    does) so ``_build_message_dict``/``add_messages_batch`` are production
    code — a hand-rolled duck-typed stub previously omitted ``author_id`` and
    only worked because ``sources`` was passed by keyword (#13303 review).
    """

    def __init__(self, sessions: Dict[str, List[Dict[str, Any]]] | None = None) -> None:
        self.sessions: Dict[str, List[Dict[str, Any]]] = sessions or {}

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self.sessions.get(session_id, []))

    async def save_session(self, session_id: str, messages=None, **_kwargs) -> bool:
        self.sessions[session_id] = list(messages or [])
        return True


def _write_transcript(tmp_path, session_id: str, exchanges: List[Dict[str, str]]) -> str:
    """Write a transcript JSON file matching ChatWorkflowManager's on-disk shape."""
    transcript_dir = tmp_path / "conversation_transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "messages": [{"timestamp": "2026-01-01 00:00:00", **exchange} for exchange in exchanges],
        "message_count": len(exchanges),
    }
    (transcript_dir / f"{session_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    return str(transcript_dir)


def _write_raw_transcript(tmp_path, session_id: str, content: str):
    """Write *content* verbatim as a transcript file; returns its path."""
    transcript_dir = tmp_path / "conversation_transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    path = transcript_dir / f"{session_id}.json"
    path.write_text(content, encoding="utf-8")
    return path


def _read_raw(path) -> str:
    return path.read_text(encoding="utf-8")


class TestRepairSessionEndToEnd:
    """Exercises the transcript-read + load/save seam repair_session owns."""

    @pytest.mark.asyncio
    async def test_damaged_session_is_backfilled_from_transcript_and_saved(self, tmp_path):
        transcript_dir = _write_transcript(
            tmp_path, SESSION_ID, [{"user": "What is the deploy status?", "assistant": "All green."}]
        )
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("What is the deploy status?")]})

        count = await repair_session(SESSION_ID, chat_mgr, transcript_dir=transcript_dir)

        assert count == 1
        saved = chat_mgr.sessions[SESSION_ID]
        assert [m["sender"] for m in saved] == ["user", "assistant"]
        assert saved[1]["text"] == "All green."
        assert saved[1]["sources"] == []
        assert saved[1]["metadata"]["backfilled_from"] == "legacy_conversation_transcripts"

    @pytest.mark.asyncio
    async def test_healthy_tool_turn_is_not_double_posted_end_to_end(self, tmp_path):
        """#13303 review: the double-post bug reproduced against the full seam."""
        original = [
            _user("what is uptime?"),
            _system("uptime: 3 days"),
            _assistant("Uptime is 3 days."),
        ]
        transcript_dir = _write_transcript(
            tmp_path, SESSION_ID, [{"user": "what is uptime?", "assistant": "Uptime is 3 days."}]
        )
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: list(original)})

        count = await repair_session(SESSION_ID, chat_mgr, transcript_dir=transcript_dir)

        assert count == 0
        assert chat_mgr.sessions[SESSION_ID] == original

    @pytest.mark.asyncio
    async def test_healthy_session_is_not_saved(self, tmp_path):
        """No write at all when nothing needed repair — avoids no-op session churn."""
        transcript_dir = _write_transcript(tmp_path, SESSION_ID, [{"user": "hi", "assistant": "hello"}])
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("hi"), _assistant("hello")]})
        original = list(chat_mgr.sessions[SESSION_ID])

        count = await repair_session(SESSION_ID, chat_mgr, transcript_dir=transcript_dir)

        assert count == 0
        assert chat_mgr.sessions[SESSION_ID] == original

    @pytest.mark.asyncio
    async def test_no_transcript_is_a_no_op(self, tmp_path):
        """No transcript file exists — nothing to repair from, no error, session untouched."""
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("orphaned")]})

        count = await repair_session(SESSION_ID, chat_mgr, transcript_dir=str(tmp_path / "does-not-exist"))

        assert count == 0
        assert chat_mgr.sessions[SESSION_ID] == [_user("orphaned")]

    @pytest.mark.asyncio
    async def test_malformed_transcript_is_a_no_op_and_left_in_place(self, tmp_path):
        bad = _write_raw_transcript(tmp_path, SESSION_ID, "{not valid json")
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("hi")]})

        count = await repair_session(SESSION_ID, chat_mgr, transcript_dir=str(bad.parent))

        assert count == 0
        assert _read_raw(bad) == "{not valid json"  # never renamed or rewritten

    @pytest.mark.asyncio
    async def test_session_with_no_chat_sessions_turns_is_not_created(self, tmp_path):
        """A B-only session is served read-only for LLM context, never moved by this repair."""
        transcript_dir = _write_transcript(tmp_path, SESSION_ID, [{"user": "hi", "assistant": "hi back"}])
        chat_mgr = _InMemoryChatHistory(sessions={})

        count = await repair_session(SESSION_ID, chat_mgr, transcript_dir=transcript_dir)

        assert count == 0
        assert SESSION_ID not in chat_mgr.sessions

    @pytest.mark.asyncio
    async def test_repair_twice_is_idempotent_end_to_end(self, tmp_path):
        """Blocker D: calling repair_session twice must not duplicate the backfilled turn."""
        transcript_dir = _write_transcript(
            tmp_path, SESSION_ID, [{"user": "what is uptime?", "assistant": "Uptime is 3 days."}]
        )
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("what is uptime?"), _system("uptime: 3 days")]})

        first = await repair_session(SESSION_ID, chat_mgr, transcript_dir=transcript_dir)
        second = await repair_session(SESSION_ID, chat_mgr, transcript_dir=transcript_dir)

        assert first == 1
        assert second == 0
        assert [m["sender"] for m in chat_mgr.sessions[SESSION_ID]] == ["user", "system", "assistant"]

    def test_the_llm_context_cache_is_not_a_witness(self):
        """#18293: chat:conversation:* is re-projected from chat_sessions, so it is never read here."""
        assert not hasattr(backfill_module, "get_async_redis_client")
        assert "redis_client" not in repair_session.__code__.co_varnames
