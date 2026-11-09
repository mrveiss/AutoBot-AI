# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Two workers over one Redis: a closed session stays closed, and a result is interpreted once (#21202)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest

from autobot_shared.status_enums import CommandRisk
from services.agent_terminal import interpretation_turn as turn
from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.service import AgentTerminalService
from services.agent_terminal.session_state import (
    CLOSED_TOMBSTONE_TTL_SECONDS,
    DECIDED_MARKER_MIN_TTL_SECONDS,
    ApprovalStateUnavailableError,
    closed_key,
    session_key,
)
from services.agent_terminal.shared_session_state_20674_test import SID, _raise_pending, _service, _worker

pytestmark = pytest.mark.asyncio

BOUND = 5  # every wait below is bounded by this many seconds


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# --- a closed session stays closed -------------------------------------------------------------------------


async def _closed_on_a_with_stale_b(redis):
    a, b = _worker(redis), _worker(redis)
    await _raise_pending(a)
    stale = await b.get_session(SID)
    assert await a.close_session(SID)
    return a, b, stale


async def test_close_writes_the_tombstone_and_drops_the_record_together(redis):
    await _closed_on_a_with_stale_b(redis)
    assert await redis.exists(closed_key(SID))
    assert not await redis.exists(session_key(SID))
    assert 0 < await redis.ttl(closed_key(SID)) <= CLOSED_TOMBSTONE_TTL_SECONDS
    assert CLOSED_TOMBSTONE_TTL_SECONDS >= DECIDED_MARKER_MIN_TTL_SECONDS


async def test_a_stale_save_from_b_after_a_closed_is_refused_and_the_record_stays_gone(redis):
    _a, b, stale = await _closed_on_a_with_stale_b(redis)
    stale.set_pending_approval("ls", None, CommandRisk.HIGH.value, [], "cmd-2", False, [])
    assert await asyncio.wait_for(b._persist_session(stale), BOUND) is False
    assert not await redis.exists(session_key(SID))
    assert SID not in b.sessions  # the stale copy is dropped, not kept


async def test_b_cannot_decide_a_session_a_closed(redis):
    _a, b, stale = await _closed_on_a_with_stale_b(redis)
    service = _service(b)
    result = await asyncio.wait_for(service.approve_command(SID, True), BOUND)
    assert result["status"] == "error"
    service._execute_approved_command.assert_not_called()
    assert not await redis.exists(session_key(SID))


async def test_the_decision_claim_itself_refuses_a_closed_session(redis):
    _a, b, stale = await _closed_on_a_with_stale_b(redis)
    b.sessions[SID] = stale
    assert await asyncio.wait_for(b.claim_decision(stale), BOUND) is False


async def test_a_rebuild_from_chat_history_cannot_bring_a_closed_session_back(redis):
    _a, b, _stale = await _closed_on_a_with_stale_b(redis)
    b.sessions.clear()
    b.chat_history_manager = AsyncMock()
    b.chat_history_manager.get_session_messages = AsyncMock(
        return_value=[
            {
                "messageType": "command_approval_request",
                "timestamp": 1.0,
                "metadata": {"command": "rm x", "terminal_session_id": SID, "command_id": "cmd-1"},
            }
        ]
    )
    b._conversation_owner = AsyncMock(return_value="owner")
    await redis.set(f"agent_terminal:approval_conversation:{SID}", "conv-1")
    assert await asyncio.wait_for(b._rebuild_session_from_pending_approval(SID), BOUND) is None
    assert not await redis.exists(session_key(SID))


async def test_an_unreadable_tombstone_store_refuses_the_decision(redis):
    _a, b, stale = await _closed_on_a_with_stale_b(redis)
    b.sessions[SID] = stale
    redis.eval = AsyncMock(side_effect=ConnectionError("down"))
    with pytest.raises(ApprovalStateUnavailableError):
        await asyncio.wait_for(b.claim_decision(stale), BOUND)


# --- a result is interpreted exactly once ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fast_handoff(monkeypatch):
    monkeypatch.setattr(turn, "INTERPRETATION_RECHECK_SECONDS", 0.005)
    monkeypatch.setattr(turn, "INTERPRETATION_HANDOFF_SECONDS", 30.0)


