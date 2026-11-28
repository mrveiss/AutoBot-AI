# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""An approval is decided only on state Redis confirms; a cached copy never authorises one (#20674)."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from services.agent_terminal.session_state import (
    APPROVAL_STATE_UNAVAILABLE,
    ApprovalStateUnavailableError,
    claim_decision,
    pending_decision_id,
)
from services.agent_terminal.shared_session_state_20674_test import SID, _raise_pending, _service, _worker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _break(redis) -> None:
    """Every Redis call now fails, as in an outage."""

    async def down(*_a, **_k):
        raise ConnectionError("redis down")

    for name in ("get", "set", "eval", "delete"):
        setattr(redis, name, down)


@pytest.mark.parametrize("approved", [True, False])
async def test_redis_down_refuses_the_decision_and_leaves_the_cache(redis, approved):
    worker = _worker(redis)
    session = await _raise_pending(worker)
    before = dict(session.pending_approval)
    _break(redis)
    service = _service(worker)
    result = await service.approve_command(SID, approved)
    assert result == {"status": "error", "error": APPROVAL_STATE_UNAVAILABLE}
    service._execute_approved_command.assert_not_called()
    service._handle_denied_command.assert_not_called()
    assert worker.sessions[SID] is session and session.pending_approval == before


async def test_record_missing_in_redis_refuses_a_cached_pending_approval(redis):
    worker = _worker(redis)
    session = await _raise_pending(worker)
    await redis.flushall()
    service = _service(worker)
    result = await service.approve_command(SID, True)
    assert result["error"] == APPROVAL_STATE_UNAVAILABLE
    service._execute_approved_command.assert_not_called()
    assert session.has_pending_approval()


async def test_display_read_with_redis_down_is_served_from_the_cache(redis):
    worker = _worker(redis)
    session = await _raise_pending(worker)
    _break(redis)
    assert await worker.get_session(SID) is session


async def test_claim_without_a_usable_redis_is_refused():
    with pytest.raises(ApprovalStateUnavailableError):
        await claim_decision(None, SID, "cmd-1")


async def test_two_restored_approvals_in_one_session_are_each_decided(redis):
    first = {"command": "rm a", "timestamp": 100.0}
    second = {"command": "rm b", "timestamp": 200.0}
    assert pending_decision_id(first) != pending_decision_id(second)
    assert await claim_decision(redis, SID, pending_decision_id(first))
    assert await claim_decision(redis, SID, pending_decision_id(second))
    assert await claim_decision(redis, SID, pending_decision_id(first)) is None
