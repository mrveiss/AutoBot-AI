# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat-send per-user limit refuses requests, not merely calls ``acquire`` (#16857).

#16857's acceptance criterion: "a test per wired limiter asserts a request is
actually refused when the limit is exceeded -- not that acquire was called. A
mock that returns truthy passes against an unwired limiter." So the shared
``RateLimiter`` runs for real here, its Lua sliding window executing against
fakeredis, and the assertion is the HTTP status of the request past the limit.

The dependency is mounted exactly as production mounts it: through
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

import api.chat_send_rate_limit as send_limit  # noqa: E402
import autobot_shared.rate_limiter as shared_rate_limiter  # noqa: E402
from initialization.router_registry.route_dependencies import dependencies_for  # noqa: E402

_PER_MINUTE = shared_rate_limiter._get_tier_defaults()["authenticated"][0]
_CHAT_PY = Path(__file__).resolve().parent / "chat.py"


def _app() -> FastAPI:
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
    return app


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    # One server, a fresh client per call: each TestClient runs its own event loop,
    # and an async client bound to one loop must not be reused from another.
    server = fakeredis.FakeServer()
    get_client = AsyncMock(side_effect=lambda **_kw: fakeredis_async.FakeRedis(server=server))
    monkeypatch.setattr(shared_rate_limiter, "get_async_redis_client", get_client)
    return server


@pytest.fixture()
def caller(monkeypatch):
    """Set who is calling; the dependency resolves the caller itself, after its send check."""
    current = {"user": {"user_id": "u-1"}}
    monkeypatch.setattr(send_limit, "get_current_user", AsyncMock(side_effect=lambda _req: current["user"]))
    return current


def test_a_user_past_the_limit_is_refused_with_retry_after(caller):
    client = TestClient(_app())
    for i in range(_PER_MINUTE):  # one user, many conversations: the limit is per user
        assert client.post(f"/api/chats/c-{i}/message").status_code == 200, f"send {i} refused early"

    refused = client.post("/api/chats/c-next/message")

    assert refused.status_code == 429, refused.text
    assert int(refused.headers["Retry-After"]) >= 0


def test_a_flood_by_one_user_does_not_lock_the_owner_out_of_their_conversation(caller):
    """The review finding that removed the per-conversation limit, pinned."""
    client = TestClient(_app())
    caller["user"] = {"user_id": "attacker"}
    for _ in range(_PER_MINUTE + 5):
        client.post("/api/chats/victim-conv/message")

    caller["user"] = {"user_id": "owner"}
    assert client.post("/api/chats/victim-conv/message").status_code == 200


def test_every_send_endpoint_shape_is_limited(caller):
    client = TestClient(_app())
    body = {"message": "hi", "chat_id": "c-1"}
    for _ in range(_PER_MINUTE):
        assert client.post("/api/chat/direct", json=body).status_code == 200
    assert client.post("/api/chat/direct", json=body).status_code == 429


def test_a_non_send_route_is_never_limited_and_never_resolves_the_caller(caller, monkeypatch):
    """No other chat route may gain an auth requirement or a cap from this dependency."""
    resolve = AsyncMock(side_effect=AssertionError("caller resolved on a non-send route"))
    monkeypatch.setattr(send_limit, "get_current_user", resolve)
    client = TestClient(_app())
    for _ in range(_PER_MINUTE * 2):
        assert client.get("/api/chats/c-1").status_code == 200
    resolve.assert_not_awaited()


def test_a_caller_without_a_user_id_is_not_counted(caller):
    """The internal-service identity carries no user_id and is not a user."""
    caller["user"] = {"username": "internal-service", "role": "admin", "service": True}
    client = TestClient(_app())
    for _ in range(_PER_MINUTE * 2):
        assert client.post("/api/chats/c-1/message").status_code == 200


def test_every_named_send_endpoint_is_a_post_route_in_api_chat():
    """A renamed handler would silently drop out of SEND_ENDPOINTS; this makes it loud."""
    posts = {
        node.name
        for node in ast.parse(_CHAT_PY.read_text(encoding="utf-8")).body
        if isinstance(node, ast.AsyncFunctionDef)
        and any(isinstance(d, ast.Call) and ast.unparse(d.func) == "router.post" for d in node.decorator_list)
    }
    missing = sorted(send_limit.SEND_ENDPOINTS - posts)
    assert not missing, f"SEND_ENDPOINTS names no POST route in api/chat.py: {missing}"


def test_every_send_endpoint_keeps_its_name_through_its_decorators():
    """The limit matches the *runtime* endpoint name, so the source name is not enough.

    The AST check above proves each name is defined in ``api/chat.py``. This one
    imports the real router and proves each name is still the ``__name__`` of a
    registered POST route after its decorators: a wrapper that stopped preserving
    ``__name__`` (``with_error_handling`` uses ``functools.wraps`` today) would
    make ``_is_send`` skip every send route while the AST check stayed green.
    """
    from api.chat import router as chat_router
    from autobot_shared.api_routing.router_routes import effective_routes

    # effective_routes, not chat_router.routes: api.chat includes child routers, and
    # under fastapi>=0.139 `.routes` holds opaque wrappers for them (#15093).
    runtime_posts = {
        mounted.route.endpoint.__name__
        for mounted in effective_routes(chat_router)
        if "POST" in getattr(mounted.route, "methods", set())
    }
    assert len(runtime_posts) >= len(send_limit.SEND_ENDPOINTS), (
        f"found {len(runtime_posts)} POST routes on api.chat -- the walk did not reach them, "
        "and an empty set would make the check below pass vacuously"
    )
    lost = sorted(send_limit.SEND_ENDPOINTS - runtime_posts)
    assert not lost, f"send endpoints whose routed name no longer matches SEND_ENDPOINTS: {lost}"
