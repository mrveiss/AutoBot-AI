# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Two workers over one Redis: a closed session stays closed, and a result is interpreted once (#21202)."""

from __future__ import annotations

import asyncio
import json
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
CMD = "cmd-1"


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


def _session(command_id: str = CMD) -> AgentTerminalSession:
    from services.command_approval_manager import AgentRole

    session = AgentTerminalSession(
        session_id=SID, agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id="conv"
    )
    session.pending_approval = {"command": "ls", "command_id": command_id}
    return session


async def _finish(service: AgentTerminalService, command_id: str = CMD) -> None:
    await asyncio.wait_for(service._interpret_approved_command(_session(command_id), "ls", {"stdout": "x"}), BOUND)


async def _until_waiting(redis) -> None:
    """The runner has looked at the key: it is held by the live turn, so the runner is waiting for it."""
    while not await redis.exists(turn.interpretation_key(SID, CMD)):
        await asyncio.sleep(0)


async def test_polling_turn_alive_the_turn_interprets_and_the_command_worker_skips(redis):
    runner, interpreted = _runner(redis)
    poller = AgentTerminalService.__new__(AgentTerminalService)
    poller.session_manager = _worker(redis)  # a different worker
    token = await poller.begin_interpreting_turn(SID, CMD)
    finishing = asyncio.create_task(_finish(runner))  # the command completes while the turn is alive
    await asyncio.wait_for(_until_waiting(redis), BOUND)
    assert await poller.take_turn_interpretation(SID, CMD, token) is True  # the turn sees the result and wins
    await poller.end_interpreting_turn(SID, CMD, token)
    await asyncio.wait_for(finishing, BOUND)
    interpreted.assert_not_awaited()  # exactly once: the turn's


async def test_polling_turn_gone_the_command_worker_interprets_once(redis):
    runner, interpreted = _runner(redis)
    poller = AgentTerminalService.__new__(AgentTerminalService)
    poller.session_manager = _worker(redis)
    token = await poller.begin_interpreting_turn(SID, CMD)
    finishing = asyncio.create_task(_finish(runner))
    await asyncio.wait_for(_until_waiting(redis), BOUND)
    await poller.end_interpreting_turn(SID, CMD, token)  # the turn times out without the result
    await asyncio.wait_for(finishing, BOUND)
    interpreted.assert_awaited_once()
    assert await poller.take_turn_interpretation(SID, CMD, token) is False  # a late swap by the gone turn loses


async def test_polling_turn_gone_before_the_command_ends_the_command_worker_interprets_once(redis):
    runner, interpreted = _runner(redis)
    poller = AgentTerminalService.__new__(AgentTerminalService)
    poller.session_manager = _worker(redis)
    token = await poller.begin_interpreting_turn(SID, CMD)
    await poller.end_interpreting_turn(SID, CMD, token)
    await _finish(runner)
    interpreted.assert_awaited_once()


async def test_a_turn_slower_than_the_handoff_deadline_loses_the_swap_and_skips(redis, monkeypatch):
    monkeypatch.setattr(turn, "INTERPRETATION_HANDOFF_SECONDS", 0.05)
    runner, interpreted = _runner(redis)
    poller = AgentTerminalService.__new__(AgentTerminalService)
    poller.session_manager = _worker(redis)
    token = await poller.begin_interpreting_turn(SID, CMD)
    await _finish(runner)  # waits out the deadline, then swaps the turn's token for done
    interpreted.assert_awaited_once()
    assert await poller.take_turn_interpretation(SID, CMD, token) is False  # the slow turn's swap fails: it skips


async def test_a_turn_and_the_command_worker_racing_interpret_exactly_once(redis):
    for _ in range(20):
        await redis.delete(turn.interpretation_key(SID, CMD))
        runner, interpreted = _runner(redis)
        poller = AgentTerminalService.__new__(AgentTerminalService)
        poller.session_manager = _worker(redis)
        token = await poller.begin_interpreting_turn(SID, CMD)
        taken, _none = await asyncio.wait_for(
            asyncio.gather(poller.take_turn_interpretation(SID, CMD, token), _finish(runner)), BOUND
        )
        assert int(taken) + interpreted.await_count == 1


async def test_the_command_finishing_before_the_turn_registers_is_interpreted_once(redis):
    runner, interpreted = _runner(redis)
    await _finish(runner)  # an instant approval: the worker interprets and leaves done behind
    poller = AgentTerminalService.__new__(AgentTerminalService)
    poller.session_manager = _worker(redis)
    token = await poller.begin_interpreting_turn(SID, CMD)  # the turn registers late
    assert await redis.get(turn.interpretation_key(SID, CMD)) == "done"  # not overwritten
    assert await poller.take_turn_interpretation(SID, CMD, token) is False
    interpreted.assert_awaited_once()


