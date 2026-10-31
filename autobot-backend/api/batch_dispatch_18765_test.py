# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""POST /api/batch-jobs/load dispatches through the ASGI app with the caller's credentials (#18765).

The old ``batch_load`` called ``route.endpoint`` directly, which bypassed every target route's
``Depends`` gate. These tests run a real FastAPI app (real ``check_admin_permission``, real
``get_current_user``); only the identity lookup is faked, from the forwarded Authorization header.


The suite runs against an ``auth_middleware`` stub that approves everyone, so the REAL module is
loaded (``load_real_auth_middleware``) and its ``check_admin_permission`` / ``get_current_user`` are
the gates under test; ``/load``'s stub dependency is overridden with the real one.
"""

import asyncio

import httpx
import pytest
from fastapi import Depends, FastAPI, Request

import api.batch_dispatch as bd
import api.batch_jobs as batch_jobs
import auth_middleware as stub_auth
from tests.conftest import load_real_auth_middleware

INTERNAL_KEY = "svc-key"
USERS = {"Bearer alice": {"username": "alice", "role": "user"}, "Bearer root": {"username": "root", "role": "admin"}}


class _FakeAuth:
    def get_user_from_request(self, request):
        return USERS.get(request.headers.get("authorization", ""))

    async def _extract_user_from_run_jwt(self, request):
        return None

    async def _extract_user_from_device_jwt(self, request):
        return None


@pytest.fixture
def calls(monkeypatch):
    real = load_real_auth_middleware()
    monkeypatch.setattr(real, "get_auth_middleware", lambda: _FakeAuth())
    monkeypatch.setattr(real, "verify_internal_api_key", lambda key: key == INTERNAL_KEY)
    return []


def _app(calls: list) -> FastAPI:
    real = load_real_auth_middleware()
    app = FastAPI()
    app.include_router(batch_jobs.router, prefix="/api/batch-jobs")
    app.dependency_overrides[stub_auth.get_current_user] = real.get_current_user

    @app.get("/api/chats", dependencies=[Depends(real.check_admin_permission)])
    async def admin_only():
        calls.append("admin_only")
        return {"secret": 1}

    @app.get("/api/chat/health")
    async def echo(request: Request):
        user = _FakeAuth().get_user_from_request(request)
        return {"user": user and user["username"], "headers": dict(request.headers)}

    @app.get("/api/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/system/health")
    async def boom():
        raise RuntimeError("kaput")

    @app.get("/api/slow")
    async def slow():
        await asyncio.sleep(2)

    @app.get("/api/not-listed")
    async def not_listed():
        calls.append("not_listed")
        return {}

    return app


async def _load(calls, requests, headers=None):
    app = _app(calls)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post("/api/batch-jobs/load", json={"requests": requests}, headers=headers or {})


def _get(endpoint, **kw):
    return {"endpoint": endpoint, "method": "GET", **kw}


@pytest.mark.asyncio
async def test_a_non_admin_gets_the_admin_route_403_in_its_slot_and_the_handler_never_runs(calls) -> None:
    resp = await _load(calls, [_get("/api/chats")], {"Authorization": "Bearer alice"})
    assert resp.status_code == 200
    item = resp.json()["results"][0]
    assert item["status"] == 403
    assert item["error"]
    assert item["refused"] is False  # contrast: the route's own 403 was dispatched, not refused
    assert calls == []


@pytest.mark.asyncio
async def test_an_admin_caller_reaches_the_admin_route(calls) -> None:
    resp = await _load(calls, [_get("/api/chats")], {"Authorization": "Bearer root"})
    assert resp.json()["results"][0]["status"] == 200
    assert calls == ["admin_only"]


@pytest.mark.asyncio
async def test_the_callers_jwt_is_forwarded_and_the_internal_key_is_not(calls) -> None:
    headers = {"Authorization": "Bearer alice", "X-Internal-API-Key": INTERNAL_KEY, "X-Other": "x"}
    resp = await _load(calls, [_get("/api/chat/health")], headers)
    body = resp.json()["results"][0]["body"]
    assert body["user"] == "alice"
    assert "x-internal-api-key" not in body["headers"]
    assert "x-other" not in body["headers"]


@pytest.mark.asyncio
async def test_the_internal_key_alone_does_not_escalate_a_batch_to_admin(calls) -> None:
    resp = await _load(
        calls, [_get("/api/chats")], {"Authorization": "Bearer alice", "X-Internal-API-Key": INTERNAL_KEY}
    )
    assert resp.json()["results"][0]["status"] == 403
    assert calls == []


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/not-listed",
        "http://evil.example/api/health",
        "//evil.example/api/health",
        "/api/../api/chats",
        "/api/health/../chats",
        "/api/health?x=1",
        "/api/batch-jobs/load",
        "/api/batch-jobs/status",
        "/health",
        "",
        "/api/%2e%2e/chats",
        "/api//chats",
        "/api/chats/",
        "/API/chats",
    ],
)
@pytest.mark.asyncio
async def test_a_refused_endpoint_never_dispatches(calls, endpoint) -> None:
    resp = await _load(calls, [_get(endpoint)], {"Authorization": "Bearer root"})
    item = resp.json()["results"][0]
    assert item["status"] in (400, 403)
    assert item["body"] is None
    assert item["refused"] is True  # the client runs a refused slot directly
    assert calls == []


@pytest.mark.asyncio
async def test_a_sub_request_401_propagates_into_its_slot(calls) -> None:
    """The internal key admits /load itself but is never forwarded, so the sub-request is anonymous."""
    resp = await _load(calls, [_get("/api/chats")], {"X-Internal-API-Key": INTERNAL_KEY})
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"][0]["status"] == 401  # the gated route sees an anonymous caller
    assert calls == []


@pytest.mark.asyncio
async def test_an_empty_batch_is_refused_with_400(calls) -> None:
    resp = await _load(calls, [], {"Authorization": "Bearer root"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_a_mutating_method_is_refused(calls) -> None:
    req = {"endpoint": "/api/health", "method": "POST"}
    resp = await _load(calls, [req], {"Authorization": "Bearer root"})
    assert resp.json()["results"][0]["status"] == 403


@pytest.mark.asyncio
async def test_a_batch_over_the_maximum_is_refused_with_400(calls, monkeypatch) -> None:
    monkeypatch.setattr(bd, "BATCH_MAX_REQUESTS", 2)
    resp = await _load(calls, [_get("/api/health")] * 3, {"Authorization": "Bearer root"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_a_mixed_batch_reports_each_item_and_one_failure_does_not_fail_the_batch(calls) -> None:
    reqs = [
        _get("/api/health"),
        _get("/api/chats"),
        _get("/api/system/health"),
        _get("/api/not-listed"),
        _get("/api/chat/health"),
    ]
    resp = await _load(calls, reqs, {"Authorization": "Bearer alice"})
    assert resp.status_code == 200
    statuses = [r["status"] for r in resp.json()["results"]]
    assert statuses == [200, 403, 500, 403, 200]
    assert resp.json()["results"][0]["body"] == {"status": "healthy"}


@pytest.mark.asyncio
async def test_a_slow_sub_request_times_out_in_its_own_slot(calls, monkeypatch) -> None:
    monkeypatch.setattr(bd, "BATCH_SUBREQUEST_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(bd, "BATCHABLE_GET_PATHS", bd.BATCHABLE_GET_PATHS | {"/api/slow"})
    resp = await _load(calls, [_get("/api/slow"), _get("/api/health")], {"Authorization": "Bearer alice"})
    results = resp.json()["results"]
    assert [r["status"] for r in results] == [504, 200]
    assert "timed out" in results[0]["error"]


@pytest.mark.asyncio
async def test_an_anonymous_call_to_load_is_401(calls) -> None:
    resp = await _load(calls, [_get("/api/health")])
    assert resp.status_code == 401


def test_the_allow_list_is_get_paths_under_api_and_never_the_batch_endpoint() -> None:
    assert bd.BATCHABLE_GET_PATHS
    assert all(p.startswith("/api/") and not p.startswith("/api/batch-jobs") for p in bd.BATCHABLE_GET_PATHS)


def test_only_credentials_are_forwardable() -> None:
    assert set(bd.FORWARDED_HEADERS) == {"authorization", "cookie", "x-session-id"}
