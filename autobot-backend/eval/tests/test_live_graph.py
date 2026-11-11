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

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from chat_workflow import graph as graph_module
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.tool_call_loop import _LOOP_ABORT_THRESHOLD
from chat_workflow.tool_dispatch_guards import unknown_tool_error
from eval import live, live_turn
from eval.live_classify import classify_failures
from eval.runner import RecordingUnusable
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
    m.sessions = {}
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


class _History:
    """Stands in for ``ChatHistoryManager``: records which session ids the eval deleted."""

    deleted: list = []

    async def delete_session(self, session_id):
        _History.deleted.append(session_id)
        return True


async def _boom(self, *args, **kwargs):
    raise RuntimeError("graph exploded")
    yield  # pragma: no cover - makes this an async generator like the real one


async def _drive(script, workspace_root, graph_raises=False):
    """Run the default turn runner with *script* as the model; returns (record, contexts, deleted_threads)."""
    contexts: list = []
    deleted: list = []
    _History.deleted = []
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
    via = _boom if graph_raises else ChatWorkflowManager._process_via_graph
    try:
        with (
            patch.object(graph_module, "get_redis_checkpointer", AsyncMock(return_value=saver)),
            patch.object(ChatWorkflowManager, "_run_continuation_loop_iteration", passes),
            patch("autobot_shared.http_client.get_http_client", lambda: None),
            patch("chat_workflow.graph.attachment_prompt", AsyncMock(return_value="p")),
            patch("chat_workflow.get_chat_workflow_manager", lambda: manager),
            patch("chat_workflow.graph.delete_thread_checkpoints", spy_delete),
            patch("chat_history.ChatHistoryManager", _History),
            patch.object(ChatWorkflowManager, "_process_via_graph", via),
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


async def test_the_chat_history_the_turn_persisted_is_deleted_under_the_evals_own_id_only(tmp_path):
    async def script(iteration, ctx):
        yield ("an answer", False)

    _, _, deleted, _ = await _drive(script, tmp_path)
    assert _History.deleted == deleted and deleted[0].startswith("eval-g-")


_UUID4 = uuid.UUID(int=0xABCDEF00, version=4).hex


@pytest.mark.parametrize(
    "session_id",
    [
        "a-real-users-session",
        "eval-g-123",
        f"eval-g-{_UUID4}-extra",
        f"evalx-g-{_UUID4}",
        f"eval--{_UUID4}",
        f"eval-g-{_UUID4[:12]}1{_UUID4[13:]}",  # not a uuid4 (version nibble)
        f"eval-g-{_UUID4[:16]}0{_UUID4[17:]}",  # not a uuid4 (variant nibble)
        f"eval-g-{_UUID4.upper()}",
        f"eval-g-{_UUID4}\n",
    ],
)
async def test_a_history_delete_for_a_session_that_is_not_the_evals_own_is_refused(session_id):
    _History.deleted = []
    with patch("chat_history.ChatHistoryManager", _History):
        with pytest.raises(ValueError, match="not the eval's own"):
            await live_turn._delete_history(session_id)
    assert _History.deleted == []


async def test_a_session_id_the_eval_made_is_accepted_by_its_own_delete_guard():
    _History.deleted = []
    session_id = live_turn.new_session_id(_golden())
    with patch("chat_history.ChatHistoryManager", _History):
        await live_turn._delete_history(session_id)
    assert _History.deleted == [session_id]


async def test_a_denied_approval_ends_the_turn_and_runs_no_tool():
    """Chat's resume supports a terminal deny: the denied branch of execute_tools skips every call."""
    state = {
        "session_id": "eval-g-1",
        "tool_calls": [{"name": "navigate", "params": {"url": "x"}, "needs_approval": True}],
        "approval_decision": {"approved": False, "reason": live_turn.DENIED_REASON, "bound": []},
        "workflow_messages": [],
        "iteration_count": 1,
    }
    with patch.object(graph_module, "dispatch_approved_calls", AsyncMock(side_effect=AssertionError("ran a tool"))):
        update = await graph_module.execute_tools(state, {"configurable": {"manager": object()}})
    assert update["should_continue"] is False and "execution_history" not in update
    assert graph_module.route_after_execution({**state, **update}) == "persist_conversation"


async def test_a_graph_that_raised_and_fell_back_to_legacy_is_not_run_and_is_still_cleaned_up(tmp_path):
    async def script(iteration, ctx):
        yield ("never reached", False)

    with pytest.raises(live.GraphDidNotRun) as raised:
        await _drive(script, tmp_path, graph_raises=True)
    assert isinstance(raised.value, RecordingUnusable)  # the runner reports it as not_run, not as a clean run
    assert len(_History.deleted) == 1


async def test_a_paused_approval_is_denied_with_the_eval_reason_and_a_finished_turn_is_left_alone():
    resumed = []

    class Manager:
        async def resume_graph(self, session_id, decision):
            resumed.append((session_id, decision))
            yield None

    await live_turn._deny_pending_approval(Manager(), None, "eval-g-1", SimpleNamespace(next=("execute_tools",)))
    await live_turn._deny_pending_approval(Manager(), None, "eval-g-2", SimpleNamespace(next=()))
    assert resumed == [("eval-g-1", {"approved": False, "reason": "denied: eval run"})]


async def test_a_trajectory_id_with_punctuation_gets_a_session_id_its_own_cleanup_accepts():
    golden = GoldenTrajectory("fix.timeout/v2", "code_fix", {"prompt": "p"}, [], 0.9)
    _History.deleted = []
    session_id = live_turn.new_session_id(golden)
    with patch("chat_history.ChatHistoryManager", _History):
        await live_turn._delete_history(session_id)
    assert _History.deleted == [session_id]


async def test_cleanup_also_releases_the_in_memory_workflow_session():
    manager = _manager([])
    manager.sessions["eval-g-1"] = object()
    _History.deleted = []
    with (
        patch("chat_workflow.get_chat_workflow_manager", lambda: manager),
        patch("chat_workflow.graph.delete_thread_checkpoints", AsyncMock()),
        patch("chat_history.ChatHistoryManager", _History),
    ):
        await live_turn._cleanup("eval-g-1-" + "0" * 12 + "4" + "0" * 3 + "8" + "0" * 15)
        manager.sessions["eval-g-2"] = object()
        assert await manager.remove_session("eval-g-2") is True and await manager.remove_session("eval-g-2") is False


async def test_a_turn_whose_graph_node_failed_is_not_run():
    class Manager:
        async def initialize(self):
            return None

        async def process_message(self, *args, **kwargs):
            return []

        async def remove_session(self, session_id):
            return True

    class Graph:
        async def aget_state(self, config):
            return SimpleNamespace(values={"iteration_count": 2, "error": "node failed"}, next=())

    with (
        patch("chat_workflow.get_chat_workflow_manager", lambda: Manager()),
        patch("chat_workflow.graph.get_compiled_graph", AsyncMock(return_value=Graph())),
        patch("chat_workflow.graph.delete_thread_checkpoints", AsyncMock()),
        patch("chat_history.ChatHistoryManager", _History),
    ):
        _History.deleted = []
        with pytest.raises(live_turn.GraphFailed):
            await live_turn.chat_turn_runner(_golden(), "m", None)
    assert len(_History.deleted) == 1  # and it was still cleaned up
