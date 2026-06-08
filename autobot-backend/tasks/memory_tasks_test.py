# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for memory Celery tasks and lifecycle hooks (Issue #5073).

Covers:
- _async_write_verbatim: calls VerbatimStore.append with correct args.
- _async_extract_facts: delegates to KnowledgeExtractionAgent.
- _async_update_graph: writes entities/relations to AutoBotMemoryGraph.
- _async_compact_snapshot: persists pre-compaction snapshot to VerbatimStore.
- on_turn_complete (stop hook): enqueues all expected Celery tasks.
- on_pre_compact (compact hook): fires only at ≥ 85 % usage, not below.
- estimate_context_usage: correct fraction for known/unknown models.

Note: In the test environment Celery may not be installed, so the
``@celery_app.task`` decorator is stubbed as a passthrough.  Task invocation
is tested via the async helper functions directly, and the .delay() path is
tested via mocking the task objects in the hook modules.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _async_write_verbatim
# ---------------------------------------------------------------------------


class TestAsyncWriteVerbatim:
    """Unit tests for the async helper backing memory.write_verbatim."""

    @pytest.mark.asyncio
    async def test_calls_store_append_with_correct_args(self):
        """Should call VerbatimStore.append with correct session/turn/role/text."""
        fake_store = AsyncMock()
        fake_store.append = AsyncMock(return_value="sess_t0_user_abc12345")

        async def fake_get_store():
            return fake_store

        timestamp_iso = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()

        with patch("tasks.memory_tasks._async_write_verbatim") as patched:
            patched.return_value = asyncio.coroutine(lambda: "sess_t0_user_abc12345")() if False else None

        # Test by calling the real async helper with a mocked store
        with patch("memory.verbatim_store.get_verbatim_store", fake_get_store):
            from tasks.memory_tasks import _async_write_verbatim

            chunk_id = await _async_write_verbatim("sess-1", 0, "user", "Hello", timestamp_iso, "u1")

        fake_store.append.assert_called_once()
        call_kwargs = fake_store.append.call_args
        assert call_kwargs.kwargs.get("session_id") == "sess-1" or call_kwargs.args[0] == "sess-1"
        assert chunk_id == "sess_t0_user_abc12345"

    @pytest.mark.asyncio
    async def test_raises_on_store_failure(self):
        """Should propagate exceptions from VerbatimStore.append."""
        fake_store = AsyncMock()
        fake_store.append = AsyncMock(side_effect=RuntimeError("chroma down"))

        async def fake_get_store():
            return fake_store

        timestamp_iso = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()

        with patch("memory.verbatim_store.get_verbatim_store", fake_get_store):
            from tasks.memory_tasks import _async_write_verbatim

            with pytest.raises(RuntimeError, match="chroma down"):
                await _async_write_verbatim("sess-1", 0, "user", "Hello", timestamp_iso, None)


# ---------------------------------------------------------------------------
# _async_extract_facts
# ---------------------------------------------------------------------------


class TestAsyncExtractFacts:
    """Unit tests for the async helper backing memory.extract_facts."""

    @pytest.mark.asyncio
    async def test_returns_facts_count_from_agent(self):
        """Should delegate to KnowledgeExtractionAgent and return facts_count."""
        # _async_extract_facts does a deferred ``from agents.knowledge_extraction_agent
        # import KnowledgeExtractionAgent`` inside the coroutine body, so we patch
        # that dotted path in sys.modules before calling the helper.
        mock_agent_instance = AsyncMock()
        mock_agent_instance.extract_facts_from_messages = AsyncMock(return_value={"facts_count": 3, "status": "ok"})
        mock_agent_class = MagicMock(return_value=mock_agent_instance)

        with patch.dict(
            "sys.modules", {"agents.knowledge_extraction_agent": MagicMock(KnowledgeExtractionAgent=mock_agent_class)}
        ):
            from tasks.memory_tasks import _async_extract_facts

            count = await _async_extract_facts("sess-1", "user: hi\nassistant: hello", "u1")

        assert count == 3

    @pytest.mark.asyncio
    async def test_returns_zero_for_non_dict_result(self):
        """Should return 0 when agent returns a non-dict result."""
        mock_agent_instance = AsyncMock()
        mock_agent_instance.extract_facts_from_messages = AsyncMock(return_value=None)

        mock_agent_class = MagicMock(return_value=mock_agent_instance)

        with patch.dict(
            "sys.modules", {"agents.knowledge_extraction_agent": MagicMock(KnowledgeExtractionAgent=mock_agent_class)}
        ):
            # Reload to pick up the patch

            import tasks.memory_tasks as mt

            count = await mt._async_extract_facts("sess-1", "text", None)

        assert count == 0


