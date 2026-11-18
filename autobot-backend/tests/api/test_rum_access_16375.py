# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``api.rum`` access posture and ingest bounds (#16375, owner decision 2026-10-12).

``/config``, ``/disable``, ``/clear`` and ``/export`` are admin-only, ``/status``
needs a signed-in user, and the two ingest routes ``/event`` and ``/metrics``
stay open -- the browser's RumAgent sends no credential -- but bounded: rate
limited (429), size capped (413), field capped (422), one bounded row each.

Judged with the REAL auth dependencies, the way ``test_router_auth_16375.py``
does: under pytest ``auth_middleware`` is the conftest stub that always returns
an admin, so the module's ``Depends`` targets are overridden with the real ones
from ``real_auth_middleware`` and only the identity they read is controlled.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import api.rum as rum_api
import api.rum_ingest_bounds as bounds
from autobot_shared.rate_limit import IPRateLimiter

_PREFIX = "/api/rum"
_ADMIN, _USER, _OPEN = "admin", "user", "open"
_POLICY = {
    ("POST", "/api/rum/config"): _ADMIN,
    ("POST", "/api/rum/disable"): _ADMIN,
    ("POST", "/api/rum/clear"): _ADMIN,
    ("GET", "/api/rum/export"): _ADMIN,
    ("GET", "/api/rum/status"): _USER,
    ("POST", "/api/rum/event"): _OPEN,
    ("POST", "/api/rum/metrics"): _OPEN,
}
_GATED = sorted(k for k, v in _POLICY.items() if v != _OPEN)
_ADMIN_ROUTES = sorted(k for k, v in _POLICY.items() if v == _ADMIN)
_NON_ADMIN = {"username": "viewer", "role": "user"}
_ADMIN_USER = {"username": "root", "role": "admin"}


def _event(session: str = "rum_s1", **overrides) -> dict:
    body = {
        "type": "javascript_error",
        "timestamp": "2026-10-12T12:00:00.000Z",
        "sessionId": session,
        "url": "http://frontend.invalid/login",
        "userAgent": "pytest",
        "data": {"message": "boom"},
    }
    body.update(overrides)
    return body


@pytest.fixture
def rum_state(monkeypatch):
    """Isolated RUM buffers, a fresh in-process limiter, and a silent RUM log."""
    monkeypatch.setattr(rum_api, "rum_events", [])
    monkeypatch.setattr(rum_api, "rum_sessions", {})
    monkeypatch.setitem(rum_api.rum_config, "enabled", True)
    monkeypatch.setattr(rum_api, "rum_logger", MagicMock())
    limiter = IPRateLimiter(key_prefix="ratelimit:rum_test", limit_env=bounds._RATE_ENV, default_limit=120)
    monkeypatch.setattr(bounds, "_ingest_limiter", limiter)
    monkeypatch.setattr("autobot_shared.redis_client.get_async_redis_client", AsyncMock(return_value=None))
    return rum_api


@pytest.fixture
def client(real_auth_middleware, monkeypatch, rum_state):
    """A client whose gate is the production code; ``identity.user`` is what it sees."""
    identity = SimpleNamespace(user=None)

    async def _no_token(_request):
        return None

    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: identity.user,
        _extract_user_from_run_jwt=_no_token,
        _extract_user_from_device_jwt=_no_token,
    )
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)
    app = FastAPI()
    app.include_router(rum_api.router, prefix=_PREFIX)
    app.dependency_overrides[rum_api.get_current_user] = real_auth_middleware.get_current_user
    app.dependency_overrides[rum_api.check_admin_permission] = real_auth_middleware.check_admin_permission
    return TestClient(app), identity


def _call(test_client: TestClient, method: str, path: str):
    return test_client.request(method, path, json={} if method == "POST" else None)


def test_the_policy_table_covers_every_route() -> None:
    served = {
        (method, _PREFIX + route.path)
        for route in rum_api.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    assert served == set(_POLICY)


@pytest.mark.parametrize(("method", "path"), _GATED)
def test_an_anonymous_caller_is_refused(client, method: str, path: str) -> None:
    test_client, _ = client
    assert _call(test_client, method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), _ADMIN_ROUTES)
def test_a_non_admin_is_refused_where_admin_is_required(client, method: str, path: str) -> None:
    test_client, identity = client
    identity.user = dict(_NON_ADMIN)
    assert _call(test_client, method, path).status_code == 403


def test_a_non_admin_still_reaches_status(client) -> None:
    """Contrast: the 401s and 403s above come from the gate, not a broken override."""
    test_client, identity = client
    identity.user = dict(_NON_ADMIN)
    assert test_client.get("/api/rum/status").status_code == 200


@pytest.mark.parametrize("path", ["/api/rum/clear", "/api/rum/disable"])
def test_an_admin_passes_the_admin_routes(client, path: str) -> None:
    test_client, identity = client
    identity.user = dict(_ADMIN_USER)
    assert test_client.post(path).status_code == 200


def test_an_admin_can_export(client) -> None:
    test_client, identity = client
    identity.user = dict(_ADMIN_USER)
    assert test_client.get("/api/rum/export").status_code == 200


