# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Two workers racing on one session cannot replace each other's pending approval (#20059).

Each ``_worker`` has its own session copy and shares one real-semantics Redis, as uvicorn workers do.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from autobot_shared.eventually import DEFAULT_DEADLINE_S, eventually
from autobot_shared.status_enums import CommandRisk
from services.agent_terminal.ai_line_gate import (
    CLAIM_UNAVAILABLE_REFUSAL,
    PENDING_APPROVAL_REFUSAL,
    claim_pending,
    settle_pending,
    write_reservation,
)
from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.pending_claim import CLAIM_WRITE_TTL, _claim_key, claim_pending_slot, hold_pending_slot
from services.agent_terminal.service import AgentTerminalService
from services.agent_terminal.session_manager import APPROVAL_PENDING_SESSION_TTL, SessionManager
from services.agent_terminal.session_state import PERSIST_IF_VERSION_LUA
from services.command_approval_manager import AgentRole

pytestmark = pytest.mark.asyncio

SID = "sess-20059"


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _session() -> AgentTerminalSession:
    return AgentTerminalSession(session_id=SID, agent_id="agent-1", agent_role=AgentRole.CHAT_AGENT)


def _worker(redis) -> SimpleNamespace:
    manager = SessionManager.__new__(SessionManager)
    manager.redis_client = redis
    manager.sessions = {}
    manager._sessions_lock = asyncio.Lock()
    return SimpleNamespace(session=_session(), manager=manager)


def _set_pending(session, command_id: str) -> None:
    session.set_pending_approval(
        command="rm x",
        description=None,
        risk_value=CommandRisk.HIGH.value,
        reasons=[],
        command_id=command_id,
        is_interactive=False,
        interactive_reasons=[],
    )


async def _claim(worker, redis, command_id: str):
    return await claim_pending(worker.session, redis, command_id, "rm x", CommandRisk.HIGH)


async def test_second_worker_is_refused_while_the_first_holds_the_slot(redis):
    first, second = _worker(redis), _worker(redis)
    assert await _claim(first, redis, "cmd-1") is None
    refused = await _claim(second, redis, "cmd-2")
    assert refused["error"] == PENDING_APPROVAL_REFUSAL
    assert await redis.get(_claim_key(SID)) == "cmd-1"


async def test_concurrent_claims_have_exactly_one_winner(redis):
    workers = [_worker(redis) for _ in range(8)]
    results = await asyncio.gather(*(_claim(w, redis, f"cmd-{i}") for i, w in enumerate(workers)))
    assert sum(r is None for r in results) == 1


async def test_a_redis_error_refuses_the_command(redis):
    broken = AsyncMock()
    broken.set.side_effect = ConnectionError("down")
    refused = await _claim(_worker(redis), broken, "cmd-1")
    assert refused["error"] == CLAIM_UNAVAILABLE_REFUSAL


async def test_a_decision_releases_the_slot_and_persists_the_clear(redis):
    first, second = _worker(redis), _worker(redis)
    await _claim(first, redis, "cmd-1")
    _set_pending(first.session, "cmd-1")
    await first.manager._persist_session(first.session)
    await settle_pending(first.session, first.manager)

    assert first.session.pending_approval is None
    stored = json.loads(await redis.get(f"agent_terminal:session:{SID}"))
    assert stored["pending_approval"] is None
    assert await _claim(second, redis, "cmd-2") is None


async def test_a_failed_queue_write_releases_the_slot(redis):
    worker = _worker(redis)
    await _claim(worker, redis, "cmd-1")
    _set_pending(worker.session, "cmd-1")
    queue = AsyncMock()
    queue.add_command.side_effect = OSError("disk")
    with pytest.raises(OSError):
        await write_reservation(worker.session, SimpleNamespace(command_id="cmd-1"), queue, redis)

    async def _claim_is_free():
        return await redis.get(_claim_key(SID)) is None

    await _eventually_async(_claim_is_free)
    assert await redis.get(_claim_key(SID)) is None
    assert worker.session.pending_approval is None


async def test_a_worker_dying_before_it_persists_frees_the_slot_by_ttl(redis):
    await _claim(_worker(redis), redis, "cmd-1")
    assert 0 < await redis.ttl(_claim_key(SID)) <= CLAIM_WRITE_TTL


