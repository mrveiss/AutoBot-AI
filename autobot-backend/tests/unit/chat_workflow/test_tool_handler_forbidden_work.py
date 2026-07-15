# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dispatch-level enforcement of the forbidden_work manifest (GH#11145).

Proves the capability boundary is active on the real production tool-dispatch
seam (`ToolHandlerMixin._dispatch_tool_call`) — not just inside the agent loop.
A profile-bound agent (research_agent) is hard-blocked from an out-of-manifest
tool (bash/execute_command) before any handler runs, while the designated
executor (system_agent) and the profile-less chat agent are unaffected.
"""

from types import SimpleNamespace

import pytest

from chat_workflow.models import AgentContext
from chat_workflow.tool_handler import ToolHandlerMixin


def _mixin() -> ToolHandlerMixin:
    """Bare mixin instance — enforcement short-circuits before any other state."""
    return ToolHandlerMixin.__new__(ToolHandlerMixin)


def _ctx(agent_id: str | None) -> SimpleNamespace:
    agent_context = AgentContext(agent_id=agent_id) if agent_id is not None else None
    return SimpleNamespace(agent_context=agent_context)


def test_enforce_blocks_out_of_manifest_tool() -> None:
    """research_agent forbids bash — the seam returns an error and records it."""
    mixin = _mixin()
    results: list[dict] = []
    msg = mixin._enforce_forbidden_work({"name": "bash"}, _ctx("research_agent"), results)

    assert msg is not None
    assert msg.type == "error"
    assert msg.metadata.get("forbidden_by_manifest") is True
    assert results and results[0]["forbidden_by_manifest"] is True
    assert results[0]["status"] == "error"


def test_enforce_matches_by_prefix() -> None:
    """A manifest entry blocks by prefix (execute_command variant)."""
    mixin = _mixin()
    results: list[dict] = []
    msg = mixin._enforce_forbidden_work({"name": "execute_command"}, _ctx("research_agent"), results)

    assert msg is not None
    assert "forbidden" in msg.content


def test_enforce_allows_in_manifest_tool() -> None:
    """research_agent may web_search — no block, nothing recorded."""
    mixin = _mixin()
    results: list[dict] = []
    msg = mixin._enforce_forbidden_work({"name": "web_search"}, _ctx("research_agent"), results)

    assert msg is None
    assert results == []


def test_enforce_noop_for_executor_agent() -> None:
    """system_agent is the designated executor (empty forbidden_work) — bash allowed."""
    mixin = _mixin()
    results: list[dict] = []
    msg = mixin._enforce_forbidden_work({"name": "bash"}, _ctx("system_agent"), results)

    assert msg is None
    assert results == []


def test_enforce_noop_for_profileless_chat_agent() -> None:
    """No agent_context (plain chat) → empty manifest → never blocked."""
    mixin = _mixin()
    results: list[dict] = []
    assert mixin._enforce_forbidden_work({"name": "bash"}, None, results) is None
    assert mixin._enforce_forbidden_work({"name": "bash"}, _ctx("unknown_agent"), results) is None
    assert results == []


@pytest.mark.asyncio
async def test_dispatch_short_circuits_forbidden_tool() -> None:
    """End-to-end: _dispatch_tool_call blocks a forbidden tool before any handler."""
    mixin = _mixin()
    results: list[dict] = []
    messages = []
    async for item in mixin._dispatch_tool_call(
        {"name": "bash", "params": {"command": "rm -rf /"}},
        "session-1",
        "term-1",
        "http://localhost:11434",
        "test-model",
        results,
        [],
        ctx=_ctx("research_agent"),
    ):
        messages.append(item)

    # Only the forbidden-work error is yielded; dispatch returns before any branch.
    assert len(messages) == 1
    assert messages[0].type == "error"
    assert messages[0].metadata.get("forbidden_by_manifest") is True
    assert results[0]["tool"] == "bash"
    assert results[0]["forbidden_by_manifest"] is True