def test_an_anonymous_event_is_accepted_and_writes_one_row(client, rum_state) -> None:
    test_client, _ = client
    response = test_client.post("/api/rum/event", json=_event())
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    assert len(rum_state.rum_events) == 1
    assert list(rum_state.rum_sessions) == ["rum_s1"]


def test_an_oversize_event_is_refused_and_writes_nothing(client, rum_state, monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_RUM_EVENT_MAX_BYTES", "512")
    test_client, _ = client
    response = test_client.post("/api/rum/event", json=_event(data={"stack": "x" * 1024}))
    assert response.status_code == 413
    assert rum_state.rum_events == []


def test_an_overlong_field_is_refused_and_writes_nothing(client, rum_state) -> None:
    test_client, _ = client
    cap = bounds.EVENT_FIELD_CAPS["sessionId"]
    response = test_client.post("/api/rum/event", json=_event(session="s" * (cap + 1)))
    assert response.status_code == 422
    assert rum_state.rum_events == [] and rum_state.rum_sessions == {}


def test_a_flood_is_refused_after_the_limit(client, rum_state, monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_RUM_INGEST_RATE_LIMIT", "3")
    test_client, _ = client
    codes = [test_client.post("/api/rum/event", json=_event()).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert len(rum_state.rum_events) == 3


def test_the_event_buffer_and_session_table_are_capped(client, rum_state, monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_RUM_MAX_EVENTS", "2")
    monkeypatch.setenv("AUTOBOT_RUM_MAX_SESSIONS", "2")
    test_client, _ = client
    for session in ("a", "b", "c"):
        assert test_client.post("/api/rum/event", json=_event(session=session)).status_code == 200
    assert [e["sessionId"] for e in rum_state.rum_events] == ["b", "c"]
    assert list(rum_state.rum_sessions) == ["b", "c"]


def test_anonymous_metrics_are_accepted_and_oversize_refused(client, monkeypatch) -> None:
    test_client, _ = client
    body = {"session_id": "rum_s1", "timestamp": "2026-10-12T12:00:00Z"}
    assert test_client.post("/api/rum/metrics", json=body).status_code == 200
    monkeypatch.setenv("AUTOBOT_RUM_METRICS_MAX_BYTES", "16")
    assert test_client.post("/api/rum/metrics", json=body).status_code == 413


# ---------------------------------------------------------------------------
# #18368 / review: /metrics bounds, streaming body cap, log-line escaping
# ---------------------------------------------------------------------------


def _chunks(total: int, size: int = 256):
    sent = 0
    yield b'{"session_id": "s", "timestamp": "t", "pad": "'
    while sent < total:
        yield b"x" * size
        sent += size
    yield b'"}'


def test_a_chunked_body_without_content_length_is_refused_while_streaming(client, monkeypatch) -> None:
    """No Content-Length to check: the cap must count bytes as they arrive."""
    monkeypatch.setenv("AUTOBOT_RUM_METRICS_MAX_BYTES", "1024")
    parsed = []
    monkeypatch.setattr(rum_api, "enforce_metrics_caps", lambda m: parsed.append(m))
    test_client, _ = client
    response = test_client.post(
        "/api/rum/metrics", content=_chunks(64 * 1024), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert parsed == [], "the handler (and so the JSON parse) must never have been reached"


def test_the_body_cap_is_scoped_to_the_ingest_routes() -> None:
    from api.rum_body_cap import BODY_CAP_ENV

    assert set(BODY_CAP_ENV) == {"/event", "/metrics"}


def _metrics(**lists) -> dict:
    body = {"session_id": "rum_s1", "timestamp": "2026-10-12T12:00:00Z"}
    body.update(lists)
    return body


def test_an_oversize_metrics_list_is_refused(client, monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_RUM_METRICS_MAX_ITEMS", "5")
    test_client, _ = client
    item = {"resource_type": "script", "load_time_seconds": 0.1}
    assert test_client.post("/api/rum/metrics", json=_metrics(resources=[item] * 5)).status_code == 200
    assert test_client.post("/api/rum/metrics", json=_metrics(resources=[item] * 6)).status_code == 422


def test_an_overlong_metrics_string_is_refused_even_nested(client, monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_RUM_METRICS_MAX_FIELD_CHARS", "32")
    test_client, _ = client
    errors = [{"error_type": "TypeError", "page": "/" + "p" * 40}]
    assert test_client.post("/api/rum/metrics", json=_metrics(js_errors=errors)).status_code == 422


def test_crlf_in_an_event_cannot_forge_a_log_line(client, rum_state) -> None:
    test_client, _ = client
    forged = "boom\r\n2026-10-12 - RUM - ERROR - forged entry"
    body = _event(type="error", data={"message": forged})
    assert test_client.post("/api/rum/event", json=body).status_code == 200
    line = rum_state.rum_logger.error.call_args.args[0]
    assert "forged entry" in line, "the formatter must have interpolated the raw message"
    assert "\n" not in line and "\r" not in line
    assert "\\x0d\\x0a" in line
