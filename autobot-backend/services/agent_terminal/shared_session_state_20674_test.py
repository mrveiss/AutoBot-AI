# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Two workers share one Redis; a decision acts on its state, not on a worker's copy (#20674)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from autobot_shared.status_enums import CommandRisk
from services.agent_terminal.ai_line_gate import settle_pending
from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.pending_claim import CLAIM_WRITE_TTL, _claim_key, claim_pending_slot
from services.agent_terminal.service import AgentTerminalService
from services.agent_terminal.session_manager import SessionManager
from services.command_approval_manager import AgentRole

pytestmark = pytest.mark.asyncio

SID = "sess-20674"


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _worker(redis) -> SessionManager:
    manager = SessionManager.__new__(SessionManager)
    manager.redis_client = redis
    manager.sessions = {}
    manager._sessions_lock = asyncio.Lock()
    return manager


def _service(manager: SessionManager) -> AgentTerminalService:
    service = AgentTerminalService.__new__(AgentTerminalService)
    service.session_manager = manager
    service.redis_client = manager.redis_client
    service.approval_handler = AsyncMock()
    service.approval_handler._get_approval_lock = AsyncMock(return_value=asyncio.Lock())
    service._execute_approved_command = AsyncMock(return_value={"status": "approved"})
    service._handle_denied_command = AsyncMock(return_value={"status": "denied"})
    return service


async def _raise_pending(manager: SessionManager, command_id: str = "cmd-1") -> AgentTerminalSession:
    session = AgentTerminalSession(session_id=SID, agent_id="a", agent_role=AgentRole.CHAT_AGENT)
    manager.sessions[SID] = session
    assert await claim_pending_slot(manager.redis_client, SID, command_id)
    session.set_pending_approval("rm x", None, CommandRisk.HIGH.value, [], command_id, False, [])
    assert await manager._persist_session(session)
    return session


async def test_pending_approval_made_on_a_is_decided_on_b(redis):
    a, b = _worker(redis), _worker(redis)
    await _raise_pending(a)
    result = await _service(b).approve_command(SID, True)
    assert result == {"status": "approved"}


async def test_decision_on_b_with_a_stale_copy_sees_the_approval_a_made_later(redis):
    a, b = _worker(redis), _worker(redis)
    await a.get_session(SID)  # nothing yet
    b.sessions[SID] = AgentTerminalSession(session_id=SID, agent_id="a", agent_role=AgentRole.CHAT_AGENT)
    await _raise_pending(a)
    assert (await b.get_session(SID)).has_pending_approval()


async def test_a_yes_routed_to_b_after_a_decided_does_not_run_again(redis):
    a, b = _worker(redis), _worker(redis)
    await _raise_pending(a)
    stale = await b.get_session(SID)
    service_a, service_b = _service(a), _service(b)
    assert (await service_a.approve_command(SID, True))["status"] == "approved"
    await settle_pending(a.sessions[SID], a)
    b.sessions[SID] = stale
    stale.pending_approval = {"command": "rm x", "command_id": "cmd-1"}  # B still shows it undecided
    again = await service_b.approve_command(SID, True)
    assert again["status"] == "error"
    service_b._execute_approved_command.assert_not_called()


async def test_two_concurrent_yes_run_the_command_once(redis):
    a, b = _worker(redis), _worker(redis)
    await _raise_pending(a)
    await b.get_session(SID)
    services = [_service(a), _service(b)]
    results = await asyncio.gather(*(s.approve_command(SID, True) for s in services))
    assert sorted(r["status"] for r in results) == ["approved", "error"]


async def test_stale_persist_from_b_does_not_overwrite_a_newer_record(redis):
    a, b = _worker(redis), _worker(redis)
    await _raise_pending(a)
    stale = await b.get_session(SID)
    stale_version = stale.version
    await settle_pending(a.sessions[SID], a)  # A decides: record now has no approval
    stale.version = stale_version
    stale.set_pending_approval("ls", None, CommandRisk.HIGH.value, [], "cmd-2", False, [])
    assert await b._persist_session(stale) is False
    assert (await a.get_session(SID)).pending_approval is None
    assert stale.pending_approval is None  # the stale copy was refreshed, not kept


async def test_stale_persist_does_not_make_a_held_claim_look_abandoned(redis):
    a, b = _worker(redis), _worker(redis)
    await _raise_pending(a, "cmd-1")
    stale = await b.get_session(SID)
    stale.version -= 1  # B read the record before A's last save
    stale.pending_approval = None
    assert await b._persist_session(stale) is False
    await redis.expire(_claim_key(SID), CLAIM_WRITE_TTL + 100)
    assert await claim_pending_slot(redis, SID, "cmd-9") is False
    assert await redis.get(_claim_key(SID)) == "cmd-1"
    assert (await a.get_session(SID)).get_pending_command_id() == "cmd-1"


def _real_run_service(manager: SessionManager, outcome) -> AgentTerminalService:
    """A service whose approved run is real up to the command body, which ``outcome`` stands in for."""
    service = _service(manager)
    del service._execute_approved_command
    service.approval_handler.update_command_queue_status = AsyncMock()
    service._run_approved_command_body = AsyncMock(**outcome)
    return service


async def test_a_failed_run_lets_an_immediate_reapproval_run(redis):
    a, b = _worker(redis), _worker(redis)
    await _raise_pending(a)
    failing = _real_run_service(a, {"side_effect": RuntimeError("pty gone")})
    first = await failing.approve_command(SID, True)
    assert first["status"] == "error"
    retry = _real_run_service(b, {"return_value": {"status": "approved"}})
    assert await retry.approve_command(SID, True) == {"status": "approved"}


async def test_a_successful_run_still_refuses_a_second_run(redis):
    a, b = _worker(redis), _worker(redis)
    await _raise_pending(a)
    ok = _real_run_service(a, {"return_value": {"status": "approved"}})
    assert await ok.approve_command(SID, True) == {"status": "approved"}  # approval stays pending: not settled here
    again = _real_run_service(b, {"return_value": {"status": "approved"}})
    assert (await again.approve_command(SID, True))["status"] == "error"
    again._run_approved_command_body.assert_not_called()


async def test_a_release_only_frees_its_own_claim(redis):
    a = _worker(redis)
    session = await _raise_pending(a)
    assert await a.claim_decision(session)
    session.decision_token = "someone-elses-token"
    await a.release_after_failed_run(session)
    assert await a.claim_decision(session) is False
