# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat-send rate limits refuse requests, not merely call ``acquire`` (#16857).

#16857's acceptance criterion: "a test per wired limiter asserts a request is
actually refused when the limit is exceeded -- not that acquire was called. A
mock that returns truthy passes against an unwired limiter." So the shared
``RateLimiter`` runs for real here, its Lua sliding window executing against
fakeredis, and the assertion is the HTTP status of the request past the limit.

The limiters are mounted exactly as production mounts them: through
``route_dependencies.dependencies_for("chat")``.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fakeredis")
pytest.importorskip("lupa")  # the limiter's check-and-record is a Lua script

import fakeredis  # noqa: E402
import fakeredis.aioredis as fakeredis_async  # noqa: E402
from fastapi import APIRouter, Body, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import autobot_shared.rate_limiter as shared_rate_limiter  # noqa: E402
from api.chat_send_rate_limit import SEND_ENDPOINTS  # noqa: E402
from auth_middleware import get_current_user  # noqa: E402
from initialization.router_registry.route_dependencies import dependencies_for  # noqa: E402

_AUTH_PER_MINUTE = shared_rate_limiter._TIER_DEFAULTS["authenticated"][0]
_CHAT_PY = Path(__file__).resolve().parent / "chat.py"


def _app(user: dict) -> FastAPI:
    """A router whose handlers carry real send-endpoint names, mounted like ``api.chat``."""
    router = APIRouter()

    @router.post("/chats/{chat_id}/message")
    async def send_chat_message_by_id(chat_id: str) -> dict:
        return {"ok": chat_id}

    @router.post("/chat/direct")
    async def send_direct_chat_response(message: str = Body(...), chat_id: str = Body(...)) -> dict:
        return {"ok": chat_id}

    @router.get("/chats/{chat_id}")
    async def get_chat(chat_id: str) -> dict:
        return {"ok": chat_id}

    app = FastAPI()
    app.include_router(router, prefix="/api", dependencies=dependencies_for("chat"))

    async def _user() -> dict:
        return user

    app.dependency_overrides[get_current_user] = _user
    return app


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    # One server, a fresh client per call: each TestClient runs its own event loop,
    # and an async client bound to one loop must not be reused from another.
    server = fakeredis.FakeServer()
    get_client = AsyncMock(side_effect=lambda **_kw: fakeredis_async.FakeRedis(server=server))
    monkeypatch.setattr(shared_rate_limiter, "get_async_redis_client", get_client)
    return server


def test_a_user_past_the_per_user_limit_is_refused_with_retry_after():
    client = TestClient(_app({"user_id": "u-1"}))
    for i in range(_AUTH_PER_MINUTE):  # each send to a different conversation
        assert client.post(f"/api/chats/c-{i}/message").status_code == 200, f"send {i} refused early"

    refused = client.post("/api/chats/c-next/message")

    assert refused.status_code == 429, refused.text
    assert "user" in refused.json()["detail"]
    assert int(refused.headers["Retry-After"]) >= 0


def test_a_conversation_past_its_limit_is_refused_even_across_users():
    for i in range(_AUTH_PER_MINUTE):  # each send from a different user, all to one conversation
        resp = TestClient(_app({"user_id": f"u-{i}"})).post("/api/chats/shared/message")
        assert resp.status_code == 200, f"send {i} refused early"

    refused = TestClient(_app({"user_id": "u-last"})).post("/api/chats/shared/message")

    assert refused.status_code == 429, refused.text
    assert "conversation" in refused.json()["detail"]


def test_the_conversation_is_read_from_the_body_when_the_path_has_none():
    for i in range(_AUTH_PER_MINUTE):
        body = {"message": "hi", "chat_id": "body-conv"}
        assert TestClient(_app({"user_id": f"b-{i}"})).post("/api/chat/direct", json=body).status_code == 200

    refused = TestClient(_app({"user_id": "b-last"})).post(
        "/api/chat/direct", json={"message": "hi", "chat_id": "body-conv"}
    )

    assert refused.status_code == 429, refused.text


def test_a_non_send_route_is_never_limited():
    """The owner's scoping: a route-wide cap would throttle the UI's own polling."""
    client = TestClient(_app({"user_id": "poller"}))
    for _ in range(_AUTH_PER_MINUTE * 2):
        assert client.get("/api/chats/c-1").status_code == 200


def test_every_named_send_endpoint_is_a_post_route_in_api_chat():
    """A renamed handler would silently drop out of SEND_ENDPOINTS; this makes it loud."""
    posts = {
        node.name
        for node in ast.parse(_CHAT_PY.read_text(encoding="utf-8")).body
        if isinstance(node, ast.AsyncFunctionDef)
        and any(isinstance(d, ast.Call) and ast.unparse(d.func) == "router.post" for d in node.decorator_list)
    }
    missing = sorted(SEND_ENDPOINTS - posts)
    assert not missing, f"SEND_ENDPOINTS names no POST route in api/chat.py: {missing}"