async def test_persisting_the_approval_lifts_the_claim_to_the_session_ttl(redis):
    worker = _worker(redis)
    await _claim(worker, redis, "cmd-1")
    _set_pending(worker.session, "cmd-1")
    await worker.manager._persist_session(worker.session)
    assert await redis.ttl(_claim_key(SID)) > CLAIM_WRITE_TTL
    assert await redis.ttl(_claim_key(SID)) <= APPROVAL_PENDING_SESSION_TTL
    assert await _claim(_worker(redis), redis, "cmd-2") is not None


async def test_a_lost_release_cannot_strand_the_session(redis):
    """The approval was decided, but the release never reached Redis: the next command takes over."""
    worker = _worker(redis)
    await _claim(worker, redis, "cmd-1")
    _set_pending(worker.session, "cmd-1")
    await worker.manager._persist_session(worker.session)
    worker.session.clear_pending_and_resume()
    await worker.manager._persist_session(worker.session)

    assert await claim_pending_slot(redis, SID, "cmd-2") is True
    assert await redis.get(_claim_key(SID)) == "cmd-2"


async def test_a_claim_inside_the_write_window_is_not_taken_over(redis):
    """Control: the persisted session shows no approval yet, which is normal before the first persist."""
    assert await claim_pending_slot(redis, SID, "cmd-1") is True
    assert await claim_pending_slot(redis, SID, "cmd-2") is False


async def test_only_the_holder_can_extend_a_claim(redis):
    assert await claim_pending_slot(redis, SID, "cmd-1") is True
    await hold_pending_slot(redis, SID, "cmd-2", APPROVAL_PENDING_SESSION_TTL)
    assert await redis.ttl(_claim_key(SID)) <= CLAIM_WRITE_TTL


async def test_closing_the_session_frees_the_slot(redis):
    worker = _worker(redis)
    worker.manager.sessions[SID] = worker.session
    await _claim(worker, redis, "cmd-1")
    assert await worker.manager.close_session(SID) is True
    assert await redis.get(_claim_key(SID)) is None


def _service(worker, redis):
    svc = AgentTerminalService.__new__(AgentTerminalService)
    svc.redis_client = redis
    svc.session_manager = worker.manager
    svc.command_queue = AsyncMock()
    svc.terminal_logger = AsyncMock()
    svc.approval_handler = AsyncMock()
    return svc


async def _queue(svc, session):
    return await svc._queue_command_for_approval(
        session=session,
        command="rm x",
        description=None,
        risk=CommandRisk.HIGH,
        reasons=[],
        is_interactive=False,
        interactive_reasons=[],
    )


async def test_the_service_refuses_the_second_workers_command(redis):
    first, second = _worker(redis), _worker(redis)
    assert (await _queue(_service(first, redis), first.session))["status"] == "pending_approval"
    assert (await _queue(_service(second, redis), second.session))["error"] == PENDING_APPROVAL_REFUSAL
    assert second.session.pending_approval is None


async def test_a_denial_through_the_service_frees_the_slot(redis):
    first, second = _worker(redis), _worker(redis)
    svc = _service(first, redis)
    await _queue(svc, first.session)
    await svc._handle_denied_command(first.session, "rm x", first.session.get_pending_command_id(), "high", "u", None)
    assert (await _queue(_service(second, redis), second.session))["status"] == "pending_approval"


async def test_a_restored_approval_without_a_command_id_still_writes_its_conversation_pointer(redis):
    """An approval rebuilt from chat history has no command id; the #13478 pointer must still be written."""
    worker = _worker(redis)
    worker.session.conversation_id = "conv-1"
    worker.session.pending_approval = {"command": "rm x", "risk": CommandRisk.HIGH.value}
    await worker.manager._persist_session(worker.session)
    assert await redis.get(f"agent_terminal:approval_conversation:{SID}") == "conv-1"
    assert await redis.get(_claim_key(SID)) is None


async def test_a_claim_lost_while_its_approval_waits_is_re_asserted(redis):
    """A failed renewal lets the claim lapse: the waiting approval still refuses the next command, on every try."""
    first, second = _worker(redis), _worker(redis)
    await _claim(first, redis, "cmd-1")
    _set_pending(first.session, "cmd-1")
    await first.manager._persist_session(first.session)
    await redis.delete(_claim_key(SID))

    assert (await _claim(second, redis, "cmd-2"))["error"] == PENDING_APPROVAL_REFUSAL
    assert await redis.get(_claim_key(SID)) == "cmd-1"
    assert await redis.ttl(_claim_key(SID)) > CLAIM_WRITE_TTL
    assert (await _claim(second, redis, "cmd-3"))["error"] == PENDING_APPROVAL_REFUSAL


