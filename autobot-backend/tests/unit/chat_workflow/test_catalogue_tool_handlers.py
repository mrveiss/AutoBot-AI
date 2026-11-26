# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`query_self_model` and the read-only system tools at the PRODUCTION dispatch seam (#22278, #22267).

``ToolRegistry.execute_tool`` has no production caller, so a tool served only there is unreachable from chat.
These tests drive ``_dispatch_tool_call`` -- the seam every real tool call runs through.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.ai_lines import VERIFIED_USER_KEY
from chat_workflow.tool_handler import ToolHandlerMixin

_DISPATCH_ARGS = {
    "session_id": "sess-1",
    "terminal_session_id": "term-1",
    "ollama_endpoint": "http://127.0.0.1:11434",
    "selected_model": "test-model",
}


def _mixin() -> ToolHandlerMixin:
    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
    mixin._enforce_forbidden_work = lambda *a, **k: None
    mixin._enforce_config_protection = lambda *a, **k: None
    mixin._enforce_fact_forcing = lambda *a, **k: None
    mixin._enforce_ai_line = AsyncMock(return_value=None)
    return mixin


async def _dispatch(tool_call: dict, results: list, user_id: str | None = "user-1") -> list:
    ctx = SimpleNamespace(consecutive_invalid_tool_calls=0, context={VERIFIED_USER_KEY: user_id} if user_id else {})
    return [
        msg
        async for msg in _mixin()._dispatch_tool_call(
            tool_call, execution_results=results, additional_response_parts=[], ctx=ctx, **_DISPATCH_ARGS
        )
    ]


def _registry(result: dict):
    return patch("tools.tool_registry.ToolRegistry.execute_tool", new=AsyncMock(return_value=result))


@pytest.mark.asyncio
async def test_query_self_model_is_reachable_and_runs_as_the_verified_user():
    results = []
    answer = {"result": "1 of 1 visible matching entities:", "status": "success"}
    with _registry(answer) as execute:
        msgs = await _dispatch({"name": "query_self_model", "params": {"kind": "tool"}}, results)

    execute.assert_awaited_once_with("query_self_model", {"kind": "tool"}, "user-1")
    assert msgs[0].type == "command_output" and "visible matching" in msgs[0].content
    assert results[0]["tool"] == "query_self_model" and results[0]["status"] == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["query_system_information", "list_system_services"])
async def test_the_read_only_system_tools_are_reachable_from_chat(tool):
    results = []
    with _registry({"result": "ok", "status": "success"}) as execute:
        msgs = await _dispatch({"name": tool, "params": {}}, results)

    execute.assert_awaited_once_with(tool, {}, "user-1")
    assert msgs[0].content == "ok" and results[0]["tool"] == tool


@pytest.mark.asyncio
async def test_no_verified_user_is_refused_before_any_tool_runs():
    results = []
    with _registry({"result": "none", "status": "success"}) as execute:
        msgs = await _dispatch({"name": "query_system_information", "params": {"user_id": "x"}}, results, user_id=None)

    execute.assert_not_awaited()
    assert msgs[0].type == "error" and results[0]["status"] == "error"


@pytest.mark.asyncio
async def test_a_tool_exception_becomes_an_error_message_not_a_crash():
    results = []
    with patch("tools.tool_registry.ToolRegistry.execute_tool", new=AsyncMock(side_effect=RuntimeError("boom"))):
        msgs = await _dispatch({"name": "list_system_services", "params": {}}, results)

    assert msgs[0].type == "error" and "boom" in msgs[0].content and results[0]["status"] == "error"


@pytest.mark.asyncio
async def test_a_schema_violation_is_refused_before_the_tool_runs():
    with _registry({"result": "x", "status": "success"}) as execute:
        msgs = await _dispatch({"name": "query_self_model", "params": {"kind": "not-a-kind"}}, [])

    execute.assert_not_awaited()
    assert msgs[0].metadata.get("schema_validation_failed")
