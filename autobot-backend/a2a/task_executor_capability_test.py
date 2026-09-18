# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A peer's task carries the peer's capabilities to routing, and a refusal fails the task (#16957)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a.task_executor import execute_a2a_task
from a2a.types import TaskState
from agents.agent_orchestration.capability_requirements import refusal
from autobot_shared.trust_enums import TrustLevel


async def _run(level: TrustLevel, orchestrator_result: dict):
    tm = MagicMock()
    trust = MagicMock()
    trust.get_trust_level.return_value = level
    orchestrator = MagicMock(process_request=AsyncMock(return_value=orchestrator_result))
    with (
        patch("a2a.task_executor.get_task_manager", return_value=tm),
        patch("a2a.task_executor.get_trust_manager", return_value=trust),
        patch("agents.agent_orchestration.get_distributed_agent_coordinator", return_value=orchestrator, create=True),
    ):
        await execute_a2a_task("task-1", "what do you remember about X", peer_id="peer-1")
    return tm, orchestrator


@pytest.mark.asyncio
async def test_the_orchestrator_receives_the_peers_capabilities():
    _, orchestrator = await _run(TrustLevel.LIMITED, refusal(["rag"]))

    authority = orchestrator.process_request.await_args.kwargs["authority"]
    assert authority.capabilities == {"discovery", "submit_tasks"}


@pytest.mark.asyncio
async def test_a_refused_route_fails_the_task_naming_the_capability():
    tm, _ = await _run(TrustLevel.LIMITED, refusal(["rag"]))

    tm.update_state.assert_any_call("task-1", TaskState.FAILED, message="capability_refused: query_memory")
    tm.add_artifact.assert_not_called()


@pytest.mark.asyncio
async def test_an_unrecognised_level_grants_nothing():
    """Fail closed: a level the matrix does not know holds no capability, not all of them."""
    _, orchestrator = await _run("not-a-level", refusal(["rag"]))

    assert orchestrator.process_request.await_args.kwargs["authority"].capabilities == frozenset()