# ---------------------------------------------------------------------------
# _async_update_graph
# ---------------------------------------------------------------------------


class TestAsyncUpdateGraph:
    """Unit tests for the async helper backing memory.update_graph."""

    @pytest.mark.asyncio
    async def test_writes_entities_and_relations(self):
        """Should call add_or_update_entity and add_relation for each item."""
        mock_graph = AsyncMock()
        mock_graph.initialize = AsyncMock()
        mock_graph.add_or_update_entity = AsyncMock()
        mock_graph.add_relation = AsyncMock()

        mock_graph_class = MagicMock(return_value=mock_graph)

        with patch.dict("sys.modules", {"autobot_memory_graph": MagicMock(AutoBotMemoryGraph=mock_graph_class)}):

            import tasks.memory_tasks as mt

            result = await mt._async_update_graph(
                "sess-1",
                [{"name": "Redis", "type": "service", "properties": {}}],
                [{"source": "App", "target": "Redis", "relation_type": "uses", "properties": {}}],
            )

        assert result["entities_written"] == 1
        assert result["relations_written"] == 1

    @pytest.mark.asyncio
    async def test_counts_partial_failures(self):
        """Entity write failures should be counted but not stop relation writes."""
        mock_graph = AsyncMock()
        mock_graph.initialize = AsyncMock()
        mock_graph.add_or_update_entity = AsyncMock(side_effect=RuntimeError("write failed"))
        mock_graph.add_relation = AsyncMock()

        mock_graph_class = MagicMock(return_value=mock_graph)

        with patch.dict("sys.modules", {"autobot_memory_graph": MagicMock(AutoBotMemoryGraph=mock_graph_class)}):

            import tasks.memory_tasks as mt

            result = await mt._async_update_graph(
                "sess-1",
                [{"name": "Bad", "type": "x", "properties": {}}],
                [{"source": "A", "target": "B", "relation_type": "r", "properties": {}}],
            )

        # Entity failed → 0 written; relation succeeded → 1 written
        assert result["entities_written"] == 0
        assert result["relations_written"] == 1


# ---------------------------------------------------------------------------
# _async_compact_snapshot
# ---------------------------------------------------------------------------


class TestAsyncCompactSnapshot:
    """Unit tests for the async helper backing memory.compact_snapshot."""

    @pytest.mark.asyncio
    async def test_appends_snapshot_with_sentinel_turn(self):
        """Should append to VerbatimStore with turn=-1 sentinel."""
        fake_store = AsyncMock()
        fake_store.append = AsyncMock(return_value="snap_chunk_id")

        async def fake_get_store():
            return fake_store

        with patch("memory.verbatim_store.get_verbatim_store", fake_get_store):
            from tasks.memory_tasks import _async_compact_snapshot

            await _async_compact_snapshot("sess-1", "user: hi\nassistant: hello", "u1")

        fake_store.append.assert_called_once()
        call_kwargs = fake_store.append.call_args
        # turn=-1 is the sentinel for pre-compaction snapshots
        turn_val = call_kwargs.kwargs.get("turn") if call_kwargs.kwargs else call_kwargs.args[1]
        assert turn_val == -1
        # text should include the PRE-COMPACT SNAPSHOT marker
        text_val = call_kwargs.kwargs.get("text") if call_kwargs.kwargs else call_kwargs.args[3]
        assert "[PRE-COMPACT SNAPSHOT]" in text_val


# ---------------------------------------------------------------------------
# on_turn_complete (stop hook)
# ---------------------------------------------------------------------------


