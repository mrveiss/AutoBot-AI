# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for per-agent forbidden_work enforcement in the agent loop (GH#11139).

Acceptance criteria:
  - A tool matching the agent's forbidden_tools manifest is hard-blocked BEFORE
    the approval gate (returns a denial result, never requests approval).
  - Matching is by exact name and by prefix (e.g. "bash_run" -> "bash").
  - Empty forbidden_tools (the default) is a no-op — no behavior change.
"""

from unittest.mock import AsyncMock, MagicMock

from agent_loop.loop import AgentLoop
from agent_loop.types import AgentLoopConfig


def _make_loop(forbidden: frozenset[str] = frozenset()) -> AgentLoop:
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    config = AgentLoopConfig(
        mandatory_think_enabled=False,
        think_on_completion=False,
        log_iterations=False,
        forbidden_tools=forbidden,
    )
    return AgentLoop(event_stream=event_stream, config=config)


class TestForbiddenToolMatching:
    def test_exact_name_match(self) -> None:
        loop = _make_loop(frozenset({"bash", "deploy"}))
        assert loop._forbidden_tool_name({"tool_name": "deploy"}) == "deploy"

    def test_prefix_match(self) -> None:
        loop = _make_loop(frozenset({"bash"}))
        assert loop._forbidden_tool_name({"tool_name": "bash_run"}) == "bash"

    def test_allowed_tool_returns_none(self) -> None:
        loop = _make_loop(frozenset({"bash"}))
        assert loop._forbidden_tool_name({"tool_name": "read_file"}) is None

    def test_empty_manifest_is_noop(self) -> None:
        loop = _make_loop(frozenset())
        assert loop._forbidden_tool_name({"tool_name": "bash"}) is None


class TestCheckForbidden:
    def test_blocks_first_forbidden_tool(self) -> None:
        loop = _make_loop(frozenset({"ansible"}))
        result = loop._check_forbidden(
            [{"tool_name": "read_file"}, {"tool_name": "ansible"}]
        )
        assert "ansible" in result
        assert "forbidden" in result["ansible"]["error"].lower()

    def test_passes_when_nothing_forbidden(self) -> None:
        loop = _make_loop(frozenset({"ansible"}))
        assert loop._check_forbidden([{"tool_name": "read_file"}]) == {}

    def test_empty_manifest_passes_everything(self) -> None:
        loop = _make_loop(frozenset())
        assert loop._check_forbidden([{"tool_name": "bash"}, {"tool_name": "deploy"}]) == {}
