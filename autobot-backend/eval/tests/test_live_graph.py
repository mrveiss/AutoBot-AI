# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The default live turn through the REAL chat graph with a scripted model (#20843).

Only the model pass (``_run_continuation_loop_iteration``) and the manager's I/O seams are scripted, on
``MemorySaver``; the graph, its routing, the loop detector, the graph state read-back, the checkpoint cleanup and
the failure classifier are real. Each scenario asserts the detector the chat workflow owns fired, so a classifier
that drifted into a parallel re-implementation would not satisfy them.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from chat_workflow import graph as graph_module
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.tool_call_loop import _LOOP_ABORT_THRESHOLD
from chat_workflow.tool_dispatch_guards import unknown_tool_error
from eval import live
from eval.live_classify import classify_failures
from eval.store import GoldenTrajectory

pytestmark = pytest.mark.asyncio


class _Redis:
    async def set(self, k, v, ex=None):
        pass

    async def get(self, k):
        return None


def _manager(contexts: list) -> ChatWorkflowManager:
    m = ChatWorkflowManager.__new__(ChatWorkflowManager)
    m._active_streams = 0
    m.redis_client = _Redis()
    m.rag_service = None
    m.initialize = AsyncMock(return_value=True)
    session = SimpleNamespace(metadata={}, conversation_history=[], kb_principal=lambda: None)

    async def intents(*a, **k):
        yield False

    llm_ctx = SimpleNamespace(
        ollama_endpoint="e",
        selected_model="m",
        system_prompt="",
        initial_prompt="hi",
        used_knowledge=True,
        rag_citations=[],
    )

    async def role(sid, ctx, role_, scope):
        contexts.append(dict(ctx or {}))
        return ctx or {}

    m._apply_session_role = role
    m._initialize_chat_session = AsyncMock(return_value=(session, "term", False))
    m._persist_user_message = AsyncMock()
    m._process_special_intents = intents
    m.get_or_create_session = AsyncMock(return_value=session)
    m._prepare_llm_workflow_params = AsyncMock(return_value={"prompt": "hi", "lightweight_mode_used": False})
    m._create_llm_iteration_context = lambda *a, **k: llm_ctx
    m._persist_workflow_messages = AsyncMock()
    m._build_and_log_continuation_prompt = lambda ctx, hist: "continued"
    return m


def _golden() -> GoldenTrajectory:
    return GoldenTrajectory("g", "knowledge_qa", {"prompt": "why?"}, [], 0.9, tool_match="subsequence")


async def _drive(script, workspace_root):
    """Run the default turn runner with *script* as the model; returns (record, contexts, deleted_threads)."""
    contexts: list = []
    deleted: list = []
    saver = MemorySaver()
    graph_module._compiled_graph = None

    async def passes(self, http, prompt, iteration, ctx):
        async for item in script(iteration, ctx):
            yield item

    real_delete = graph_module.delete_thread_checkpoints

    async def spy_delete(thread_id):
        deleted.append(thread_id)
        await real_delete(thread_id)

    manager = _manager(contexts)
    try:
        with (
            patch.object(graph_module, "get_redis_checkpointer", AsyncMock(return_value=saver)),
            patch.object(ChatWorkflowManager, "_run_continuation_loop_iteration", passes),
            patch("autobot_shared.http_client.get_http_client", lambda: None),
            patch("chat_workflow.graph.attachment_prompt", AsyncMock(return_value="p")),
            patch("chat_workflow.get_chat_workflow_manager", lambda: manager),
            patch("chat_workflow.graph.delete_thread_checkpoints", spy_delete),
        ):
            record = await live.chat_turn_runner(_golden(), "pinned-model", workspace_root)
    finally:
        graph_module._compiled_graph = None
    return record, contexts, deleted, saver


async def test_a_clean_answer_has_no_category_and_the_turn_is_pinned_bounded_and_cleaned_up(tmp_path):
    async def script(iteration, ctx):
        yield {"type": "response", "content": "a grounded answer", "metadata": {}}
        yield ("a grounded answer", False)

    record, contexts, deleted, saver = await _drive(script, tmp_path)
    assert record.final_text == "a grounded answer" and record.final_status == "completed"
    assert classify_failures(record) == []
    (ctx,) = contexts
    assert ctx["model"] == "pinned-model" and ctx["agent_id"] == live.READ_ONLY_AGENT_ID  # chat's own selector
    assert ctx["requires_approval_before"], "every approval category is gated"
    (thread,) = deleted
    assert thread.startswith("eval-g-") and not [c async for c in saver.alist({"configurable": {"thread_id": thread}})]


async def test_a_repeated_tool_call_trips_the_real_loop_detector(tmp_path):
    async def script(iteration, ctx):
        ctx.execution_history.append({"tool": "web_search", "status": "success", "command": "web_search"})
        yield ("searching again", True)

    record, *_ = await _drive(script, tmp_path)
    assert record.tool_loop_count >= _LOOP_ABORT_THRESHOLD  # set by the graph's own detector, read from state
    assert "loop_stall" in classify_failures(record) and record.tool_sequence[0] == "web_search"


async def test_the_dispatchers_unknown_tool_error_is_classified(tmp_path):
    async def script(iteration, ctx):
        message = unknown_tool_error("no_such_tool", None, [], {"web_search"})
        yield {"type": message.type, "content": message.content, "metadata": message.metadata}
        yield ("sorry", False)

    record, *_ = await _drive(script, tmp_path)
    assert "unknown_tool" in classify_failures(record)


async def test_an_unparsed_tool_call_in_the_model_text_is_classified_malformed(tmp_path):
    broken = '<TOOL_CALL name="web_search" params=\'{"query": \'>look it up'

    async def script(iteration, ctx):
        yield (broken, False)

    record, *_ = await _drive(script, tmp_path)
    assert record.raw_responses == [broken]
    assert "malformed_tool_call" in classify_failures(record)
