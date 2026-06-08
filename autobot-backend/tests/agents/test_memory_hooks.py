# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for _before_process / _after_process memory lifecycle hooks (#3771).

Verifies:
- hook call order (before -> handler -> after)
- hook failures are isolated and never crash the agent
- default no-op hooks do not alter existing agent behaviour
"""

import sys
import types
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Pre-populate sys.modules with a hollow 'agents' package so that
# agents/standardized_agent.py's relative imports work without executing
# agents/__init__.py (which pulls in llama_index and other unavailable libs).
# Pattern documented in CLAUDE.md key discoveries:
#   "pytest conftest.py hollow-api pattern: pre-populate sys.modules['api']
#    with types.ModuleType(__path__=[api_dir])"
# ---------------------------------------------------------------------------
_AGENTS_DIR = Path(__file__).resolve().parents[2] / "agents"

if "agents" not in sys.modules:
    _agents_pkg = types.ModuleType("agents")
    _agents_pkg.__path__ = [str(_AGENTS_DIR)]  # type: ignore[assignment]
    _agents_pkg.__package__ = "agents"
    sys.modules["agents"] = _agents_pkg

# Now the regular package imports work because 'agents' is already registered.
from agents.base_agent import AgentRequest  # noqa: E402
from agents.standardized_agent import ActionHandler, StandardizedAgent  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal concrete agent for testing
# ---------------------------------------------------------------------------


class _MinimalAgent(StandardizedAgent):
    """Minimal StandardizedAgent subclass used in unit tests."""

    def __init__(self):
        super().__init__("test_agent")
        self.register_action_handler(
            "echo",
            ActionHandler(
                handler_method="handle_echo",
                required_params=["text"],
            ),
        )

    def _get_system_prompt(self) -> str:
        return "test"

    def get_capabilities(self) -> List[str]:
        return ["echo"]

    async def handle_echo(self, request: AgentRequest) -> Dict[str, Any]:
        return {"echoed": request.payload["text"]}


def _make_request(action: str = "echo", payload: dict = None, context: dict = None) -> AgentRequest:
    return AgentRequest(
        request_id=str(uuid.uuid4()),
        agent_type="test_agent",
        action=action,
        payload=payload or {"text": "hello"},
        context=context or {},
    )


# ---------------------------------------------------------------------------
# Hook call-order tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_before_process_called_before_handler():
    """_before_process must be awaited before the action handler fires."""
    agent = _MinimalAgent()
    call_order = []

    original_before = agent._before_process
    original_handler = agent.handle_echo

    async def spy_before(ctx):
        call_order.append("before")
        return await original_before(ctx)

    async def spy_handler(req):
        call_order.append("handler")
        return await original_handler(req)

    agent._before_process = spy_before
    agent.handle_echo = spy_handler

    await agent.process_request(_make_request())

    assert call_order.index("before") < call_order.index("handler")


@pytest.mark.asyncio
async def test_after_process_called_after_handler():
    """_after_process must be awaited after the action handler completes."""
    agent = _MinimalAgent()
    call_order = []

    original_after = agent._after_process
    original_handler = agent.handle_echo

    async def spy_after(ctx, result):
        call_order.append("after")
        return await original_after(ctx, result)

    async def spy_handler(req):
        call_order.append("handler")
        return await original_handler(req)

    agent._after_process = spy_after
    agent.handle_echo = spy_handler

    await agent.process_request(_make_request())

    assert call_order.index("handler") < call_order.index("after")


@pytest.mark.asyncio
async def test_full_hook_order():
    """Full order must be: before -> handler -> after."""
    agent = _MinimalAgent()
    call_order = []

    agent._before_process = AsyncMock(side_effect=lambda ctx: (call_order.append("before"), ctx)[1])
    agent._after_process = AsyncMock(side_effect=lambda ctx, r: call_order.append("after"))
    original_handler = agent.handle_echo

    async def spy_handler(req):
        call_order.append("handler")
        return await original_handler(req)

    agent.handle_echo = spy_handler

    response = await agent.process_request(_make_request())

    assert response.status == "success"
    assert call_order == ["before", "handler", "after"]


# ---------------------------------------------------------------------------
# Hook failure isolation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_before_process_failure_does_not_crash_agent():
    """A raised exception in _before_process must not prevent handler from running."""
    agent = _MinimalAgent()

    async def failing_before(ctx):
        raise RuntimeError("simulated before-hook failure")

    agent._before_process = failing_before

    response = await agent.process_request(_make_request())

    assert response.status == "success"
    assert response.result["echoed"] == "hello"


@pytest.mark.asyncio
async def test_after_process_failure_does_not_crash_agent():
    """A raised exception in _after_process must not prevent a success response."""
    agent = _MinimalAgent()

    async def failing_after(ctx, result):
        raise RuntimeError("simulated after-hook failure")

    agent._after_process = failing_after

    response = await agent.process_request(_make_request())

    assert response.status == "success"
    assert response.result["echoed"] == "hello"


@pytest.mark.asyncio
async def test_both_hooks_failing_does_not_crash_agent():
    """Both hooks may fail independently — agent must still succeed."""
    agent = _MinimalAgent()

    async def failing_before(ctx):
        raise ValueError("before error")

    async def failing_after(ctx, result):
        raise ValueError("after error")

    agent._before_process = failing_before
    agent._after_process = failing_after

    response = await agent.process_request(_make_request())

    assert response.status == "success"


# ---------------------------------------------------------------------------
# Default no-op hook behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_before_process_returns_context_unchanged():
    """Default _before_process must return the same context dict."""
    agent = _MinimalAgent()
    ctx = {"session_id": "abc", "user": "alice"}
    result = await agent._before_process(ctx)
    assert result is ctx


@pytest.mark.asyncio
async def test_default_after_process_returns_none():
    """Default _after_process must be a coroutine returning None."""
    agent = _MinimalAgent()
    result = await agent._after_process({"session_id": "abc"}, {"data": 1})
    assert result is None


@pytest.mark.asyncio
async def test_no_op_hooks_preserve_existing_behaviour():
    """With default hooks, process_request must behave identically to pre-hook code."""
    agent = _MinimalAgent()
    response = await agent.process_request(_make_request(payload={"text": "world"}))

    assert response.status == "success"
    assert response.result["echoed"] == "world"
    assert response.agent_type == "test_agent"
