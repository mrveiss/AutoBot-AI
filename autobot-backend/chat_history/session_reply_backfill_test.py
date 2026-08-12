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

``chat:conversation:{id}`` (the short-lived ``{user, assistant}`` pair cache
used for LLM context) and ``data/conversation_transcripts/{id}.json`` (the
durable file transcript) are both written by ``_persist_conversation``
regardless of the bug, and are the two sources this module backfills from —
Redis first (fast, likely TTL-expired for anything old enough to need this),
falling back to the transcript file (the actual source of truth once Redis
has expired).

These tests prove ``repair_session``/``compute_backfilled_messages`` correctly
reconstructs damaged sessions from both sources, correctly identifies a
"damaged" turn by scanning its full message window (not just the next slot —
a healthy tool-using turn is ``[user, system, assistant]`` and must not be
misjudged damaged), and leaves already-healthy sessions/turns untouched.

This is a repair PATH, not a live run: every test below uses an in-memory
fake Redis client, a real ``MessagesMixin``-backed in-memory store, and (for
the transcript-fallback tests) a ``tmp_path``-scoped transcript directory —
nothing here touches a real Redis instance or production filesystem.
"""

import json
from typing import Any, Dict, List

import pytest

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


class _FakeAsyncRedis:
    """Minimal async Redis stand-in exposing only ``.get`` (what repair_session uses)."""

    def __init__(self, values: Dict[str, str] | None = None) -> None:
        self.values = values or {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)


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


class TestRepairSessionEndToEnd:
    """Exercises the Redis-read + transcript-fallback + load/save seam repair_session owns."""

    @pytest.mark.asyncio
    async def test_damaged_session_is_backfilled_from_redis_and_saved(self):
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("What is the deploy status?")]})
        redis_client = _FakeAsyncRedis(
            {"chat:conversation:sess-13293": ('[{"user": "What is the deploy status?", "assistant": "All green."}]')}
        )

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)

        assert count == 1
        saved = chat_mgr.sessions[SESSION_ID]
        assert [m["sender"] for m in saved] == ["user", "assistant"]
        assert saved[1]["text"] == "All green."
        assert saved[1]["sources"] == []
        assert saved[1]["metadata"]["backfilled_from"] == "chat:conversation"

    @pytest.mark.asyncio
    async def test_healthy_tool_turn_is_not_double_posted_end_to_end(self):
        """#13303 review: the double-post bug reproduced against the full seam."""
        original = [
            _user("what is uptime?"),
            _system("uptime: 3 days"),
            _assistant("Uptime is 3 days."),
        ]
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: list(original)})
        redis_client = _FakeAsyncRedis(
            {"chat:conversation:sess-13293": '[{"user": "what is uptime?", "assistant": "Uptime is 3 days."}]'}
        )

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)

        assert count == 0
        assert chat_mgr.sessions[SESSION_ID] == original

    @pytest.mark.asyncio
    async def test_healthy_session_is_not_saved(self):
        """No write at all when nothing needed repair — avoids no-op session churn."""
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("hi"), _assistant("hello")]})
        redis_client = _FakeAsyncRedis({"chat:conversation:sess-13293": '[{"user": "hi", "assistant": "hello"}]'})
        original = list(chat_mgr.sessions[SESSION_ID])

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)

        assert count == 0
        assert chat_mgr.sessions[SESSION_ID] == original

    @pytest.mark.asyncio
    async def test_expired_redis_key_falls_back_to_transcript_file(self, tmp_path):
        """Blocker #3: chat:conversation:* TTL'd out — repair must still succeed from disk."""
        transcript_dir = _write_transcript(
            tmp_path, SESSION_ID, [{"user": "What is the deploy status?", "assistant": "All green."}]
        )
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("What is the deploy status?")]})
        redis_client = _FakeAsyncRedis({})  # key absent — simulates TTL expiry

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client, transcript_dir=transcript_dir)

        assert count == 1
        saved = chat_mgr.sessions[SESSION_ID]
        assert [m["sender"] for m in saved] == ["user", "assistant"]
        assert saved[1]["text"] == "All green."

    @pytest.mark.asyncio
    async def test_no_redis_client_available_falls_back_to_transcript_file(self, tmp_path, monkeypatch):
        """Redis fully unavailable (get_async_redis_client() -> None) — must still repair from disk."""

        async def _no_redis(database: str = "main"):
            return None

        monkeypatch.setattr("chat_history.session_reply_backfill.get_async_redis_client", _no_redis)
        transcript_dir = _write_transcript(tmp_path, SESSION_ID, [{"user": "hi", "assistant": "hello there"}])
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("hi")]})

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=None, transcript_dir=transcript_dir)

        assert count == 1
        assert chat_mgr.sessions[SESSION_ID][1]["text"] == "hello there"

    @pytest.mark.asyncio
    async def test_no_redis_client_and_no_transcript_does_not_raise(self, tmp_path, monkeypatch):
        async def _no_redis(database: str = "main"):
            return None

        monkeypatch.setattr("chat_history.session_reply_backfill.get_async_redis_client", _no_redis)
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("hi")]})

        count = await repair_session(
            SESSION_ID, chat_mgr, redis_client=None, transcript_dir=str(tmp_path / "does-not-exist")
        )

        assert count == 0

    @pytest.mark.asyncio
    async def test_redis_pair_preferred_over_transcript_when_both_present(self, tmp_path):
        """Redis is the fast path — used first when it has the answer, transcript untouched."""
        transcript_dir = _write_transcript(tmp_path, SESSION_ID, [{"user": "hi", "assistant": "stale transcript"}])
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("hi")]})
        redis_client = _FakeAsyncRedis({"chat:conversation:sess-13293": '[{"user": "hi", "assistant": "fresh redis"}]'})

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client, transcript_dir=transcript_dir)

        assert count == 1
        assert chat_mgr.sessions[SESSION_ID][1]["text"] == "fresh redis"

    @pytest.mark.asyncio
    async def test_no_source_available_is_a_no_op(self, tmp_path):
        """Neither Redis nor a transcript file exists — nothing to repair from, no error."""
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("orphaned")]})
        redis_client = _FakeAsyncRedis({})

        count = await repair_session(
            SESSION_ID, chat_mgr, redis_client=redis_client, transcript_dir=str(tmp_path / "does-not-exist")
        )

        assert count == 0
        assert SESSION_ID in chat_mgr.sessions  # unchanged, not deleted

    @pytest.mark.asyncio
    async def test_malformed_conversation_payload_falls_back_to_transcript(self, tmp_path):
        transcript_dir = _write_transcript(tmp_path, SESSION_ID, [{"user": "hi", "assistant": "from transcript"}])
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("hi")]})
        redis_client = _FakeAsyncRedis({"chat:conversation:sess-13293": "{not valid json"})

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client, transcript_dir=transcript_dir)

        assert count == 1
        assert chat_mgr.sessions[SESSION_ID][1]["text"] == "from transcript"

    @pytest.mark.asyncio
    async def test_unknown_session_is_a_no_op(self):
        chat_mgr = _InMemoryChatHistory(sessions={})
        redis_client = _FakeAsyncRedis({"chat:conversation:sess-13293": '[{"user": "hi", "assistant": "hi back"}]'})

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)

        assert count == 0
        assert SESSION_ID not in chat_mgr.sessions

    @pytest.mark.asyncio
    async def test_repair_twice_is_idempotent_end_to_end(self):
        """Blocker D: calling repair_session twice must not duplicate the backfilled turn."""
        chat_mgr = _InMemoryChatHistory(sessions={SESSION_ID: [_user("what is uptime?"), _system("uptime: 3 days")]})
        redis_client = _FakeAsyncRedis(
            {"chat:conversation:sess-13293": '[{"user": "what is uptime?", "assistant": "Uptime is 3 days."}]'}
        )

        first = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)
        second = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)

        assert first == 1
        assert second == 0
        assert [m["sender"] for m in chat_mgr.sessions[SESSION_ID]] == ["user", "system", "assistant"]
