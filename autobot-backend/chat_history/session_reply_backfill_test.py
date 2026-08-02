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
used for LLM context, written by ``_persist_conversation`` regardless of the
bug) still has the missing text while it has not expired. These tests prove
``repair_session``/``compute_backfilled_messages`` correctly reconstructs the
damaged sessions from that source — and leaves already-healthy sessions and
turns untouched.

This is a repair PATH, not a live run: every test below uses an in-memory
fake Redis client and a fake chat-history store; nothing here touches a real
Redis instance or `chat_history.ChatHistoryManager`'s real I/O.
"""

from typing import Any, Dict, List

import pytest

from chat_history.session_reply_backfill import (
    compute_backfilled_messages,
    repair_session,
)

SESSION_ID = "sess-13293"


def _user(text: str) -> Dict[str, Any]:
    return {"sender": "user", "text": text, "messageType": "default"}


def _assistant(text: str, **metadata: Any) -> Dict[str, Any]:
    return {"sender": "assistant", "text": text, "messageType": "response", "metadata": metadata}


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
        """chat:conversation:* expired/never had this turn — nothing to backfill from."""
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


class _FakeAsyncRedis:
    """Minimal async Redis stand-in exposing only ``.get`` (what repair_session uses)."""

    def __init__(self, values: Dict[str, str] | None = None) -> None:
        self.values = values or {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)


class _FakeChatHistoryManager:
    """In-memory chat-history store exercising the real message-dict shape."""

    def __init__(self, sessions: Dict[str, List[Dict[str, Any]]] | None = None) -> None:
        self.sessions = sessions or {}
        self.saved: Dict[str, List[Dict[str, Any]]] = {}

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self.sessions.get(session_id, []))

    async def save_session(self, session_id: str, messages=None, **_kwargs) -> None:
        self.saved[session_id] = list(messages or [])
        self.sessions[session_id] = list(messages or [])

    def _build_message_dict(self, sender, text, message_type, raw_data, tool_markers, sources=None):
        return {
            "sender": sender,
            "text": text,
            "messageType": message_type,
            "metadata": raw_data,
            "sources": sources if sources is not None else [],
        }


class TestRepairSessionEndToEnd:
    """Exercises the Redis-read + load/save seam repair_session owns."""

    @pytest.mark.asyncio
    async def test_damaged_session_is_backfilled_and_saved(self):
        chat_mgr = _FakeChatHistoryManager(sessions={SESSION_ID: [_user("What is the deploy status?")]})
        redis_client = _FakeAsyncRedis(
            {"chat:conversation:sess-13293": ('[{"user": "What is the deploy status?", "assistant": "All green."}]')}
        )

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)

        assert count == 1
        saved = chat_mgr.saved[SESSION_ID]
        assert [m["sender"] for m in saved] == ["user", "assistant"]
        assert saved[1]["text"] == "All green."
        assert saved[1]["sources"] == []
        assert saved[1]["metadata"]["backfilled_from"] == "chat:conversation"

    @pytest.mark.asyncio
    async def test_healthy_session_is_not_saved(self):
        """No write at all when nothing needed repair — avoids no-op session churn."""
        chat_mgr = _FakeChatHistoryManager(sessions={SESSION_ID: [_user("hi"), _assistant("hello")]})
        redis_client = _FakeAsyncRedis({"chat:conversation:sess-13293": '[{"user": "hi", "assistant": "hello"}]'})

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)

        assert count == 0
        assert SESSION_ID not in chat_mgr.saved

    @pytest.mark.asyncio
    async def test_expired_conversation_key_is_a_no_op(self):
        """chat:conversation:* TTL'd out — nothing to repair from, must not error."""
        chat_mgr = _FakeChatHistoryManager(sessions={SESSION_ID: [_user("orphaned")]})
        redis_client = _FakeAsyncRedis({})  # key absent — simulates TTL expiry

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)

        assert count == 0
        assert SESSION_ID not in chat_mgr.saved

    @pytest.mark.asyncio
    async def test_malformed_conversation_payload_does_not_raise(self):
        chat_mgr = _FakeChatHistoryManager(sessions={SESSION_ID: [_user("hi")]})
        redis_client = _FakeAsyncRedis({"chat:conversation:sess-13293": "{not valid json"})

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)

        assert count == 0
        assert SESSION_ID not in chat_mgr.saved

    @pytest.mark.asyncio
    async def test_unknown_session_is_a_no_op(self):
        chat_mgr = _FakeChatHistoryManager(sessions={})
        redis_client = _FakeAsyncRedis({"chat:conversation:sess-13293": '[{"user": "hi", "assistant": "hi back"}]'})

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=redis_client)

        assert count == 0
        assert SESSION_ID not in chat_mgr.saved

    @pytest.mark.asyncio
    async def test_no_redis_client_available_does_not_raise(self, monkeypatch):
        """Simulates Redis being fully unavailable (get_async_redis_client() -> None)."""

        async def _no_redis(database: str = "main"):
            return None

        monkeypatch.setattr("chat_history.session_reply_backfill.get_async_redis_client", _no_redis)
        chat_mgr = _FakeChatHistoryManager(sessions={SESSION_ID: [_user("hi")]})

        count = await repair_session(SESSION_ID, chat_mgr, redis_client=None)

        assert count == 0
