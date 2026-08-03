# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for Issue #13214 — streamed AutoBot replies must survive reload.

The GUI reloads a conversation from the chat-history store (``chat:session:*``,
served by ``GET /api/chat/sessions/{id}``). The streaming endpoint
(``POST /api/chats/{id}/message``) has no persistence call of its own — it relies
on the workflow's ``_persist_workflow_messages``.

Every LLM chunk that workflow emits is stamped ``metadata.streaming = True`` by
``StreamingMessage.to_workflow_message`` and is therefore dropped by both
accumulators (``graph._run_llm_iteration`` and
``ChatWorkflowManager._collect_llm_iteration_response``), whose comments state the
complete reply "is persisted in _persist_workflow_messages". It was not: the
``llm_response`` argument was accepted and ignored, so a plain conversational turn
wrote an empty batch and the session read back user-turns only.

These tests assert the assistant turn is actually READABLE back out of the store
after a streamed reply — not merely that a write was attempted.
"""

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from chat_history.messages import MessagesMixin
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.models import StreamingMessage

SESSION_ID = "sess-13214"
REPLY = "Hello! I'm AutoBot. How can I help you today?"


class _InMemoryChatHistory(MessagesMixin):
    """Chat-history store backed by a dict.

    Deliberately reuses the REAL ``MessagesMixin`` so ``_build_message_dict`` and
    ``add_messages_batch`` are production code; only the load/save seam is
    in-memory. Reads therefore go through the same path the GUI's
    ``get_session_messages`` uses.
    """

    def __init__(self) -> None:
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self.sessions.get(session_id, []))

    async def save_session(self, session_id: str, messages=None, **_kwargs) -> bool:
        self.sessions[session_id] = list(messages or [])
        return True


@pytest.fixture
def store(monkeypatch):
    """Patch the store ``_persist_workflow_messages`` constructs internally."""
    instance = _InMemoryChatHistory()
    monkeypatch.setattr("chat_history.ChatHistoryManager", lambda: instance)
    return instance


def _manager() -> ChatWorkflowManager:
    """A manager instance without running the heavyweight __init__.

    ``_persist_workflow_messages`` touches no instance state beyond the helper it
    calls, so bypassing __init__ keeps the test free of Redis/LLM wiring.
    """
    return ChatWorkflowManager.__new__(ChatWorkflowManager)


def _assistant_turns(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [m for m in messages if m.get("sender") == "assistant"]


class TestStreamingDropsEveryChunk:
    """Establishes the precondition: streamed chunks never reach workflow_messages."""

    def test_streaming_metadata_is_always_set(self):
        """Production code stamps streaming=True on every chunk — not a test literal."""
        msg = StreamingMessage(type="response")
        msg.stream(REPLY)
        assert msg.to_workflow_message().metadata["streaming"] is True

    @pytest.mark.asyncio
    async def test_graph_iteration_accumulates_nothing_from_a_streamed_reply(self, monkeypatch):
        """``graph._run_llm_iteration`` returns an EMPTY message list for a streamed turn."""
        from chat_workflow import graph as graph_mod

        monkeypatch.setattr("autobot_shared.http_client.get_http_client", lambda: object())

        streaming_msg = StreamingMessage(type="response")

        class _FakeManager:
            async def _run_continuation_loop_iteration(self, _client, _prompt, _iteration, _ctx):
                for chunk in ("Hello! ", "I'm AutoBot. ", "How can I help you today?"):
                    streaming_msg.stream(chunk)
                    yield streaming_msg.to_workflow_message()
                yield (REPLY, False)

        ctx = SimpleNamespace(initial_prompt="hello")
        messages, llm_response, should_continue = await graph_mod._run_llm_iteration(_FakeManager(), ctx, 1, [], None)

        assert messages == []  # every chunk dropped — nothing left to persist
        assert llm_response == REPLY  # the complete reply IS known here
        assert should_continue is False


class TestStreamedReplyIsReadableAfterReload:
    """The regression: the assistant turn must be readable from the GUI-facing store."""

    @pytest.mark.asyncio
    async def test_conversational_streamed_reply_is_persisted(self, store):
        """FAILS pre-fix: batch is empty, so the session reads back with zero turns."""
        await ChatWorkflowManager._persist_workflow_messages(_manager(), SESSION_ID, [], [REPLY])

        persisted = await store.load_session(SESSION_ID)
        assistant = _assistant_turns(persisted)
        assert len(assistant) == 1
        assert assistant[0]["text"] == REPLY
        assert assistant[0]["messageType"] == "response"

    @pytest.mark.asyncio
    async def test_end_to_end_stream_then_reload(self, store, monkeypatch):
        """Drive the real graph accumulator, then persist, then read the store back."""
        from chat_workflow import graph as graph_mod

        monkeypatch.setattr("autobot_shared.http_client.get_http_client", lambda: object())

        streaming_msg = StreamingMessage(type="response")

        class _FakeManager:
            async def _run_continuation_loop_iteration(self, _client, _prompt, _iteration, _ctx):
                for chunk in ("Hello! ", "I'm AutoBot. ", "How can I help you today?"):
                    streaming_msg.stream(chunk)
                    yield streaming_msg.to_workflow_message()
                yield (REPLY, False)

        messages, llm_response, _ = await graph_mod._run_llm_iteration(
            _FakeManager(), SimpleNamespace(initial_prompt="hello"), 1, [], None
        )
        wf_messages = [
            SimpleNamespace(type=m.get("type", "response"), content=m.get("content", ""), metadata=m.get("metadata"))
            for m in messages
        ]

        await ChatWorkflowManager._persist_workflow_messages(_manager(), SESSION_ID, wf_messages, [llm_response])

        reloaded = await store.load_session(SESSION_ID)
        assert [m["text"] for m in _assistant_turns(reloaded)] == [REPLY]

    @pytest.mark.asyncio
    async def test_reply_precedes_its_own_iteration_tool_output(self, store):
        """Issue #13295 FIXED: a single-iteration tool turn reloads in live order.

        Live, the model's prose is generated (and streamed) BEFORE the tool
        call it contains is dispatched (``_run_continuation_iteration`` runs
        ``_yield_llm_response_and_check_stop`` before
        ``_yield_tool_results_and_decide``). When the loop stops after that
        one tool call (no second LLM pass), true order is prose -> tool
        output — the reverse of the old flat "all tool output, then the
        whole reply" batch, which a prior fix attempt (#13303 review) showed
        cannot be produced by a single front/back insertion point. The tool
        message's ``metadata.iteration`` (stamped by
        ``_handle_tool_message_types``) is what lets ``_build_persist_batch``
        place it after the prose that introduced it.
        """
        wf_messages = [
            SimpleNamespace(type="terminal_output", content="uptime: 3 days", metadata={"iteration": 1}),
        ]

        await ChatWorkflowManager._persist_workflow_messages(_manager(), SESSION_ID, wf_messages, [REPLY])

        persisted = await store.load_session(SESSION_ID)
        assert [m["sender"] for m in persisted] == ["assistant", "system"]
        assert persisted[0]["text"] == REPLY

    @pytest.mark.asyncio
    async def test_two_iteration_turn_reload_order_matches_live_order(self, store):
        """Issue #13295 FIXED: a genuine 2-iteration tool turn reloads in live order.

        iteration 1: model streams "Let me check." then calls a tool (tagged
        ``metadata.iteration = 1`` on the persisted terminal_output).
        iteration 2 (continuation, AFTER the tool result comes back): model
        streams "Uptime is 3 days." — the actual answer, no further tool call.
        Live order is prose1 -> tool output -> prose2. Previously (#13303),
        both prose segments collapsed into one joined string with a single
        insertion point, which could only match ONE of the single-iteration
        or 2-iteration cases at a time — not both. ``_persist_workflow_messages``
        now takes the per-iteration response list directly and interleaves
        using each message's iteration tag.
        """
        wf_messages = [
            SimpleNamespace(type="terminal_output", content="uptime: 3 days", metadata={"iteration": 1}),
        ]
        all_llm_responses = ["Let me check.", "Uptime is 3 days."]

        await ChatWorkflowManager._persist_workflow_messages(_manager(), SESSION_ID, wf_messages, all_llm_responses)

        persisted = await store.load_session(SESSION_ID)
        assert [(m["sender"], m["text"]) for m in persisted] == [
            ("assistant", "Let me check."),
            ("system", "uptime: 3 days"),
            ("assistant", "Uptime is 3 days."),
        ]


class TestNoDuplicateOrEmptyTurns:
    """The new write must not duplicate an existing turn or invent an empty one."""

    @pytest.mark.asyncio
    async def test_empty_llm_response_writes_nothing(self, store):
        await ChatWorkflowManager._persist_workflow_messages(_manager(), SESSION_ID, [], [""])
        assert await store.load_session(SESSION_ID) == []

    @pytest.mark.asyncio
    async def test_identical_existing_turn_is_not_duplicated(self, store):
        """The ``respond`` tool already emits a non-streaming turn with this text.

        Issue #13295: the duplicate is produced in the SAME iteration as the
        prose it echoes — the dedup scan must see it even though it is
        persisted AFTER the prose entry in the corrected order.
        """
        wf_messages = [
            SimpleNamespace(type="response", content=REPLY, metadata={"message_type": "respond_tool", "iteration": 1})
        ]

        await ChatWorkflowManager._persist_workflow_messages(_manager(), SESSION_ID, wf_messages, [REPLY])

        persisted = await store.load_session(SESSION_ID)
        assert len(_assistant_turns(persisted)) == 1

    @pytest.mark.asyncio
    async def test_error_turn_persist_is_unchanged(self, store):
        """``_persist_error_turn`` passes ``all_llm_responses=[]`` — behaviour unchanged.

        Issue #13295: confirms the error-turn path (no completed response at
        all) still falls through to the flat, un-interleaved batch — every
        workflow_messages entry is appended via the leftover fallback exactly
        as the pre-#13295 code did.
        """
        wf_messages = [SimpleNamespace(type="error", content="The assistant could not respond.", metadata={})]

        await ChatWorkflowManager._persist_workflow_messages(_manager(), SESSION_ID, wf_messages, [])

        persisted = await store.load_session(SESSION_ID)
        assert len(persisted) == 1
        assert persisted[0]["text"] == "The assistant could not respond."


class TestFinalReplyCarriesModelAndCitations:
    """Issue #13292: the persisted turn must carry the same model badge and KB

    citations the (discarded) streaming chunks carried — not ``sources: []``
    and no ``model`` regardless of what was actually used to answer.
    """

    MODEL = "claude-sonnet-5"
    CITATIONS = [
        {"title": "Runbook", "source": "kb/runbook.md", "score": 0.91, "id": "chunk-1"},
    ]

    @pytest.mark.asyncio
    async def test_model_is_recorded_on_the_persisted_turn(self, store):
        """FAILS pre-fix: metadata has no 'model' key at all."""
        await ChatWorkflowManager._persist_workflow_messages(
            _manager(), SESSION_ID, [], [REPLY], selected_model=self.MODEL
        )

        persisted = await store.load_session(SESSION_ID)
        assert _assistant_turns(persisted)[0]["metadata"]["model"] == self.MODEL

    @pytest.mark.asyncio
    async def test_kb_citations_become_sources_when_knowledge_was_used(self, store):
        """FAILS pre-fix: sources is always [] no matter what rag_citations held."""
        await ChatWorkflowManager._persist_workflow_messages(
            _manager(),
            SESSION_ID,
            [],
            [REPLY],
            selected_model=self.MODEL,
            rag_citations=self.CITATIONS,
            used_knowledge=True,
        )

        persisted = await store.load_session(SESSION_ID)
        sources = _assistant_turns(persisted)[0]["sources"]
        assert sources == [{"title": "Runbook", "path": "kb/runbook.md", "score": 0.91, "chunk_id": "chunk-1"}]

    @pytest.mark.asyncio
    async def test_citations_omitted_when_knowledge_was_not_used(self, store):
        """used_knowledge=False must not leak stale/irrelevant citations into sources."""
        await ChatWorkflowManager._persist_workflow_messages(
            _manager(),
            SESSION_ID,
            [],
            [REPLY],
            selected_model=self.MODEL,
            rag_citations=self.CITATIONS,
            used_knowledge=False,
        )

        persisted = await store.load_session(SESSION_ID)
        assert _assistant_turns(persisted)[0]["sources"] == []