async def test_a_lost_claim_on_a_restored_approval_without_an_id_still_refuses_and_leaves_no_claim(redis):
    worker = _worker(redis)
    worker.session.pending_approval = {"command": "rm x", "risk": CommandRisk.HIGH.value}
    await worker.manager._persist_session(worker.session)
    assert (await _claim(_worker(redis), redis, "cmd-2"))["error"] == PENDING_APPROVAL_REFUSAL
    assert await redis.get(_claim_key(SID)) is None


async def test_a_failed_renewal_does_not_skip_the_conversation_pointer(redis, monkeypatch):
    worker = _worker(redis)
    worker.session.conversation_id = "conv-1"
    _set_pending(worker.session, "cmd-1")
    monkeypatch.setattr(
        "services.agent_terminal.session_manager.hold_pending_slot", AsyncMock(side_effect=ConnectionError("blip"))
    )
    await worker.manager._persist_session(worker.session)
    assert await redis.get(f"agent_terminal:approval_conversation:{SID}") == "conv-1"


async def test_a_failed_save_at_the_decision_is_retried_until_other_workers_can_queue(redis, monkeypatch):
    monkeypatch.setattr("services.agent_terminal.ai_line_gate._CLEAR_RETRY_DELAYS_SECONDS", (0, 0, 0))
    first, second = _worker(redis), _worker(redis)
    await _claim(first, redis, "cmd-1")
    _set_pending(first.session, "cmd-1")
    await first.manager._persist_session(first.session)
    real_eval = redis.eval
    redis.eval = _fail_twice_then(real_eval)

    await settle_pending(first.session, first.manager)
    assert (await _claim(second, redis, "cmd-2"))["error"] == PENDING_APPROVAL_REFUSAL  # still stale here

    await _until_session_is_cleared(redis)
    await redis.delete(_claim_key(SID))
    assert await _claim(second, redis, "cmd-3") is None


async def test_the_retry_stops_once_a_newer_approval_owns_the_record(redis, monkeypatch):
    monkeypatch.setattr("services.agent_terminal.ai_line_gate._CLEAR_RETRY_DELAYS_SECONDS", (0,))
    worker = _worker(redis)
    worker.manager._persist_session = AsyncMock(return_value=False)
    await settle_pending(worker.session, worker.manager)
    _set_pending(worker.session, "cmd-new")
    calls = worker.manager._persist_session.await_count
    await eventually(lambda: not _retry_tasks_running())
    assert worker.manager._persist_session.await_count == calls


def _fail_twice_then(real):
    failures = iter([ConnectionError("blip"), ConnectionError("blip")])

    async def _eval(*args, **kwargs):
        failure = next(failures, None) if args[0] == PERSIST_IF_VERSION_LUA else None
        if failure is not None:
            raise failure
        return await real(*args, **kwargs)

    return _eval


def _retry_tasks_running() -> list:
    """The background tasks that retry clearing this session's decided approval."""
    return [t for t in asyncio.all_tasks() if t.get_name() == f"retry-clear-{SID}" and not t.done()]


async def _eventually_async(condition) -> None:
    """``eventually`` for a condition that must be awaited: poll it until it holds or the deadline passes."""

    async def _poll() -> None:
        while not await condition():
            await asyncio.sleep(0)

    await asyncio.wait_for(_poll(), timeout=DEFAULT_DEADLINE_S)


async def _until_session_is_cleared(redis) -> None:
    async def _cleared():
        return json.loads(await redis.get(f"agent_terminal:session:{SID}"))["pending_approval"] is None

    await _eventually_async(_cleared)


async def test_the_retry_clears_the_decided_approval_a_refresh_restored(redis, monkeypatch):
    monkeypatch.setattr("services.agent_terminal.ai_line_gate._CLEAR_RETRY_DELAYS_SECONDS", (0, 0))
    worker = _worker(redis)
    _set_pending(worker.session, "cmd-1")
    refusals = iter([False, False])

    async def _persist(session):
        if next(refusals, True) is False:
            _set_pending(session, "cmd-1")  # the refused save refreshed the copy over the decided approval
            return False
        return True

    worker.manager._persist_session = _persist
    await settle_pending(worker.session, worker.manager)
    await eventually(lambda: not _retry_tasks_running())
    assert not worker.session.has_pending_approval()