class TestOnTurnComplete:
    """Unit tests for stop_hook.on_turn_complete.

    stop_hook.py uses a deferred import pattern (``globals().get(...)`` with
    fallback ``from tasks.memory_tasks import ...``).  Tests inject mocks
    directly into the module namespace so the ``globals().get`` check returns
    the mock instead of falling through to the real import.
    """

    @pytest.mark.asyncio
    async def test_enqueues_write_verbatim_twice_and_extract_facts_once(self):
        """on_turn_complete should enqueue write_verbatim (x2) and extract_facts (x1)."""
        import chat_workflow.stop_hook as sh

        wv_mock = MagicMock()
        wv_mock.delay = MagicMock()
        ef_mock = MagicMock()
        ef_mock.delay = MagicMock()

        # Inject mocks into the module namespace so deferred globals().get() picks them up
        prev_wv = sh.__dict__.pop("write_verbatim_task", None)
        prev_ef = sh.__dict__.pop("extract_facts_task", None)
        sh.write_verbatim_task = wv_mock
        sh.extract_facts_task = ef_mock
        try:
            await sh.on_turn_complete(
                session_id="sess-abc",
                user_message="How does Redis work?",
                assistant_response="Redis is an in-memory store.",
                user_id="user-1",
                turn_number=3,
            )
        finally:
            # Restore original state
            del sh.write_verbatim_task
            del sh.extract_facts_task
            if prev_wv is not None:
                sh.write_verbatim_task = prev_wv
            if prev_ef is not None:
                sh.extract_facts_task = prev_ef

        assert wv_mock.delay.call_count == 2
        calls = wv_mock.delay.call_args_list
        roles = [c.args[2] for c in calls]
        assert "user" in roles
        assert "assistant" in roles

        ef_mock.delay.assert_called_once()
        ef_args = ef_mock.delay.call_args.args
        assert ef_args[0] == "sess-abc"
        assert "How does Redis work?" in ef_args[1]
        assert "Redis is an in-memory store." in ef_args[1]

    @pytest.mark.asyncio
    async def test_does_not_raise_on_task_enqueue_failure(self):
        """on_turn_complete should swallow errors and never raise."""
        import chat_workflow.stop_hook as sh

        wv_failing = MagicMock()
        wv_failing.delay = MagicMock(side_effect=RuntimeError("broker down"))
        ef_ok = MagicMock()
        ef_ok.delay = MagicMock()

        prev_wv = sh.__dict__.pop("write_verbatim_task", None)
        prev_ef = sh.__dict__.pop("extract_facts_task", None)
        sh.write_verbatim_task = wv_failing
        sh.extract_facts_task = ef_ok
        try:
            await sh.on_turn_complete(
                session_id="sess-err",
                user_message="hi",
                assistant_response="hello",
                user_id=None,
                turn_number=0,
            )
        except Exception as exc:
            pytest.fail(f"on_turn_complete raised unexpectedly: {exc}")
        finally:
            del sh.write_verbatim_task
            del sh.extract_facts_task
            if prev_wv is not None:
                sh.write_verbatim_task = prev_wv
            if prev_ef is not None:
                sh.extract_facts_task = prev_ef


# ---------------------------------------------------------------------------
# on_pre_compact + estimate_context_usage (compact hook)
# ---------------------------------------------------------------------------


class TestEstimateContextUsage:
    """Unit tests for compact_hook.estimate_context_usage."""

    def test_short_conversation_below_threshold(self):
        """Short conversation should produce usage well below 0.85."""
        from chat_workflow.compact_hook import estimate_context_usage

        messages = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]
        usage = estimate_context_usage(messages, "llama3")
        assert usage < 0.85

    def test_large_conversation_above_threshold(self):
        """Conversation consuming ≥90 % of context should be ≥ 0.85."""
        from chat_workflow.compact_hook import estimate_context_usage

        # 8192 tokens * 4 chars/token = 32768 chars; 90% ≈ 29491 chars
        big_content = "x" * 29500
        messages = [{"role": "user", "content": big_content}]
        usage = estimate_context_usage(messages, "llama3")
        assert usage >= 0.85

    def test_unknown_model_falls_back_to_default(self):
        """Unknown model name should use default context size."""
        from chat_workflow.compact_hook import (
            _MODEL_CONTEXT_SIZES,
            estimate_context_usage,
        )

        messages = [{"role": "user", "content": "x" * 100}]
        usage = estimate_context_usage(messages, "totally-unknown-model-xyz")
        default_size = _MODEL_CONTEXT_SIZES["default"]
        expected = (100 / 4) / default_size
        assert abs(usage - expected) < 1e-6

    def test_empty_messages_returns_zero(self):
        """Empty message list should return 0.0 usage."""
        from chat_workflow.compact_hook import estimate_context_usage

        assert estimate_context_usage([], "llama3") == 0.0

    def test_usage_clamped_to_one(self):
        """Usage should never exceed 1.0 even when content exceeds context."""
        from chat_workflow.compact_hook import estimate_context_usage

        # 2x the llama3 8192-token budget
        huge_content = "y" * (8192 * 4 * 2)
        messages = [{"role": "user", "content": huge_content}]
        usage = estimate_context_usage(messages, "llama3")
        assert usage == 1.0

    def test_known_model_prefix_match(self):
        """Model tag like 'llama3.2:8b-instruct' should match 'llama3.2' entry."""
        from chat_workflow.compact_hook import estimate_context_usage

        messages = [{"role": "user", "content": "x" * 400}]
        usage_tagged = estimate_context_usage(messages, "llama3.2:8b-instruct-q4_K_M")
        usage_bare = estimate_context_usage(messages, "llama3.2")
        assert abs(usage_tagged - usage_bare) < 1e-6


