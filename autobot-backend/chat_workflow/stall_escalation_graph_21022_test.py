# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21022 review: stall routing in the PRODUCTION chat graph, the resume binding, the reload restore, the prompt."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from autobot_shared.ssot_config import config
from chat_workflow import graph, stall_escalation, stall_pending
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.tool_call_loop import _LOOP_ABORT_THRESHOLD

pytestmark = pytest.mark.asyncio

HISTORY = [{"tool": "web_search", "status": "success", "output": "found it"}]
STALLED = {
    "session_id": "s1",
    "context": {},
    "iteration_count": 2,
    "tool_loop_count": _LOOP_ABORT_THRESHOLD,
    "execution_history": HISTORY,
    "workflow_messages": [],
    "should_continue": True,
}
CFG = {"configurable": {"thread_id": "s1", "stream_callback": None, "manager": MagicMock()}}


@pytest.fixture
def prod(monkeypatch):
    """The real ``build_chat_graph()`` with a checkpointer; only the model call and persistence are stubbed."""
    seen: dict = {}

    # LangGraph injects the run config only into a parameter named ``config`` -- the production nodes' convention.
    async def generate(state, config: RunnableConfig):
        seen["generate"] = state
        return {"error": "end of test"}  # route_after_generation -> persist_conversation

    async def persist(state, config: RunnableConfig):
        seen["persist"] = state
        return {}

    monkeypatch.setattr(graph, "generate_response", generate)
    monkeypatch.setattr(graph, "persist_conversation", persist)
    monkeypatch.setattr(stall_escalation, "_bus_publish_event", AsyncMock())
    monkeypatch.setattr(config.llm, "chat_stall_escalation", "ask")
    compiled = graph.build_chat_graph().compile(checkpointer=MemorySaver())
    monkeypatch.setattr(graph, "get_compiled_graph", AsyncMock(return_value=compiled))
    return compiled, seen


async def _stall(compiled):
    await compiled.aupdate_state(CFG, STALLED, as_node="execute_tools")
    await compiled.ainvoke(None, CFG)
    return await compiled.aget_state(CFG)


async def test_a_stalled_production_turn_pauses_at_the_question(prod):
    compiled, _ = prod
    snapshot = await _stall(compiled)
    assert snapshot.next == ("ask_human",)
    question = await stall_pending.pending_stall_question(MagicMock(), "s1")
    assert question["type"] == "human_question" and question["question_id"]


async def test_the_answer_resumes_the_production_graph_into_generation_with_history(prod):
    compiled, seen = prod
    await _stall(compiled)
    await compiled.ainvoke(Command(resume={"answer": "use the other host"}), CFG)
    state = seen["generate"]
    assert "use the other host" in state["tool_loop_warning"]
    assert state["execution_history"] == HISTORY and state["tool_loop_count"] == 0
    assert "persist" in seen  # the stub generation ended the run


async def test_an_empty_answer_stops_and_the_stop_message_reaches_persistence(prod):
    compiled, seen = prod
    await _stall(compiled)
    await compiled.ainvoke(Command(resume={"answer": ""}), CFG)
    assert "generate" not in seen
    assert any("stopped the loop" in str(m) for m in seen["persist"]["workflow_messages"])


async def test_control_stop_mode_never_pauses_the_production_graph(prod, monkeypatch):
    compiled, seen = prod
    monkeypatch.setattr(config.llm, "chat_stall_escalation", "stop")
    await compiled.aupdate_state(CFG, STALLED, as_node="execute_tools")
    await compiled.ainvoke(None, CFG)
    assert "persist" in seen and (await compiled.aget_state(CFG)).next == ()


async def test_the_answer_and_the_tool_results_share_the_resumed_prompt():
    update = await _resumed_update("use the other host")
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    ctx = SimpleNamespace(
        message="what is X", consecutive_invalid_tool_calls=0, execution_history=HISTORY, initial_prompt="p"
    )
    graph._carry_tool_results_into_prompt(manager, ctx, {**STALLED, **update})
    assert "use the other host" in ctx.initial_prompt and "found it" in ctx.initial_prompt


async def _resumed_update(answer: str) -> dict:
    """What the real ``ask_human`` node returns once the person has answered."""
    state = {**STALLED, "stall_question": {"question_id": "q"}}
    with patch.object(stall_escalation, "interrupt", return_value={"answer": answer}):
        with patch.object(stall_escalation, "_bus_publish_event", AsyncMock()):
            return await stall_escalation.ask_human(state, CFG)


def _pending(monkeypatch, value):
    monkeypatch.setattr(stall_pending, "pending_stall_question", AsyncMock(return_value=value))


async def test_an_approval_resume_cannot_answer_a_stall_question(monkeypatch):
    _pending(monkeypatch, {"question_id": "q1"})
    with pytest.raises(HTTPException) as err:
        await stall_pending.check_resume_binding(MagicMock(), "s1", {"approved": True})
    assert err.value.status_code == 409


