# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The approve request answers without waiting on an LLM call, and a second approve is a 409 (#19951)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fastapi import HTTPException

from api.agent_terminal import approve_agent_command
from services.agent_terminal import decision_response
from services.agent_terminal.decision_session import NO_PENDING_APPROVAL
from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.service import AgentTerminalService
from services.agent_terminal.shared_session_state_20674_test import SID, _raise_pending, _service, _worker
from services.command_approval_manager import AgentRole

pytestmark = pytest.mark.asyncio

BOUND = 5


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _post_execution_service(interpret) -> AgentTerminalService:
    """A service whose post-execution steps are real except the collaborators that talk to other systems."""
    service = AgentTerminalService.__new__(AgentTerminalService)
    service._save_command_to_chat = AsyncMock()
    service._owns_interpretation = AsyncMock(return_value=True)
    service._update_and_broadcast_approval_status = AsyncMock()
    service.approval_handler = AsyncMock()
    service.session_manager = AsyncMock()
    service.chat_workflow_manager = MagicMock()
    service.chat_workflow_manager.interpret_terminal_command = interpret
    return service


def _session() -> AgentTerminalSession:
    session = AgentTerminalSession(
        session_id=SID, agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id="conv"
    )
    session.pending_approval = {"command": "uptime", "command_id": "cmd-1"}
    return session


async def test_the_approve_path_returns_while_the_llm_interpretation_is_still_running():
    release, started = asyncio.Event(), asyncio.Event()

    async def slow_interpretation(**_kw):
        started.set()
        await release.wait()  # an LLM call that has not finished

    service = _post_execution_service(slow_interpretation)
    await asyncio.wait_for(
        service._post_execution_updates(_session(), "uptime", {"stdout": "x"}, "LOW", "u", None, False), BOUND
    )
    assert not release.is_set()  # the request completed with the interpretation still pending
    await asyncio.wait_for(started.wait(), BOUND)  # ... and it does run, after the response
    release.set()


async def test_the_interpretation_still_runs_for_the_decision_that_was_pending_when_it_was_scheduled():
    seen = []
    service = _post_execution_service(AsyncMock(side_effect=lambda **kw: seen.append(kw)))
    owner = service._owns_interpretation
    session = _session()
    service._interpret_in_background(session, "uptime", {"stdout": "out"})
    session.pending_approval = None  # settle_pending clears it right after the task is scheduled
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert seen and seen[0]["command"] == "uptime"
    assert owner.await_args.args[0].pending_approval == {"command": "uptime", "command_id": "cmd-1"}


async def test_a_second_approve_of_the_same_hold_is_refused_and_nothing_runs_again(redis):
    worker = _worker(redis)
    await _raise_pending(worker)
    service = _service(worker)
    first = await service.approve_command(SID, True)
    second = await service.approve_command(SID, True)
    assert first == {"status": "approved"}
    assert second == {"status": "error", "error": NO_PENDING_APPROVAL}
    service._execute_approved_command.assert_awaited_once()


async def test_the_route_turns_that_refusal_into_a_409(redis):
    worker = _worker(redis)
    await _raise_pending(worker)
    service = _service(worker)
    request = MagicMock(approved=True, comment=None, auto_approve_future=False, remember_for_project=False)
    request.project_path, request.user_id = None, None
    user = {"username": "alice", "user_id": "u1", "role": "admin"}
    await approve_agent_command(SID, user, request, service)
    with pytest.raises(HTTPException) as refused:
        await approve_agent_command(SID, user, request, service)
    assert refused.value.status_code == 409 and refused.value.detail == NO_PENDING_APPROVAL
    service._execute_approved_command.assert_awaited_once()


async def test_other_results_pass_through_unchanged():
    for result in ({"status": "approved"}, {"status": "error", "error": "Session not found"}):
        assert decision_response(result) is result


async def test_the_websocket_twin_carries_the_same_already_decided_semantics(redis, monkeypatch):
    from api import agent_terminal_access as access

    worker = _worker(redis)
    await _raise_pending(worker)
    service = _service(worker)
    monkeypatch.setattr(access, "get_agent_terminal_service", lambda redis_client=None: service)
    monkeypatch.setattr(access, "get_redis_client", lambda: redis)
    monkeypatch.setattr(access, "require_interactive_human", lambda *a, **k: None)
    monkeypatch.setattr(access, "require_session_access", AsyncMock())
    user = {"username": "alice"}
    first = await access.approve_over_websocket({"terminal_session_id": SID, "approved": True}, user)
    second = await access.approve_over_websocket({"terminal_session_id": SID, "approved": True}, user)
    assert first == {"status": "approved"}
    assert second["status"] == "error" and second["status_code"] == 409
    service._execute_approved_command.assert_awaited_once()
