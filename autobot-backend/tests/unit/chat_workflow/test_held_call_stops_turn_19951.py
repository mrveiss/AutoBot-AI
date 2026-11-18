# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A held chat tool call stops the turn in the production graph until a person decides it (#19951).

Drives the real ``build_chat_graph()`` over a checkpointer: planner node, ``route_after_generation``,
``request_approval`` interrupt, ``execute_tools``, the manager's real ``_process_tool_calls`` and the AI-line seam.
Only the model, the stores behind the seam (``ai_line_world``) and the browser executor are faked. The held tool is
``click``, a mutating browser action the real gate holds.
"""

from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from async_chat_workflow import WorkflowMessage
from chat_workflow import graph, tool_handler
from chat_workflow.manager import ChatWorkflowManager
from tests.unit.chat_workflow.test_ai_line_support import VERIFIED_COMPANY, ai_line_world, arun_guard

pytestmark = pytest.mark.asyncio

CLICK = {"name": "click", "params": {"selector": "#buy"}}
CLICKED = "clicked buy"


def _input(**extra) -> dict:
    return {
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
        **extra,
    }


class Turn:
    """One turn over the production graph, recording every model call, executor run and streamed card."""

    def __init__(self, monkeypatch, gate: bool = True, then_click: bool = False):
        self.prompts: list = []
        self.executed: list = []
        self.streamed: list = []
        self.interrupts: list = []
        self.then_click = then_click

        async def nothing(state, config: RunnableConfig):
            return {}

        async def registered(*_a, **_k):
            return True

        async def unverified(*_a, **_k):
            return None

        for node in ("persist_conversation", "reflect_on_response", "inline_judge_response"):
            monkeypatch.setattr(graph, node, nothing)
        monkeypatch.setattr(tool_handler, "is_registered_tool", registered)
        monkeypatch.setattr(tool_handler, "enforce_pre_action_verifier", unverified)
        monkeypatch.setattr("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", gate)
        self.compiled = graph.build_chat_graph().compile(checkpointer=MemorySaver())
        self.cfg = {
            "configurable": {"thread_id": "s1", "stream_callback": self.streamed.append, "manager": self._manager()}
        }

    def _manager(self):
        manager = ChatWorkflowManager.__new__(ChatWorkflowManager)

        async def model(http_client, current_prompt, iteration, ctx):
            self.prompts.append(current_prompt)
            wants_click = len(self.prompts) == 1 or self.then_click
            yield ("ok", [dict(CLICK, params=dict(CLICK["params"]))] if wants_click else [], False)

        async def browser(tool_call, execution_results, session_id="", role="user"):
            self.executed.append(tool_call["name"])
            execution_results.append({"tool": tool_call["name"], "status": "success", "output": CLICKED})
            yield WorkflowMessage(type="execution", content=CLICKED, metadata={})

        async def keep(results):
            return results

        manager._collect_and_validate_llm_response = model
        manager._handle_browser_tool = browser
        manager._offload_oversized_output = keep
        return manager

    async def start(self):
        """Begin at ``generate_response`` (``create_plan``'s successor) and run until the graph stops."""
        await self.compiled.aupdate_state(self.cfg, _input(), as_node="create_plan")
        return await self._run(None)

    async def decide(self, decision):
        return await self._run(Command(resume=decision))

    async def _run(self, graph_input):
        result = await self.compiled.ainvoke(graph_input, self.cfg)
        self.interrupts += [i.value for i in result.get("__interrupt__") or []]
        return result

    def cards(self) -> list:
        """Every approval card the person was shown: the interrupt's value, plus any the nodes streamed."""
        streamed = [m for m in self.streamed if m.get("type") == "command_approval_request"]
        return self.interrupts + streamed


@pytest.fixture
def turn(monkeypatch):
    return Turn(monkeypatch)


async def test_one_hold_is_one_card_and_no_further_model_call_until_decided(turn):
    with ai_line_world():
        await turn.start()
        snapshot = await turn.compiled.aget_state(turn.cfg)

    assert snapshot.next == ("request_approval",), "the turn is parked at the approval, not looping"
    assert snapshot.values["tool_calls"][0]["needs_approval"] is True, "the planner held the call before routing"
    assert len(turn.prompts) == 1, "the model was called once, for the plan that held"
    assert turn.executed == [], "a held call has not run"
    assert [c["metadata"]["calls"][0]["tool"] for c in turn.cards()] == ["click"]


async def test_an_approved_hold_runs_the_shown_call_once_and_the_model_reads_its_output(turn):
    with ai_line_world() as filed:
        await turn.start()
        await turn.decide({"approved": True})

    assert turn.executed == ["click"], "the approved call ran once"
    assert len(turn.prompts) == 2, "the model is asked again only after the decision"
    assert CLICKED in turn.prompts[1], "the output of the executed call reached the model"
    assert len(turn.cards()) == 1, "resuming does not show the decided card again"
    assert filed.await_count == 0, "the real seam let the card-approved call through without filing a second record"


async def test_a_refused_hold_tells_the_model_it_has_no_result_and_nothing_ran(turn):
    with ai_line_world() as filed:
        await turn.start()
        await turn.decide({"approved": False, "reason": "not now"})
        state = (await turn.compiled.aget_state(turn.cfg)).values

    assert turn.executed == [], "a refused call never runs"
    assert [r["status"] for r in state["execution_history"]] == ["refused"]
    assert len(turn.prompts) == 2
    told = turn.prompts[1]
    assert "refused" in told and "not now" in told and "did not run" in told
    assert CLICKED not in told, "the model must not be handed a result the call never produced"
    assert len(turn.cards()) == 1 and filed.await_count == 0


async def test_without_the_card_the_seam_files_exactly_one_hold(turn):
    state = _input()
    ctx = graph._build_llm_iteration_context(state)
    assert ctx.approved_fingerprints == frozenset()

    message, filed = await arun_guard(dict(CLICK), ctx, [])

    assert message is not None and filed == 1


async def test_the_card_id_is_stable_for_the_same_calls_and_differs_for_another_pass():
    from chat_workflow.approval_binding import card_id

    state = _input()
    shown = [dict(CLICK)]
    assert card_id(state, shown) == card_id(state, [dict(CLICK)])
    assert card_id({**state, "iteration_count": 1}, shown) != card_id(state, shown)
    assert card_id(state, [{"name": "click", "params": {"selector": "#other"}}]) != card_id(state, shown)


async def test_with_the_gate_off_a_held_call_ends_the_loop_after_one_model_call_and_one_record(monkeypatch):
    turn = Turn(monkeypatch, gate=False, then_click=True)  # a model that would ask for the click on every call
    with ai_line_world() as filed:
        await turn.start()
        snapshot = await turn.compiled.aget_state(turn.cfg)

    assert len(turn.prompts) == 1, "the held call ended the loop; the model was not asked again"
    assert snapshot.next == () and turn.executed == []
    assert filed.await_count == 1, "one hold, one approval record"
