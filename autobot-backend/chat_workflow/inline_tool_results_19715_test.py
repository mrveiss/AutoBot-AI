# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19715: inline tool results reach the next prompt, loops are caught, and the cap forces an answer."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from chat_workflow import graph, limits
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.tool_call_loop import (
    _LOOP_ABORT_THRESHOLD,
    _LOOP_WARNING_MSG,
    FINAL_ANSWER_INSTRUCTION,
    stamp_call_fingerprint,
    summary_fingerprints,
)


def _state(**extra):
    state = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "user_message": "what is X",
        "context": {},
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
        "iteration_count": 0,
        "all_llm_responses": [],
        "tool_calls": [],
    }
    return {**state, **extra}


def _config(manager):
    return {"configurable": {"manager": manager, "stream_callback": None}}


def _search_summary(query="X", output="found it"):
    summary = {"tool": "web_search", "status": "success", "output": output}
    stamp_call_fingerprint([summary], {"name": "web_search", "params": {"query": query}})
    return summary


def _manager_recording_prompts(results_per_pass):
    """A manager whose inline pass records its prompt and adds that pass's tool results."""
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    prompts = []
    passes = iter(results_per_pass)

    async def one_pass(_http, prompt, _iteration, ctx):
        prompts.append(prompt)
        ctx.execution_history.extend(next(passes))
        yield ("reply", True)

    manager._run_continuation_loop_iteration = one_pass
    return manager, prompts


async def _generate(manager, state):
    with patch("chat_workflow.session_role.CHAT_APPROVAL_GATE_ENABLED", False):
        return await graph.generate_response(state, _config(manager))


@pytest.mark.asyncio
async def test_the_second_iterations_prompt_carries_the_first_ones_result() -> None:
    manager, prompts = _manager_recording_prompts([[_search_summary()], []])
    first = await _generate(manager, _state())
    assert len(first["execution_history"]) == 1
    await _generate(manager, _state(**first))
    assert prompts[0] == "p"
    assert "found it" in prompts[1]


@pytest.mark.asyncio
async def test_a_pass_reports_only_its_own_calls_and_keeps_the_whole_history() -> None:
    manager, _ = _manager_recording_prompts([[_search_summary("second")]])
    result = await _generate(manager, _state(execution_history=[_search_summary("first")]))
    assert len(result["tool_calls"]) == 1 and len(result["execution_history"]) == 2


@pytest.mark.asyncio
async def test_a_loop_warning_stays_in_the_prompt_with_the_results() -> None:
    manager, prompts = _manager_recording_prompts([[]])
    state = _state(execution_history=[_search_summary()], tool_loop_warning="STOP REPEATING")
    await _generate(manager, state)
    assert "STOP REPEATING" in prompts[0] and "found it" in prompts[0]


async def _execute(state):
    return await graph.execute_tools(state, _config(MagicMock()))


@pytest.mark.asyncio
async def test_an_identical_inline_call_trips_the_loop_detection() -> None:
    state = _state(iteration_count=3, should_continue=True, tool_calls=[_search_summary()])
    state["tool_call_fingerprints"] = summary_fingerprints([_search_summary()]) * 2
    result = await _execute(state)
    assert result["tool_loop_count"] == 1
    assert result["tool_loop_warning"] == _LOOP_WARNING_MSG
    assert result["tool_calls"] == []


@pytest.mark.asyncio
async def test_the_same_tool_with_other_arguments_is_not_a_loop() -> None:
    state = _state(iteration_count=3, should_continue=True, tool_calls=[_search_summary("new")])
    state["tool_call_fingerprints"] = summary_fingerprints([_search_summary("old")]) * 2
    assert (await _execute(state))["tool_loop_count"] == 0


@pytest.mark.asyncio
async def test_repeated_loops_stop_with_a_message_to_the_user() -> None:
    state = _state(iteration_count=4, should_continue=True, tool_calls=[_search_summary()], tool_loop_count=1)
    state["tool_call_fingerprints"] = summary_fingerprints([_search_summary()]) * 2
    result = await _execute(state)
    assert result["tool_loop_count"] == _LOOP_ABORT_THRESHOLD
    assert "stopped the loop" in result["workflow_messages"][-1]["content"]
    assert graph.route_after_execution({**state, **result}) == "persist_conversation"


def test_the_cap_routes_to_a_final_answer_and_below_it_loops() -> None:
    cap = limits.MAX_CONTINUATION_ITERATIONS
    assert graph.route_after_execution(_state(should_continue=True, iteration_count=cap)) == "force_final_answer"
    assert graph.route_after_execution(_state(should_continue=True, iteration_count=cap - 1)) == "generate_response"
    assert graph.route_after_execution(_state(should_continue=False, iteration_count=cap)) == "persist_conversation"


def _final_manager():
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    return manager


async def _final(plan):
    state = _state(execution_history=[_search_summary()], iteration_count=5, should_continue=True)
    with patch.object(graph, "_run_llm_iteration_plan", plan):
        return await graph.force_final_answer(state, _config(_final_manager())), plan


@pytest.mark.asyncio
async def test_the_final_pass_dispatches_nothing_and_asks_for_an_answer_from_the_results() -> None:
    plan = AsyncMock(return_value=([{"type": "response", "content": "the answer"}], "the answer", [], True))
    result, plan = await _final(plan)
    ctx = plan.await_args.args[1]
    assert FINAL_ANSWER_INSTRUCTION in ctx.initial_prompt and "found it" in ctx.initial_prompt
    assert result["should_continue"] is False and result["all_llm_responses"] == ["the answer"]
    assert result["workflow_messages"][-1]["type"] == "response"


@pytest.mark.asyncio
async def test_a_failed_final_pass_still_ends_on_a_message_to_the_user() -> None:
    result, _ = await _final(AsyncMock(side_effect=aiohttp.ClientError()))
    assert result["workflow_messages"][-1]["type"] == "response"
    assert "ran out of steps" in result["workflow_messages"][-1]["content"]


def test_several_results_of_one_call_count_as_one_call() -> None:
    first, second = _search_summary(), _search_summary()
    assert len(summary_fingerprints([first, second])) == 1


def test_a_shell_result_is_identified_by_its_command() -> None:
    one = summary_fingerprints([{"command": "ls"}])
    assert one != summary_fingerprints([{"command": "pwd"}])
