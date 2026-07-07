# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
End-to-end wiring: AgentProfile.forbidden_work -> AgentLoopConfig.forbidden_tools (GH#11145).

#11139 delivered the enforcement primitive (``_check_forbidden``); this proves the
connective tissue: constructing ``AgentLoop`` with an ``agent_id`` resolves that
agent's ``forbidden_work`` manifest from ``AgentRegistry`` and hard-blocks the
forbidden tools through a real dispatch path.

Acceptance criteria:
  - ``agent_id`` populates ``config.forbidden_tools`` from the agent's profile.
  - The designated executor (``system_agent``, no ``forbidden_work``) stays unbounded.
  - No / unknown ``agent_id`` is a no-op (backward compatible).
  - An explicit ``config.forbidden_tools`` is never overwritten by the manifest.
  - A forbidden tool is blocked in ``_execute_tools`` before the approval gate.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_loop.loop import AgentLoop
from agent_loop.types import AgentLoopConfig


def _make_loop(agent_id: str | None = None, config: AgentLoopConfig | None = None) -> AgentLoop:
    event_stream = MagicMock()
    event_stream.get_latest = AsyncMock(return_value=[])
    event_stream.publish = AsyncMock()
    cfg = config or AgentLoopConfig(
        mandatory_think_enabled=False,
        think_on_completion=False,
        log_iterations=False,
    )
    return AgentLoop(event_stream=event_stream, config=cfg, agent_id=agent_id)


class TestManifestWiring:
    def test_agent_id_populates_forbidden_tools_from_registry(self) -> None:
        # research_agent.forbidden_work == _INFRA_AND_SHELL_TOOLS (bash, deploy, ...)
        loop = _make_loop(agent_id="research_agent")
        assert "bash" in loop.config.forbidden_tools
        assert "deploy" in loop.config.forbidden_tools

    def test_executor_agent_has_no_boundary(self) -> None:
        # system_agent is the designated executor: intentionally no forbidden_work.
        loop = _make_loop(agent_id="system_agent")
        assert loop.config.forbidden_tools == frozenset()

    def test_no_agent_id_is_unbounded(self) -> None:
        loop = _make_loop(agent_id=None)
        assert loop.config.forbidden_tools == frozenset()

    def test_unknown_agent_is_unbounded(self) -> None:
        loop = _make_loop(agent_id="does_not_exist")
        assert loop.config.forbidden_tools == frozenset()

    def test_explicit_config_forbidden_tools_not_overwritten(self) -> None:
        cfg = AgentLoopConfig(
            mandatory_think_enabled=False,
            think_on_completion=False,
            log_iterations=False,
            forbidden_tools=frozenset({"custom_tool"}),
        )
        loop = _make_loop(agent_id="research_agent", config=cfg)
        assert loop.config.forbidden_tools == frozenset({"custom_tool"})

    def test_agent_id_is_recorded(self) -> None:
        loop = _make_loop(agent_id="research_agent")
        assert loop.agent_id == "research_agent"


class TestEndToEndDispatch:
    """Prove enforcement is active end-to-end when the loop runs as an agent."""

    @pytest.mark.asyncio
    async def test_research_agent_cannot_execute_bash(self) -> None:
        loop = _make_loop(agent_id="research_agent")
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        loop._check_approvals = AsyncMock(return_value={})
        loop.tool_executor = MagicMock()

        result = await loop._execute_tools([{"tool_name": "bash", "args": {"cmd": "ls"}}])

        assert "bash" in result and "forbidden" in result["bash"]["error"].lower()
        loop._check_approvals.assert_not_awaited()
        loop.tool_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_research_agent_allows_non_forbidden_tool(self) -> None:
        loop = _make_loop(agent_id="research_agent")
        loop._check_tool_call_repetition = MagicMock(return_value=None)
        # Stop right after the forbidden check to prove read_file passed it.
        loop._check_approvals = AsyncMock(return_value={"read_file": {"error": "stop"}})

        result = await loop._execute_tools([{"tool_name": "read_file", "args": {}}])

        loop._check_approvals.assert_awaited_once()
        assert result == {"read_file": {"error": "stop"}}
