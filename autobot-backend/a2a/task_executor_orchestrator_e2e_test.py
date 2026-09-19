# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A peer's task is refused a memory-reading agent through the path a real task takes (#16957 AC2).

``execute_a2a_task`` → the real ``DistributedAgentCoordinator.process_request`` →
its real legacy path → the real ``AgentExecutor`` gate. Only the leaves are
stubbed: the router's decision (routing is not the security boundary), the agents
themselves, and the trust store's level. The executor and the orchestrator were
tested at their own layers; this joins them, so a break in the authority's
hand-off between the two fails here.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a.task_executor import execute_a2a_task
from a2a.types import TaskState
from agents.agent_orchestration import coordinator as coordinator_module
from agents.agent_orchestration.agent_execution import AgentExecutor
from agents.agent_orchestration.coordinator import DistributedAgentCoordinator
from agents.agent_orchestration.types import AgentType
from autobot_shared.trust_enums import TrustLevel


def _coordinator(kb_librarian: MagicMock) -> DistributedAgentCoordinator:
    """The real coordinator, without its heavy init: distributed mode off, so the legacy path runs."""
    coordinator = DistributedAgentCoordinator.__new__(DistributedAgentCoordinator)
    coordinator._distributed_manager = SimpleNamespace(is_running=False, distributed_agents={})
    router = SimpleNamespace(
        determine_routing=AsyncMock(return_value={"strategy": "single_agent", "primary_agent": AgentType.RAG})
    )
    rag = MagicMock(process_document_query=AsyncMock(return_value={"status": "success", "response": "answer"}))
    coordinator._executor = AgentExecutor(
        distributed_manager=MagicMock(),
        router=router,
        get_chat_agent=MagicMock(),
        get_system_commands_agent=MagicMock(),
        get_rag_agent=MagicMock(return_value=rag),
        get_kb_librarian=MagicMock(return_value=kb_librarian),
        get_research_agent=MagicMock(),
    )
    return coordinator


async def _submit(level: TrustLevel):
    kb_librarian = MagicMock(process_query=AsyncMock(return_value={"documents": []}))
    tm = MagicMock()
    trust = MagicMock()
    trust.get_trust_level.return_value = level
    scrubbed = SimpleNamespace(text="answer", redaction_count=0)
    evaluated = SimpleNamespace(passed=True, confidence=0.9, eval_reason=None)
    with (
        patch.object(coordinator_module, "LEGACY_AGENTS_AVAILABLE", True),
        patch("a2a.task_executor.get_task_manager", return_value=tm),
        patch("a2a.task_executor.get_trust_manager", return_value=trust),
        patch("a2a.task_executor.scrub_outbound", return_value=scrubbed),
        patch("a2a.task_executor.evaluate_task_output", new=AsyncMock(return_value=evaluated)),
        patch(
            "agents.agent_orchestration.get_distributed_agent_coordinator",
            return_value=_coordinator(kb_librarian),
            create=True,
        ),
    ):
        await execute_a2a_task("task-e2e", "what does the knowledge base say about X", peer_id="alice/peer-x")
    return tm, kb_librarian


@pytest.mark.asyncio
async def test_a_limited_peer_is_refused_the_rag_route_before_the_knowledge_base_is_read():
    tm, kb_librarian = await _submit(TrustLevel.LIMITED)

    tm.update_state.assert_any_call("task-e2e", TaskState.FAILED, message="capability_refused: query_memory")
    kb_librarian.process_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_control_a_standard_peer_reaches_the_same_route():
    """The refusal above comes from the capability, not from a broken chain."""
    tm, kb_librarian = await _submit(TrustLevel.STANDARD)

    kb_librarian.process_query.assert_awaited_once()
    assert not any(c.kwargs.get("message", "").startswith("capability_refused") for c in tm.update_state.call_args_list)