def _runner(redis) -> tuple[AgentTerminalService, MagicMock]:
    """The worker that ran the command: a service over its own SessionManager."""
    service = AgentTerminalService.__new__(AgentTerminalService)
    service.session_manager = _worker(redis)
    service.chat_workflow_manager = MagicMock()
    service.chat_workflow_manager.interpret_terminal_command = AsyncMock()
    return service, service.chat_workflow_manager.interpret_terminal_command


def _session() -> AgentTerminalSession:
    from services.command_approval_manager import AgentRole

    return AgentTerminalSession(session_id=SID, agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id="conv")


async def _finish(service: AgentTerminalService) -> None:
    await asyncio.wait_for(service._interpret_approved_command(_session(), "ls", {"stdout": "x"}), BOUND)


async def _until_waiting(redis) -> None:
    """The runner has looked at the key: it is held by the live turn, so the runner is waiting for it."""
    while not await redis.exists(turn.interpretation_key(SID)):
        await asyncio.sleep(0)


async def test_polling_turn_alive_the_turn_interprets_and_the_command_worker_skips(redis):
    runner, interpreted = _runner(redis)
    poller = AgentTerminalService.__new__(AgentTerminalService)
    poller.session_manager = _worker(redis)  # a different worker
    token = await poller.begin_interpreting_turn(SID)
    finishing = asyncio.create_task(_finish(runner))  # the command completes while the turn is alive
    await asyncio.wait_for(_until_waiting(redis), BOUND)
    assert await poller.take_turn_interpretation(SID, token) is True  # the turn sees the result and wins
    await poller.end_interpreting_turn(SID, token)
    await asyncio.wait_for(finishing, BOUND)
    interpreted.assert_not_awaited()  # exactly once: the turn's


async def test_polling_turn_gone_the_command_worker_interprets_once(redis):
    runner, interpreted = _runner(redis)
    poller = AgentTerminalService.__new__(AgentTerminalService)
    poller.session_manager = _worker(redis)
    token = await poller.begin_interpreting_turn(SID)
    finishing = asyncio.create_task(_finish(runner))
    await asyncio.wait_for(_until_waiting(redis), BOUND)
    await poller.end_interpreting_turn(SID, token)  # the turn times out without the result
    await asyncio.wait_for(finishing, BOUND)
    interpreted.assert_awaited_once()
    assert await poller.take_turn_interpretation(SID, token) is False  # a late swap by the gone turn loses


async def test_polling_turn_gone_before_the_command_ends_the_command_worker_interprets_once(redis):
    runner, interpreted = _runner(redis)
    poller = AgentTerminalService.__new__(AgentTerminalService)
    poller.session_manager = _worker(redis)
    token = await poller.begin_interpreting_turn(SID)
    await poller.end_interpreting_turn(SID, token)
    await _finish(runner)
    interpreted.assert_awaited_once()


async def test_a_turn_slower_than_the_handoff_deadline_loses_the_swap_and_skips(redis, monkeypatch):
    monkeypatch.setattr(turn, "INTERPRETATION_HANDOFF_SECONDS", 0.05)
    runner, interpreted = _runner(redis)
    poller = AgentTerminalService.__new__(AgentTerminalService)
    poller.session_manager = _worker(redis)
    token = await poller.begin_interpreting_turn(SID)
    await _finish(runner)  # waits out the deadline, then swaps the turn's token for done
    interpreted.assert_awaited_once()
    assert await poller.take_turn_interpretation(SID, token) is False  # the slow turn's swap fails: it skips


async def test_a_turn_and_the_command_worker_racing_interpret_exactly_once(redis):
    for _ in range(20):
        await redis.delete(turn.interpretation_key(SID))
        runner, interpreted = _runner(redis)
        poller = AgentTerminalService.__new__(AgentTerminalService)
        poller.session_manager = _worker(redis)
        token = await poller.begin_interpreting_turn(SID)
        taken, _none = await asyncio.wait_for(
            asyncio.gather(poller.take_turn_interpretation(SID, token), _finish(runner)), BOUND
        )
        assert int(taken) + interpreted.await_count == 1
