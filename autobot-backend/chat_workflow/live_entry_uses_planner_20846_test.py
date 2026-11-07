# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The live entry point goes through the planner node (#21023, part of #20846), with a control.

Drives the real ``ChatWorkflowManager.process_message_stream`` over the real ``build_chat_graph()`` compiled on
``MemorySaver``. Only the manager's I/O seams and the LLM pass are stubbed; the planner is the real
``LLMPlannerModule`` over a fake Redis, its model call patched.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from chat_workflow import graph as graph_module
from chat_workflow import plan_runner
from chat_workflow.manager import ChatWorkflowManager
from planner import LLMPlannerModule

pytestmark = pytest.mark.asyncio

_PLAN = {
    "steps": [{"step_number": i, "description": f"s{i}", "depends_on": [i - 1] if i > 1 else []} for i in (1, 2, 3)]
}


class _Redis:
    def __init__(self):
        self.d = {}

    async def set(self, k, v, ex=None):
        self.d[k] = v

    async def get(self, k):
        return self.d.get(k)


def _manager() -> ChatWorkflowManager:
    m = ChatWorkflowManager.__new__(ChatWorkflowManager)
    m._active_streams = 0
    m.redis_client = _Redis()
    m.rag_service = None
    session = SimpleNamespace(metadata={}, conversation_history=[], kb_principal=lambda: None)

    async def intents(*a, **k):
        yield False

    llm_ctx = SimpleNamespace(
        ollama_endpoint="e",
        selected_model="m",
        system_prompt="",
        initial_prompt="hi",
        used_knowledge=False,
        rag_citations=[],
    )
    m._apply_session_role = AsyncMock(side_effect=lambda sid, ctx, role, scope: ctx or {})
    m._initialize_chat_session = AsyncMock(return_value=(session, "term", False))
    m._persist_user_message = AsyncMock()
    m._process_special_intents = intents
    m.get_or_create_session = AsyncMock(return_value=session)
    m._prepare_llm_workflow_params = AsyncMock(return_value={"prompt": "hi", "lightweight_mode_used": False})
    m._create_llm_iteration_context = lambda *a, **k: llm_ctx
    m._persist_workflow_messages = AsyncMock()
    m._build_and_log_continuation_prompt = lambda ctx, hist: "continued"
    return m


async def _two_passes(self, http, prompt, iteration, ctx):
    """Pass 1 'runs a tool' and asks to continue; pass 2 answers."""
    if iteration == 1:
        ctx.execution_history.append({"tool": "t", "status": "success"})
    yield {"type": "response", "content": f"pass {iteration}", "metadata": {}}
    yield ("answer", iteration == 1)


async def _drive(manager):
    saver = MemorySaver()
    graph_module._compiled_graph = None
    try:
        with (
            patch.object(graph_module, "get_redis_checkpointer", AsyncMock(return_value=saver)),
            patch.object(ChatWorkflowManager, "_run_continuation_loop_iteration", _two_passes),
            patch("autobot_shared.http_client.get_http_client", lambda: None),
            patch("chat_workflow.graph.attachment_prompt", AsyncMock(return_value="p")),
        ):
            return [m async for m in manager.process_message_stream("live-20846", "build me a thing")]
    finally:
        graph_module._compiled_graph = None


def _shape(messages):
    return [(m.type, m.content) for m in messages]


def _spies():
    return (
        patch.object(plan_runner.PlannerLLMClient, "generate", AsyncMock(return_value=json.dumps(_PLAN))),
        patch.object(LLMPlannerModule, "create_plan", autospec=True, side_effect=LLMPlannerModule.create_plan),
        patch.object(LLMPlannerModule, "complete_step", autospec=True, side_effect=LLMPlannerModule.complete_step),
    )


async def test_flag_on_the_live_turn_creates_and_advances_a_plan():
    gen, create, complete = _spies()
    with (
        gen,
        create as create_spy,
        complete as complete_spy,
        patch.object(plan_runner, "planner_enabled", return_value=True),
    ):
        await _drive(_manager())
    assert create_spy.call_count == 1 and complete_spy.call_count == 1


async def test_flag_off_the_planner_is_never_called_and_the_output_matches_the_baseline():
    gen, create, complete = _spies()
    with (
        gen as llm_spy,
        create as create_spy,
        complete as complete_spy,
        patch.object(plan_runner, "planner_enabled", return_value=False),
    ):
        off = await _drive(_manager())
    assert create_spy.call_count == complete_spy.call_count == llm_spy.call_count == 0
    gen, create, complete = _spies()
    with gen, create, complete, patch.object(plan_runner, "planner_enabled", return_value=True):
        on = await _drive(_manager())
    assert off, "control: the baseline run produced output, so equality below is not two empty lists"
    assert _shape(off) == _shape(on)  # planning adds state and a prompt line; it adds no user-visible message here
