# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A rebuild from chat history never makes a decided approval decidable again (#20674, #21174)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.session_manager import APPROVAL_PENDING_SESSION_TTL, SessionManager
from services.agent_terminal.session_state import (
    DECIDED_MARKER_TTL_SECONDS,
    DECISION_TTL_SECONDS,
    claim_decision,
    decided_key,
    session_key,
)
from services.agent_terminal.shared_session_state_20674_test import _real_run_service, _service
from services.command_approval_manager import AgentRole

pytestmark = pytest.mark.asyncio

CONV = "conv-21174"


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _request(session_id: str, command_id: str | None, command: str, stamp: float) -> dict:
    meta = {"command": command, "terminal_session_id": session_id, "risk_level": "HIGH"}
    if command_id:
        meta["command_id"] = command_id
    return {"messageType": "command_approval_request", "timestamp": stamp, "text": "needs approval", "metadata": meta}


def _worker(redis, messages: list[dict]) -> SessionManager:
    manager = SessionManager.__new__(SessionManager)
    manager.redis_client = redis
    manager.sessions = {}
    manager._sessions_lock = asyncio.Lock()
    manager.chat_history_manager = AsyncMock()
    manager.chat_history_manager.get_session_messages = AsyncMock(return_value=messages)
    manager._conversation_owner = AsyncMock(return_value="owner")
    return manager


async def _raise(manager: SessionManager, sid: str, command_id: str, command: str) -> None:
    session = AgentTerminalSession(
        session_id=sid, agent_id="a", agent_role=AgentRole.CHAT_AGENT, conversation_id=CONV, owner="owner"
    )
    manager.sessions[sid] = session
    session.set_pending_approval(command, None, "HIGH", [], command_id, False, [])
    assert await manager._persist_session(session)


async def _expire(redis, manager: SessionManager, sid: str) -> None:
    """The session record is gone (1 h idle TTL) and no worker has it cached; the pointer survives."""
    await redis.delete(session_key(sid))
    manager.sessions.clear()


async def test_a_request_of_another_session_is_never_restored_for_this_one(redis):
    messages = [_request("sess-Y", "cmd-y", "rm y", 200.0)]
    worker = _worker(redis, messages)
    await redis.set("agent_terminal:approval_conversation:sess-X", CONV)
    service = _service(worker)
    result = await service.approve_command("sess-X", True)
    assert result["status"] == "error"
    service._execute_approved_command.assert_not_called()
    assert await redis.get(session_key("sess-X")) is None


async def test_a_request_without_a_session_id_is_not_restored(redis):
    request = _request("sess-X", "cmd-x", "rm x", 100.0)
    del request["metadata"]["terminal_session_id"]
    worker = _worker(redis, [request])
    await redis.set("agent_terminal:approval_conversation:sess-X", CONV)
    assert await worker._rebuild_session_from_pending_approval("sess-X") is None


async def test_a_decided_approval_stays_decided_when_the_record_expired_and_the_response_message_is_lost(redis):
    messages = [_request("sess-X", "cmd-x", "rm x", 100.0)]  # no command_approval_response was written
    a = _worker(redis, messages)
    await _raise(a, "sess-X", "cmd-x", "rm x")
    assert (await _service(a).approve_command("sess-X", True))["status"] == "approved"
    assert await redis.exists(decided_key("cmd-x"))
    await _expire(redis, a, "sess-X")
    await redis.delete("agent_terminal:decision:sess-X:cmd-x")  # even with the claim gone
    b = _worker(redis, messages)
    service_b = _service(b)
    assert (await service_b.approve_command("sess-X", True))["status"] == "error"
    service_b._execute_approved_command.assert_not_called()
    assert await b._rebuild_session_from_pending_approval("sess-X") is None


async def test_a_rebuilt_approval_keeps_its_original_command_id(redis):
    worker = _worker(redis, [_request("sess-X", "cmd-x", "rm x", 100.0)])
    await redis.set("agent_terminal:approval_conversation:sess-X", CONV)
    session = await worker._rebuild_session_from_pending_approval("sess-X")
    assert session.get_pending_command_id() == "cmd-x"


async def test_a_failed_run_can_be_reapproved_after_a_rebuild(redis):
    messages = [_request("sess-X", "cmd-x", "rm x", 100.0)]
    a = _worker(redis, messages)
    await _raise(a, "sess-X", "cmd-x", "rm x")
    failing = _real_run_service(a, {"side_effect": RuntimeError("pty gone")})
    assert (await failing.approve_command("sess-X", True))["status"] == "error"
    assert not await redis.exists(decided_key("cmd-x"))  # the release cleared the marker with the claim
    await _expire(redis, a, "sess-X")
    retry = _real_run_service(_worker(redis, messages), {"return_value": {"status": "approved"}})
    assert await retry.approve_command("sess-X", True) == {"status": "approved"}
    assert await redis.exists(decided_key("cmd-x"))  # a successful run keeps it


async def test_two_sessions_in_one_conversation_each_keep_their_own_approval(redis):
    messages = [_request("sess-X", "cmd-x", "rm x", 100.0), _request("sess-Y", "cmd-y", "rm y", 200.0)]
    worker = _worker(redis, messages)
    for sid in ("sess-X", "sess-Y"):
        await redis.set(f"agent_terminal:approval_conversation:{sid}", CONV)
    x = await worker._rebuild_session_from_pending_approval("sess-X")
    y = await worker._rebuild_session_from_pending_approval("sess-Y")
    assert (x.pending_approval["command"], y.pending_approval["command"]) == ("rm x", "rm y")
    assert (x.get_pending_command_id(), y.get_pending_command_id()) == ("cmd-x", "cmd-y")


