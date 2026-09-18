# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A request is refused an agent its originator may not reach, before any agent runs (#16957)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from a2a.trust_score import Capability, authority_for_level
from agents.agent_orchestration.agent_execution import AgentExecutor, _routed_agent_types
from agents.agent_orchestration.capability_requirements import (
    NEEDS_NO_CAPABILITY,
    REQUIRED_CAPABILITY,
    refused_agents,
)
from agents.agent_orchestration.types import AgentType
from autobot_shared.trust_enums import TrustLevel

#: The distributed agents the coordinator registers (coordinator.py, builtin_distributed_agents).
_DISTRIBUTED = {"classification", "npu_code_search"}

LIMITED = authority_for_level(TrustLevel.LIMITED)  # submit_tasks only -- no query_memory
STANDARD = authority_for_level(TrustLevel.STANDARD)


class TestEveryAgentIsClassified:
    def test_every_routable_agent_is_classified_exactly_once(self):
        routable = {t.value for t in AgentType} | _DISTRIBUTED

        assert set(REQUIRED_CAPABILITY) | set(NEEDS_NO_CAPABILITY) == routable
        assert not set(REQUIRED_CAPABILITY) & set(NEEDS_NO_CAPABILITY)

    def test_every_requirement_is_a_real_capability(self):
        assert all(isinstance(c, Capability) for c in REQUIRED_CAPABILITY.values())


class TestRefusedAgents:
    def test_an_internal_caller_reaches_everything(self):
        assert refused_agents(None, list(REQUIRED_CAPABILITY)) == []

    def test_a_peer_without_query_memory_is_refused_the_memory_readers_only(self):
        assert refused_agents(LIMITED, ["rag", "chat", "research"]) == ["rag", "research"]

    def test_a_peer_with_query_memory_is_refused_nothing(self):
        assert refused_agents(STANDARD, list(REQUIRED_CAPABILITY)) == []


def test_a_multi_agent_decision_names_its_secondaries():
    decision = {"primary_agent": AgentType.CHAT, "secondary_agents": [AgentType.RESEARCH]}

    assert _routed_agent_types(decision) == ["chat", "research"]


def _executor(decision=None):
    router = SimpleNamespace(determine_routing=AsyncMock(return_value=decision))
    chat = MagicMock()
    chat.process_chat_message = AsyncMock(return_value={"status": "success", "response": "hi"})
    return AgentExecutor(
        distributed_manager=MagicMock(add_active_task=AsyncMock(), remove_active_task=AsyncMock()),
        router=router,
        get_chat_agent=MagicMock(return_value=chat),
        get_system_commands_agent=MagicMock(),
        get_rag_agent=MagicMock(),
        get_kb_librarian=MagicMock(),
        get_research_agent=MagicMock(),
    )


class TestTheLegacyPath:
    @pytest.mark.asyncio
    async def test_a_memory_route_is_refused_before_it_runs(self):
        executor = _executor({"strategy": "single_agent", "primary_agent": AgentType.RAG})

        result = await executor.process_with_legacy_agents("what do you know", {}, [], authority=LIMITED)

        assert result["status"] == "refused" and result["missing_capabilities"] == ["query_memory"]
        executor._get_kb_librarian.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_secondary_memory_agent_refuses_the_whole_decision(self):
        decision = {"strategy": "multi_agent", "primary_agent": AgentType.CHAT, "secondary_agents": [AgentType.RESEARCH]}
        executor = _executor(decision)

        result = await executor.process_with_legacy_agents("q", {}, [], authority=LIMITED)

        assert result["refused_agents"] == ["research"]
        executor._get_chat_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_control_a_route_needing_nothing_runs(self):
        """The refusals above come from the capability, not from a broken executor."""
        executor = _executor({"strategy": "single_agent", "primary_agent": AgentType.CHAT})

        result = await executor.process_with_legacy_agents("hi", {}, [], authority=LIMITED)

        assert result["status"] == "success"


class TestTheDistributedPath:
    @staticmethod
    def _with_agent(executor, agent_type):
        agent = SimpleNamespace(agent_id="a-1", agent_type=agent_type, process_request=AsyncMock())
        executor._select_distributed_agent = AsyncMock(return_value=agent)
        return agent

    @pytest.mark.asyncio
    async def test_a_memory_agent_is_refused_not_fallen_back_from(self):
        executor = _executor()
        agent = self._with_agent(executor, "npu_code_search")

        result = await executor.process_with_distributed_agents("find it", {}, [], None, authority=LIMITED)

        assert result["status"] == "refused"
        agent.process_request.assert_not_awaited()
        executor.distributed_manager.add_active_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_internal_caller_reaches_it(self):
        executor = _executor()
        agent = self._with_agent(executor, "npu_code_search")
        agent.process_request.return_value = SimpleNamespace(status="success", result={"response": "ok"})

        result = await executor.process_with_distributed_agents("find it", {}, [], None, authority=None)

        assert result["status"] == "success"
        agent.process_request.assert_awaited_once()