async def test_a_second_approval_after_a_done_is_still_interpreted(redis):
    runner, interpreted = _runner(redis)
    await _finish(runner, "cmd-1")
    await _finish(runner, "cmd-2")  # a late approval in the same session: nobody is polling
    assert interpreted.await_count == 2


# --- the controls: the same orderings on the old logic, simulated here, are wrong ---------------------------

OLD_PERSIST_LUA = """
local stored = redis.call('GET', KEYS[1])
if stored then
  local current = cjson.decode(stored)['version'] or 0
  if current ~= tonumber(ARGV[1]) then
    return 0
  end
end
redis.call('SETEX', KEYS[1], tonumber(ARGV[2]), ARGV[3])
return 1
"""


async def test_control_the_old_persist_script_recreates_a_closed_session_the_new_path_does_not(redis):
    a, b, stale = await _closed_on_a_with_stale_b(redis)
    stale.set_pending_approval("ls", None, CommandRisk.HIGH.value, [], "cmd-2", False, [])
    payload = json.dumps(stale.to_persist_dict() | {"version": stale.version + 1})
    old = await redis.eval(OLD_PERSIST_LUA, 1, session_key(SID), stale.version, 3600, payload)
    assert old == 1 and await redis.exists(session_key(SID))  # old behaviour: the closed record is back
    await redis.delete(session_key(SID))
    assert await b._persist_session(stale) is False  # new behaviour: refused
    assert not await redis.exists(session_key(SID))


async def test_control_a_per_worker_flag_double_interprets_where_the_shared_key_does_not(redis):
    """Old logic: each worker's own flag. The runner's copy was read before the turn set it, so it interprets,
    and the turn interprets too."""
    runner_flag = {"live": False}  # the runner worker's stale copy
    turn_flag = {"live": True}  # the turn's worker, set after the runner read
    old_count = (0 if runner_flag["live"] else 1) + (1 if turn_flag["live"] else 0)
    assert old_count == 2
    runner, interpreted = _runner(redis)
    poller = AgentTerminalService.__new__(AgentTerminalService)
    poller.session_manager = _worker(redis)
    token = await poller.begin_interpreting_turn(SID, CMD)
    finishing = asyncio.create_task(_finish(runner))
    won = await poller.take_turn_interpretation(SID, CMD, token)
    await asyncio.wait_for(finishing, BOUND)
    assert int(won) + interpreted.await_count == 1


# --- close from any worker, and a failing store ------------------------------------------------------------


async def test_a_close_on_a_worker_that_never_cached_the_session_still_closes_it(redis):
    a, b = _worker(redis), _worker(redis)
    await _raise_pending(a)
    assert SID not in b.sessions
    assert await asyncio.wait_for(b.close_session(SID), BOUND) is True
    assert await redis.exists(closed_key(SID)) and not await redis.exists(session_key(SID))
    assert (await a._persist_session(a.sessions[SID])) is False  # A's stale cache cannot bring it back


async def test_a_failed_store_close_is_not_a_close(redis):
    a = _worker(redis)
    await _raise_pending(a)
    redis.eval = AsyncMock(side_effect=ConnectionError("down"))
    assert await asyncio.wait_for(a.close_session(SID), BOUND) is False
    assert SID in a.sessions  # nothing marked closed locally
    assert await redis.exists(session_key(SID))


async def test_a_worker_drops_a_session_another_worker_closed_when_it_refreshes(redis):
    a, b = _worker(redis), _worker(redis)
    await _raise_pending(a)
    await b.get_session(SID)
    assert await a.close_session(SID)
    assert await asyncio.wait_for(b.get_session(SID), BOUND) is None
    assert SID not in b.sessions


async def test_a_close_between_the_save_and_the_pointer_writes_leaves_no_pointer_or_slot(redis):
    from services.agent_terminal.pending_claim import _claim_key
    from services.agent_terminal.session_state import close_record, conversation_pointer_key

    a = _worker(redis)
    session = await _raise_pending(a)
    session.conversation_id = "conv-1"
    real_hold = a._write_pending_pointers

    async def _close_first(sess, ttl):
        await close_record(redis, SID)  # the close lands after the save, before the pointer writes
        return await real_hold(sess, ttl)

    a._write_pending_pointers = _close_first
    assert await asyncio.wait_for(a._persist_session(session), BOUND) is False
    assert not await redis.exists(conversation_pointer_key(SID))
    assert not await redis.exists(_claim_key(SID))
