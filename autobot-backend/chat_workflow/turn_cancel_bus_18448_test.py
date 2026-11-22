# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A cancel reaches the turn whichever worker receives it (#18448).

Two simulated workers share one Redis: worker A runs the real turn (the default
bus identity), worker B only receives the HTTP cancel (``worker_id="worker-b"``,
holding no turn of its own). Before #18448 B answered "no turn" and A's model
kept generating.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from autobot_shared.eventually import eventually
from chat_workflow import graph as graph_module
from chat_workflow import turn_cancel_bus as bus
from chat_workflow import turn_control
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.turn_control_17273_test import _FakeGraph
from tests.helpers._fake_pubsub_redis import FakeRedis


@pytest.fixture
def redis(monkeypatch):
    shared = FakeRedis()
    monkeypatch.setattr(bus, "get_async_redis_client", AsyncMock(return_value=shared))
    monkeypatch.setattr(graph_module, "delete_thread_checkpoints", AsyncMock())
    return shared


async def _no_local_turn(_session_id, _reason):
    return 0


async def _running_turn(monkeypatch, session_id):
    fake = _FakeGraph()
    monkeypatch.setattr(graph_module, "get_compiled_graph", AsyncMock(return_value=fake))
    stream = ChatWorkflowManager()._process_via_graph(session_id, "hi", {})
    await stream.__anext__()
    await asyncio.wait_for(fake.llm_started.wait(), 2)
    return fake, stream


@pytest.mark.asyncio
async def test_a_cancel_on_worker_b_stops_the_turn_on_worker_a(redis, monkeypatch):
    fake, stream = await _running_turn(monkeypatch, "s-xw")

    outcome = await bus.request_cancel("s-xw", "client_cancel", _no_local_turn, worker_id="worker-b")
    rest = [m async for m in stream]

    assert outcome == bus.CancelOutcome(cancelled=1, confirmed=True)
    assert fake.llm_cancelled is True, "the LLM call on the other worker must be cancelled"
    assert [m.type for m in rest] == ["cancelled"]
    assert not turn_control.has_active_turn("s-xw")
    assert redis.listeners(bus.CHANNEL_PREFIX) == 0 and redis.listeners(bus.ACK_PREFIX) == 0, "no subscription leaks"


@pytest.mark.asyncio
async def test_a_cancel_for_a_session_nobody_runs_is_confirmed_empty(redis):
    outcome = await bus.request_cancel("s-none", "client_cancel", _no_local_turn, worker_id="worker-b")

    assert outcome == bus.CancelOutcome(cancelled=0, confirmed=True)


@pytest.mark.asyncio
async def test_a_cancel_never_touches_another_sessions_turn(redis, monkeypatch):
    fake, stream = await _running_turn(monkeypatch, "s-mine")

    outcome = await bus.request_cancel("s-other", "client_cancel", _no_local_turn, worker_id="worker-b")

    assert outcome.cancelled == 0 and fake.llm_cancelled is False
    await turn_control.cancel_turn("s-mine")
    await stream.aclose()


@pytest.mark.asyncio
async def test_the_local_worker_is_cancelled_once_not_twice(redis, monkeypatch):
    """Its own subscription sees the published request but acks 0 -- it already ran the teardown."""
    fake, stream = await _running_turn(monkeypatch, "s-local")

    outcome = await bus.request_cancel("s-local", "client_cancel", turn_control.cancel_turn)
    rest = [m async for m in stream]

    assert outcome == bus.CancelOutcome(cancelled=1, confirmed=True)
    assert fake.llm_cancelled is True and [m.type for m in rest] == ["cancelled"]


@pytest.mark.asyncio
async def test_an_unreachable_bus_is_unconfirmed_not_empty(monkeypatch):
    monkeypatch.setattr(bus, "get_async_redis_client", AsyncMock(return_value=None))

    outcome = await bus.request_cancel("s-x", "client_cancel", _no_local_turn, worker_id="worker-b")

    assert outcome == bus.CancelOutcome(cancelled=0, confirmed=False), "'no turn' would be a guess"


@pytest.mark.asyncio
async def test_a_failing_bus_still_cancels_the_local_turn(monkeypatch):
    monkeypatch.setattr(bus, "get_async_redis_client", AsyncMock(side_effect=ConnectionError("down")))

    async def local(_s, _r):
        return 1

    outcome = await bus.request_cancel("s-x", "client_cancel", local, worker_id="worker-b")

    assert outcome == bus.CancelOutcome(cancelled=1, confirmed=False)


@pytest.mark.asyncio
async def test_a_worker_that_never_answers_makes_the_outcome_unconfirmed(redis, monkeypatch):
    monkeypatch.setattr(bus, "CHAT_TURN_CANCEL_ACK_TIMEOUT_SECONDS", 0.1)
    silent = redis.pubsub()
    await silent.subscribe(bus.CHANNEL_PREFIX + "s-silent")  # listening, but never acks

    outcome = await bus.request_cancel("s-silent", "client_cancel", _no_local_turn, worker_id="worker-b")

    assert outcome == bus.CancelOutcome(cancelled=0, confirmed=False)


@pytest.mark.asyncio
async def test_a_malformed_message_does_not_end_the_listener(redis, monkeypatch, caplog):
    fake, stream = await _running_turn(monkeypatch, "s-bad")
    await redis.publish(bus.CHANNEL_PREFIX + "s-bad", json.dumps({"nonsense": True}))
    # The listener has rejected the bad message, so the cancel below reaches a listener that survived it.
    await eventually(lambda: "turn-cancel request for session s-bad failed" in caplog.text)

    outcome = await bus.request_cancel("s-bad", "client_cancel", _no_local_turn, worker_id="worker-b")
    await stream.aclose()

    assert outcome.cancelled == 1 and fake.llm_cancelled is True


@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf"])
def test_a_bad_ack_timeout_falls_back_to_the_default(monkeypatch, bad):
    import importlib

    monkeypatch.setenv("AUTOBOT_CHAT_TURN_CANCEL_ACK_TIMEOUT_SECONDS", bad)
    try:
        importlib.reload(bus)
        assert bus.CHAT_TURN_CANCEL_ACK_TIMEOUT_SECONDS == 5.0
    finally:
        monkeypatch.delenv("AUTOBOT_CHAT_TURN_CANCEL_ACK_TIMEOUT_SECONDS")
        importlib.reload(bus)