class TestOnPreCompact:
    """Unit tests for compact_hook.on_pre_compact.

    compact_hook.py uses a deferred import pattern (``globals().get(...)``).
    Tests inject mocks directly into the module namespace so the check returns
    the mock instead of falling through to the real import.
    """

    def _inject_cs_mock(self, ch, cs_mock):
        """Inject a compact_snapshot_task mock and return original value."""
        original = ch.__dict__.pop("compact_snapshot_task", None)
        ch.compact_snapshot_task = cs_mock
        return original

    def _restore_cs(self, ch, original):
        """Remove injected mock and optionally restore original."""
        ch.__dict__.pop("compact_snapshot_task", None)
        if original is not None:
            ch.compact_snapshot_task = original

    @pytest.mark.asyncio
    async def test_does_not_enqueue_below_threshold(self):
        """on_pre_compact must NOT enqueue when estimated usage < 0.85."""
        import chat_workflow.compact_hook as ch

        cs_mock = MagicMock()
        cs_mock.delay = MagicMock()

        original = self._inject_cs_mock(ch, cs_mock)
        try:
            with patch.object(ch, "estimate_context_usage", return_value=0.50):
                await ch.on_pre_compact(
                    "sess-1",
                    [{"role": "user", "content": "short"}],
                    None,
                    "llama3",
                )
        finally:
            self._restore_cs(ch, original)

        cs_mock.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueues_at_threshold(self):
        """on_pre_compact must enqueue compact_snapshot_task when usage ≥ 0.85."""
        import chat_workflow.compact_hook as ch

        cs_mock = MagicMock()
        cs_mock.delay = MagicMock()
        messages = [{"role": "user", "content": "big message " * 500}]

        original = self._inject_cs_mock(ch, cs_mock)
        try:
            with patch.object(ch, "estimate_context_usage", return_value=0.87):
                await ch.on_pre_compact("sess-2", messages, "user-1", "llama3")
        finally:
            self._restore_cs(ch, original)

        cs_mock.delay.assert_called_once()
        call_args = cs_mock.delay.call_args.args
        assert call_args[0] == "sess-2"
        assert call_args[2] == "user-1"

    @pytest.mark.asyncio
    async def test_snapshot_content_includes_recent_messages(self):
        """Snapshot should contain role-prefixed message content."""
        import chat_workflow.compact_hook as ch

        cs_mock = MagicMock()
        cs_mock.delay = MagicMock()
        messages = [
            {"role": "user", "content": "Tell me about Redis"},
            {"role": "assistant", "content": "Redis is an in-memory store"},
        ]

        original = self._inject_cs_mock(ch, cs_mock)
        try:
            with patch.object(ch, "estimate_context_usage", return_value=0.90):
                await ch.on_pre_compact("sess-3", messages, None, "llama3")
        finally:
            self._restore_cs(ch, original)

        snapshot_text = cs_mock.delay.call_args.args[1]
        assert "user:" in snapshot_text
        assert "Tell me about Redis" in snapshot_text

    @pytest.mark.asyncio
    async def test_does_not_raise_on_enqueue_failure(self):
        """on_pre_compact should swallow enqueue errors and never raise."""
        import chat_workflow.compact_hook as ch

        failing_cs = MagicMock()
        failing_cs.delay = MagicMock(side_effect=RuntimeError("broker down"))
        messages = [{"role": "user", "content": "hi"}]

        original = self._inject_cs_mock(ch, failing_cs)
        try:
            with patch.object(ch, "estimate_context_usage", return_value=0.90):
                try:
                    await ch.on_pre_compact("sess-err", messages, None, "llama3")
                except Exception as exc:
                    pytest.fail(f"on_pre_compact raised unexpectedly: {exc}")
        finally:
            self._restore_cs(ch, original)