async def test_another_sessions_response_does_not_hide_this_sessions_approval(redis):
    response = {
        "messageType": "command_approval_response",
        "timestamp": 300.0,
        "text": "Command approved and executed: `rm y`",
        "metadata": {"terminal_session_id": "sess-Y"},
    }
    worker = _worker(redis, [_request("sess-X", "cmd-x", "rm x", 100.0), response])
    await redis.set("agent_terminal:approval_conversation:sess-X", CONV)
    assert await worker._rebuild_session_from_pending_approval("sess-X") is not None


async def test_an_unreadable_marker_store_refuses_the_rebuild(redis):
    worker = _worker(redis, [_request("sess-X", "cmd-x", "rm x", 100.0)])
    await redis.set("agent_terminal:approval_conversation:sess-X", CONV)
    redis.exists = AsyncMock(side_effect=ConnectionError("down"))
    assert await worker._rebuild_session_from_pending_approval("sess-X") is None


async def test_a_request_without_a_command_id_is_still_marked_by_its_digest(redis):
    messages = [_request("sess-X", None, "rm x", 100.0)]
    worker = _worker(redis, messages)
    await redis.set("agent_terminal:approval_conversation:sess-X", CONV)
    session = await worker._rebuild_session_from_pending_approval("sess-X")
    assert await worker.claim_decision(session)
    assert await _worker(redis, messages)._rebuild_session_from_pending_approval("sess-X") is None


async def test_the_claim_and_the_marker_are_written_together_and_outlive_the_record(redis):
    assert await claim_decision(redis, "sess-X", "cmd-x")
    assert await claim_decision(redis, "sess-X", "cmd-x") is None
    stored = await redis.ttl(decided_key("cmd-x"))
    assert APPROVAL_PENDING_SESSION_TTL < stored <= DECIDED_MARKER_TTL_SECONDS  # the marker TTL, not the claim's
    assert DECISION_TTL_SECONDS > 3600  # longer than the longest command the decision can start


async def test_a_later_unrelated_message_does_not_hide_the_approval(redis):
    chatter = {"messageType": "default", "timestamp": 300.0, "text": "Has this command executed yet?", "metadata": {}}
    worker = _worker(redis, [_request("sess-X", "cmd-x", "rm x", 100.0), chatter])
    await redis.set("agent_terminal:approval_conversation:sess-X", CONV)
    assert await worker._rebuild_session_from_pending_approval("sess-X") is not None


async def test_the_legacy_message_type_key_still_matches(redis):
    request = _request("sess-X", "cmd-x", "rm x", 100.0)
    request["message_type"] = request.pop("messageType")
    worker = _worker(redis, [request])
    await redis.set("agent_terminal:approval_conversation:sess-X", CONV)
    assert await worker._rebuild_session_from_pending_approval("sess-X") is not None


async def test_a_rebuilt_session_is_recorded_before_it_is_returned(redis):
    worker = _worker(redis, [_request("sess-X", "cmd-x", "rm x", 100.0)])
    await redis.set("agent_terminal:approval_conversation:sess-X", CONV)
    assert await worker._rebuild_session_from_pending_approval("sess-X") is not None
    assert await redis.exists(session_key("sess-X"))


async def test_a_lapsed_claim_does_not_regrant_a_decided_approval(redis):
    assert await claim_decision(redis, "sess-X", "cmd-x")
    await redis.delete("agent_terminal:decision:sess-X:cmd-x")  # the claim lapses, the marker stays
    assert await claim_decision(redis, "sess-X", "cmd-x") is None


async def test_a_release_redis_refuses_is_retried_with_the_same_token(redis, monkeypatch):
    from services.agent_terminal import decision_session

    monkeypatch.setattr(decision_session, "_RELEASE_RETRY_DELAYS_SECONDS", (0, 0))
    token = await claim_decision(redis, "sess-X", "cmd-x")
    real = redis.eval
    failures = iter([ConnectionError("blip")])

    async def _eval(*args, **kwargs):
        failure = next(failures, None)
        if failure is not None:
            raise failure
        return await real(*args, **kwargs)

    redis.eval = _eval
    await decision_session.release_with_retry(redis, "sess-X", "cmd-x", token)  # must not raise
    for _ in range(50):
        if not await redis.exists(decided_key("cmd-x")):
            break
        await asyncio.sleep(0.01)
    assert not await redis.exists(decided_key("cmd-x"))
    assert await claim_decision(redis, "sess-X", "cmd-x")


async def test_a_refused_reservation_save_is_retried_with_the_approval_put_back(redis):
    from types import SimpleNamespace

    from services.agent_terminal.ai_line_gate import persist_reservation

    worker = _worker(redis, [])
    session = AgentTerminalSession(session_id="sess-R", agent_id="a", agent_role=AgentRole.CHAT_AGENT, owner="owner")
    session.set_pending_approval("rm r", None, "HIGH", [], "cmd-r", False, [])
    calls = []

    async def _persist(s):
        calls.append(s.get_pending_command_id())
        if len(calls) == 1:
            s.pending_approval = None  # the stale-save refresh replaced the approval with the older record
            return False
        return True

    worker._persist_session = _persist
    risk = SimpleNamespace(value="HIGH")
    assert await persist_reservation(session, worker, SimpleNamespace(command_id="cmd-r"), None, risk) is None
    assert calls == ["cmd-r", "cmd-r"]  # put back before the second save
    assert session.get_pending_command_id() == "cmd-r"
