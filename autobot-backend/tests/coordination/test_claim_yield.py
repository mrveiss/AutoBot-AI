# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Asking a holder to yield, and inviting the next waiter (#15948).

The assertions that matter here are about *where* the message goes and *what
silence means*, not about the happy path. A yield protocol that quietly used its
own bus, or that treated no answer as consent, would pass a happy-path test.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from services.claim_yield import (
    HOLD,
    YIELD,
    YieldRequest,
    answer_yield,
    await_decision,
    decode_yield_request,
    invite_next_waiter,
    request_yield,
)

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None


class _RecordingTaskManager:
    """Captures publishes instead of reaching Redis pub/sub."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish_event(self, task_id: str, payload: dict) -> None:
        self.published.append((task_id, payload))


@pytest_asyncio.fixture
async def env(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis not installed")
    import services.claim_yield as cy
    from autobot_shared.coordination import claim_waitlist as wl

    client = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    manager = _RecordingTaskManager()
    monkeypatch.setattr(cy, "get_async_redis_client", _client)
    monkeypatch.setattr(cy, "get_task_manager", lambda: manager)
    monkeypatch.setattr(wl, "get_async_redis_client", _client)
    yield manager, client
    await client.flushall()


@pytest.mark.asyncio
async def test_the_request_goes_to_the_holders_own_task_channel(env):
    """No new bus: the address is the holder's task id, which a2a already routes."""
    manager, _ = env
    request = await request_yield(
        "path:a/b",
        holder_task_id="holder-task",
        requester_agent_id="agent-2",
        requester_task_id="task-2",
        reason="needs the same file",
    )
    assert len(manager.published) == 1
    task_id, payload = manager.published[0]
    assert task_id == "holder-task"
    assert payload["event"] == "work_claim_yield_request"
    assert payload["token"] == request.token
    assert payload["requester_agent_id"] == "agent-2"
    assert payload["reason"] == "needs the same file"


@pytest.mark.asyncio
async def test_an_explicit_yes_is_returned(env):
    request = await request_yield(
        "path:a/b", holder_task_id="h", requester_agent_id="a", requester_task_id="t", reason="r"
    )
    await answer_yield(request.token, YIELD)
    assert await await_decision(request, timeout_s=1) == YIELD


@pytest.mark.asyncio
async def test_an_explicit_no_is_returned(env):
    request = await request_yield(
        "path:a/b", holder_task_id="h", requester_agent_id="a", requester_task_id="t", reason="r"
    )
    await answer_yield(request.token, HOLD)
    assert await await_decision(request, timeout_s=1) == HOLD


@pytest.mark.asyncio
async def test_silence_resolves_to_hold_not_consent(env):
    """A busy or crashed holder must not lose its scope by failing to object."""
    request = await request_yield(
        "path:a/b", holder_task_id="h", requester_agent_id="a", requester_task_id="t", reason="r"
    )
    assert await await_decision(request, timeout_s=1) == HOLD


@pytest.mark.asyncio
async def test_an_unknown_decision_is_refused(env):
    with pytest.raises(ValueError):
        await answer_yield("some-token", "maybe")


def test_decode_ignores_ordinary_task_events():
    """These arrive mixed with state changes on the same channel."""
    assert decode_yield_request({"event": "state_change", "state": "working"}) is None
    decoded = decode_yield_request(
        {
            "event": "work_claim_yield_request",
            "token": "tok",
            "scope": "path:a/b",
            "requester_agent_id": "a2",
            "requester_task_id": "t2",
            "reason": "why",
        }
    )
    assert isinstance(decoded, YieldRequest)
    assert decoded.token == "tok" and decoded.scope == "path:a/b"


@pytest.mark.asyncio
async def test_inviting_a_waiter_publishes_to_that_waiter(env):
    manager, _ = env
    from autobot_shared.coordination.claim_waitlist import join

    await join("path:a/b", agent_id="w1", task_id="tw", intent="waiting")
    invited = await invite_next_waiter("path:a/b")
    assert invited is not None and invited.agent_id == "w1"
    task_id, payload = manager.published[-1]
    assert task_id == "tw"
    assert payload["event"] == "work_claim_available"


@pytest.mark.asyncio
async def test_inviting_on_an_empty_queue_publishes_nothing(env):
    manager, _ = env
    assert await invite_next_waiter("path:a/b") is None
    assert manager.published == []