async def test_an_answer_for_another_question_is_refused(monkeypatch):
    _pending(monkeypatch, {"question_id": "q1"})
    with pytest.raises(HTTPException) as err:
        await stall_pending.check_resume_binding(MagicMock(), "s1", {"answer": "x", "question_id": "old"})
    assert err.value.status_code == 409


async def test_the_matching_answer_and_an_explicit_empty_stop_pass(monkeypatch):
    _pending(monkeypatch, {"question_id": "q1"})
    await stall_pending.check_resume_binding(MagicMock(), "s1", {"answer": "x", "question_id": "q1"})
    await stall_pending.check_resume_binding(MagicMock(), "s1", {"answer": "", "question_id": "q1"})


async def test_an_answer_with_nothing_pending_is_refused_but_an_approval_is_not(monkeypatch):
    _pending(monkeypatch, None)
    with pytest.raises(HTTPException) as err:
        await stall_pending.check_resume_binding(MagicMock(), "s1", {"answer": "x", "question_id": "q1"})
    assert err.value.status_code == 409
    await stall_pending.check_resume_binding(MagicMock(), "s1", {"approved": True})  # control


async def test_an_unreadable_checkpoint_refuses_an_answer_but_not_an_approval(monkeypatch):
    monkeypatch.setattr(stall_pending, "pending_stall_question", AsyncMock(side_effect=RuntimeError("redis down")))
    with pytest.raises(HTTPException) as err:
        await stall_pending.check_resume_binding(MagicMock(), "s1", {"answer": "x", "question_id": "q1"})
    assert err.value.status_code == 503
    await stall_pending.check_resume_binding(MagicMock(), "s1", {"approved": True})  # control


@pytest.mark.parametrize("field", ["reason", "answer"])
@pytest.mark.parametrize("bad", [["a"], {"k": "v"}, 7])
async def test_a_non_string_text_field_is_a_400_not_a_500(field, bad):
    from api.chat_streaming import resume_decision

    with pytest.raises(HTTPException) as err:
        resume_decision({field: bad}, "s1")
    assert err.value.status_code == 400


def _request(manager):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(chat_workflow_manager=manager)))


async def test_a_reload_restores_the_open_question_card(monkeypatch):
    _pending(monkeypatch, {"question_id": "q1", "question": "How?", "type": "human_question"})
    history = [{"id": "u1", "sender": "user", "text": "hi"}]
    messages = await stall_pending.with_pending_question(_request(MagicMock()), "s1", history)
    card = messages[-1]
    assert card["type"] == "human_question" and card["text"] == "How?"
    assert card["metadata"]["question_id"] == "q1" and card["metadata"]["session_id"] == "s1"
    assert messages[:-1] == history


async def test_a_saved_card_is_not_duplicated_and_a_stale_answered_flag_is_cleared(monkeypatch):
    _pending(monkeypatch, {"question_id": "q1", "question": "How?"})
    saved = {
        "id": "m",
        "type": "human_question",
        "metadata": {"question_id": "q1", "answered": True, "answer_text": "x"},
    }
    messages = await stall_pending.with_pending_question(_request(MagicMock()), "s1", [saved])
    assert len(messages) == 1 and "answered" not in messages[0]["metadata"]


async def test_control_nothing_pending_or_no_manager_leaves_history_alone(monkeypatch):
    history = [{"id": "u1"}]
    _pending(monkeypatch, None)
    assert await stall_pending.with_pending_question(_request(MagicMock()), "s1", history) == history
    assert await stall_pending.with_pending_question(_request(None), "s1", history) == history


async def test_an_answer_without_a_question_id_is_refused_while_a_question_is_pending(monkeypatch):
    _pending(monkeypatch, {"question_id": "q1"})
    with pytest.raises(HTTPException) as err:
        await stall_pending.check_resume_binding(MagicMock(), "s1", {"answer": "x"})
    assert err.value.status_code == 409


async def test_a_second_concurrent_answer_gets_409_from_the_real_claim_registry(monkeypatch):
    fakeredis_async = pytest.importorskip("fakeredis.aioredis")
    fakeredis = pytest.importorskip("fakeredis")
    from autobot_shared.coordination import work_claims

    client = fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(work_claims, "get_async_redis_client", AsyncMock(return_value=client))
    first = await stall_pending.acquire_answer_lock("s1")
    with pytest.raises(HTTPException) as err:
        await stall_pending.acquire_answer_lock("s1")
    assert err.value.status_code == 409
    await stall_pending.acquire_answer_lock("s2")  # another chat is unaffected
    await stall_pending.release_answer_lock("s1", first)
    await stall_pending.release_answer_lock("s1", await stall_pending.acquire_answer_lock("s1"))  # free again
    await client.flushall()
