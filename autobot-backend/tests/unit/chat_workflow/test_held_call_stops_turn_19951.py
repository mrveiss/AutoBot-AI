# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A held chat tool call stops the turn in the production graph until a person decides it (#19951).

Drives the real ``build_chat_graph()`` (planner node, ``route_after_generation``, ``request_approval`` interrupt,
``execute_tools``) over a checkpointer; only the model call and persistence are stubbed. The held tool is ``click``,
a mutating browser action the real gate holds.
"""

from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from chat_workflow import graph
from chat_workflow.manager import ChatWorkflowManager
from tests.unit.chat_workflow.test_ai_line_support import (
    VERIFIED_COMPANY,
    ai_line_world,
)

pytestmark = pytest.mark.asyncio

CLICK = {"name": "click", "params": {"selector": "#buy"}}


class NextModelCall(Exception):
    """Raised by the stubbed model on its second call: the turn asked the model again."""


class Turn:
    """One turn over the production graph, recording every model call, dispatch and card."""

    def __init__(self, monkeypatch):
        self.prompts: list = []
        self.dispatched: list = []
        self.streamed: list = []

        async def persist(state, config: RunnableConfig):
            return {}

        monkeypatch.setattr(graph, "persist_conversation", persist)
        monkeypatch.setattr("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", True)
        self.compiled = graph.build_chat_graph().compile(checkpointer=MemorySaver())
        self.cfg = {
            "configurable": {
                "thread_id": "s1",
                "stream_callback": self.streamed.append,
                "manager": self._manager(),
            }
        }

    def _manager(self):
        manager = ChatWorkflowManager.__new__(ChatWorkflowManager)

        async def model(http_client, current_prompt, iteration, ctx):
            self.prompts.append(current_prompt)
            if len(self.prompts) > 1:
                raise NextModelCall
            yield (
                "I will click buy",
                [dict(CLICK, params=dict(CLICK["params"]))],
                False,
            )

        async def dispatch(tool_calls, *_a, ctx=None, **_k):
            self.dispatched.append([c["name"] for c in tool_calls])
            results = [{"tool": c["name"], "status": "success", "output": f"ran {c['name']}"} for c in tool_calls]
            yield {
                "type": "execution_summary",
                "metadata": {"execution_results": results},
            }
            yield (False, None)

        async def keep(results):
            return results

        manager._run_llm_iteration_plan_only = model
        manager._process_tool_calls = dispatch
        manager._offload_oversized_output = keep
        return manager

    async def run_to_the_hold(self):
        """Start at ``generate_response`` (the node after the planner) and run until the graph stops."""
        state = {
            "session_id": "s1",
            "terminal_session_id": "t1",
            "user_message": "buy it",
            "context": {"verified_company_id": VERIFIED_COMPANY},
            "llm_params": {
                "ollama_endpoint": "http://x",
                "selected_model": "m",
                "system_prompt": "s",
                "initial_prompt": "p",
            },
            "used_knowledge": False,
            "rag_citations": [],
            "execution_history": [],
            "workflow_messages": [],
            "all_llm_responses": [],
            "iteration_count": 0,
        }
        await self.compiled.aupdate_state(self.cfg, state, as_node="create_plan")
        await self.compiled.ainvoke(None, self.cfg)

    async def decide(self, decision):
        """Resume with the person's answer; the very next model call is the end of this test."""
        with pytest.raises(NextModelCall):
            await self.compiled.ainvoke(Command(resume=decision), self.cfg)

    def cards(self) -> list:
        return [m for m in self.streamed if m.get("type") == "command_approval_request"]


@pytest.fixture
def turn(monkeypatch):
    return Turn(monkeypatch)


async def test_one_hold_is_one_card_and_no_further_model_call_until_decided(turn):
    with ai_line_world():
        await turn.run_to_the_hold()
        snapshot = await turn.compiled.aget_state(turn.cfg)

    assert snapshot.next == ("request_approval",), "the turn is parked at the approval, not looping"
    assert len(turn.prompts) == 1, "the model was called once, for the plan that held"
    assert turn.dispatched == [], "a held call has not run"
    assert [c["metadata"]["calls"][0]["tool"] for c in turn.cards()] == ["click"]


async def test_a_held_turn_files_exactly_one_approval_for_the_turn(turn):
    with ai_line_world() as filed:
        await turn.run_to_the_hold()
        assert len(turn.cards()) == 1, "one hold, one approval card shown to the person"
        await turn.decide({"approved": True})

    assert turn.dispatched == [["click"]], "the approved call ran once, exactly as shown"
    # The card is the approval: the dispatch seam must not file a second record for the call the person approved.
    assert filed.await_count == 0


async def test_a_refused_hold_tells_the_model_it_has_no_result_and_nothing_ran(turn):
    with ai_line_world():
        await turn.run_to_the_hold()
        assert len(turn.prompts) == 1
        await turn.decide({"approved": False, "reason": "not now"})
        state = (await turn.compiled.aget_state(turn.cfg)).values

    assert turn.dispatched == [], "a refused call never runs"
    assert [r["status"] for r in state["execution_history"]] == ["refused"]
    assert len(turn.prompts) == 2, "the model is asked again only after the decision"
    told = turn.prompts[1]
    assert "refused" in told and "not now" in told and "did not run" in told
    assert "ran click" not in told, "the model must not be handed a result the call never produced"
