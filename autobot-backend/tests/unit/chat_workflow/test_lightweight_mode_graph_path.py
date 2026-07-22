# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11612: lightweight_mode_used must survive the LangGraph path into the
response metadata the frontend cost badge reads.

Root cause: graph.py::prepare_llm computed a ctx carrying
lightweight_mode_used (via manager._create_llm_iteration_context) but
discarded it, never writing it back into state["context"]. generate_response
then rebuilds ctx from the raw state["context"] via _build_llm_iteration_context,
so the flag was gone. Separately, the ContextVar that the streamed-message
metadata reads was only set by _execute_llm_continuation_loop, a wrapper the
graph path bypasses (it calls _run_continuation_loop_iteration directly).

These tests pin both halves of the fix.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _prepare_llm():
    try:
        from chat_workflow.graph import prepare_llm
    except ImportError as exc:  # env-dependent chain; a real regression still fails
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return prepare_llm


def _build_ctx():
    from chat_workflow.graph import _build_llm_iteration_context

    return _build_llm_iteration_context


def _mock_manager(lightweight_mode: bool):
    from chat_workflow.manager import ChatWorkflowManager

    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    manager.get_or_create_session = AsyncMock(return_value=MagicMock(session_id="s1"))
    manager._prepare_llm_workflow_params = AsyncMock(
        return_value={
            "endpoint": "http://x/api/generate",
            "model": "m",
            "prompt": "p",
            "system_prompt": "s",
            "used_knowledge": False,
            "citations": [],
            "lightweight_mode_used": lightweight_mode,
        }
    )
    return manager


@pytest.mark.asyncio
async def test_prepare_llm_persists_lightweight_mode_into_state_context():
    """prepare_llm must write lightweight_mode_used into the returned
    state["context"], not just into the ctx it discards."""
    prepare_llm = _prepare_llm()
    manager = _mock_manager(lightweight_mode=True)
    config = {"configurable": {"manager": manager}}
    state = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "user_message": "hi",
        "context": {"company_id": "co-1"},
    }

    result = await prepare_llm(state, config)

    assert result["context"]["lightweight_mode_used"] is True
    # Pre-existing context keys must survive the merge.
    assert result["context"]["company_id"] == "co-1"


@pytest.mark.asyncio
async def test_prepare_llm_to_generate_response_roundtrip_carries_flag():
    """End-to-end: prepare_llm's state update, fed back into state, must let
    _build_llm_iteration_context (used by generate_response) see the flag —
    this is exactly the seam the graph path previously dropped it at."""
    prepare_llm = _prepare_llm()
    build_ctx = _build_ctx()
    manager = _mock_manager(lightweight_mode=True)
    config = {"configurable": {"manager": manager}}
    state = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "user_message": "hi",
        "context": {},
    }

    update = await prepare_llm(state, config)
    state.update(update)

    ctx = build_ctx(state)

    assert ctx.context.get("lightweight_mode_used") is True


@pytest.mark.asyncio
async def test_prepare_llm_carries_false_when_not_lightweight():
    prepare_llm = _prepare_llm()
    build_ctx = _build_ctx()
    manager = _mock_manager(lightweight_mode=False)
    config = {"configurable": {"manager": manager}}
    state = {
        "session_id": "s1",
        "terminal_session_id": "t1",
        "user_message": "hi",
        "context": {},
    }

    update = await prepare_llm(state, config)
    state.update(update)

    ctx = build_ctx(state)

    assert ctx.context.get("lightweight_mode_used") is False


@pytest.mark.asyncio
async def test_run_continuation_loop_iteration_sets_contextvar_from_ctx():
    """The graph path calls _run_continuation_loop_iteration directly, never
    _execute_llm_continuation_loop — so the ContextVar the streamed-message
    metadata reads (_current_lightweight_mode, see manager.py _init_streaming_message)
    must be set inside _run_continuation_loop_iteration itself (#11612)."""
    import chat_workflow.manager as manager_module
    from chat_workflow.manager import ChatWorkflowManager, LLMIterationContext

    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    observed = {}

    async def fake_iteration(http_client, current_prompt, iteration, ctx):
        observed["seen"] = manager_module._current_lightweight_mode.get()
        yield ("response text", [], False)

    manager._run_continuation_iteration = fake_iteration

    ctx = LLMIterationContext(
        ollama_endpoint="http://x",
        selected_model="m",
        session_id="s1",
        terminal_session_id="t1",
        used_knowledge=False,
        rag_citations=[],
        workflow_messages=[],
        system_prompt="s",
        initial_prompt="p",
        message="hi",
        context={"lightweight_mode_used": True},
    )

    assert manager_module._current_lightweight_mode.get() is False  # ambient default

    async for _item in manager._run_continuation_loop_iteration(None, "p", 1, ctx):
        pass

    assert observed["seen"] is True
    # Token must be reset once the iteration completes — no leakage to callers.
    assert manager_module._current_lightweight_mode.get() is False
