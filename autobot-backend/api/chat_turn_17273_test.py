# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /chat/sessions/{id}/turn/cancel: owner-only, idempotent, honest (#17273, #18448).

The route is mounted through a real request. The ownership tests use the REAL
validator under the default feature-flag state (``log_only``), where the default
posture lets a non-owner who knows a session id through -- the route must not.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from api import chat_turn
from auth_middleware import get_current_user
from chat_workflow import graph as graph_module
from chat_workflow import turn_cancel_bus as bus
from chat_workflow import turn_control
from testkit.canonical_gate import install_canonical_resolver
from tests.helpers._fake_pubsub_redis import FakeRedis

URL = "/chat/sessions/{}/turn/cancel"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(chat_turn.router)
    app.dependency_overrides[get_current_user] = lambda: {"username": "bob"}
    return app


def _as_user(monkeypatch, username: str, owner: str | None) -> MagicMock:
    """Authenticate *username*; the durable owner of every session is *owner*. Nothing else is mocked."""
    install_canonical_resolver(
        monkeypatch,
        "security.session_posture.resolve_human_user",
        MagicMock(get_user_from_request=lambda _r: {"username": username, "role": "user"}),
    )
    history = MagicMock(get_session_owner=AsyncMock(return_value=owner))
    monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", lambda _r: history)
    return history


async def _post(session_id: str):
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post(URL.format(session_id))


@pytest.fixture(autouse=True)
def fake_bus(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(bus, "get_async_redis_client", AsyncMock(return_value=redis))
    monkeypatch.setattr(graph_module, "delete_thread_checkpoints", AsyncMock())
    return redis


async def _register_turn(session_id: str):
    state = {}

    async def _turn():
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    turn = turn_control._Turn(session_id=session_id)
    turn.task = asyncio.create_task(_turn())
    turn_control._REGISTRY.add(turn)
    await asyncio.sleep(0)
    return turn, state


@pytest.mark.asyncio
async def test_a_non_owner_gets_403_and_the_turn_and_checkpoint_survive(monkeypatch):
    _as_user(monkeypatch, "bob", owner="alice")
    turn, state = await _register_turn("alices-chat")
    try:
        response = await _post("alices-chat")

        assert response.status_code == 403
        assert not turn.task.done() and "cancelled" not in state, "a refused caller must not stop the run"
        graph_module.delete_thread_checkpoints.assert_not_awaited()
    finally:
        turn.task.cancel()
        turn_control._REGISTRY.remove(turn)


@pytest.mark.asyncio
async def test_the_owner_cancels_a_running_turn_and_a_second_cancel_is_a_noop(monkeypatch):
    _as_user(monkeypatch, "alice", owner="alice")
    turn, state = await _register_turn("alices-chat")
    try:
        first = await _post("alices-chat")
        again = await _post("alices-chat")
    finally:
        turn_control._REGISTRY.remove(turn)

    assert state["cancelled"] is True and turn.task.cancelled()
    assert first.status_code == 200
    assert first.json()["data"] == {"session_id": "alices-chat", "status": "cancelled", "cancelled_turns": 1}
    assert again.json()["data"] == {"session_id": "alices-chat", "status": "no_active_turn", "cancelled_turns": 0}


@pytest.mark.asyncio
async def test_cancel_with_no_turn_is_a_clear_noop(monkeypatch):
    _as_user(monkeypatch, "alice", owner="alice")

    response = await _post("alices-chat")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "no_active_turn"


@pytest.mark.asyncio
async def test_an_unreachable_bus_says_unconfirmed_not_no_active_turn(monkeypatch):
    _as_user(monkeypatch, "alice", owner="alice")
    monkeypatch.setattr(bus, "get_async_redis_client", AsyncMock(return_value=None))

    response = await _post("alices-chat")

    assert response.json()["data"] == {"session_id": "alices-chat", "status": "unconfirmed", "cancelled_turns": 0}


@pytest.mark.asyncio
async def test_an_unreadable_owner_is_denied(monkeypatch):
    history = _as_user(monkeypatch, "alice", owner="alice")
    history.get_session_owner.side_effect = RuntimeError("redis down")

    assert (await _post("alices-chat")).status_code == 403


@pytest.mark.asyncio
async def test_the_route_asks_for_the_strict_posture():
    """Behaviour is tested above; this pins the seam so the default posture cannot slip back in."""
    from security.session_posture import SessionPosture

    seen = {}

    async def spy(session_id, request, posture=SessionPosture.DEFAULT):
        seen["posture"] = posture
        return {"authorized": True}

    original = chat_turn.validate_session_ownership
    chat_turn.validate_session_ownership = spy
    try:
        await _post("alices-chat")
    finally:
        chat_turn.validate_session_ownership = original

    assert seen["posture"] is SessionPosture.STRICT
