# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every gate path refuses a token revoked by a password change (#18688, slice 3).

Before this slice, each path below resolved its caller with the synchronous
``get_user_from_request``, which cannot await the Redis password-epoch check --
so a JWT minted before its subject's password changed still passed there. Each
now resolves through the canonical ``auth_middleware.resolve_human_user``.

The REAL ``auth_middleware`` runs (``tests.conftest.load_real_auth_middleware``);
only the identity it reads and the epoch lookup are stood in. A path that still
skipped revocation answers the revoked token instead of raising 401.
"""

import asyncio
import importlib
import inspect
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from tests.conftest import load_real_auth_middleware

INTERNAL_KEY = "internal-service-key-for-tests"
_JWT_ADMIN = {"username": "alice", "role": "admin", "user_id": str(uuid.uuid4()), "iat": 1, "auth_method": "jwt"}


def _request(headers: dict | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": "GET", "path": "/probe", "query_string": b"", "headers": raw}
    scope.update({"client": ("testclient", 50000), "app": FastAPI()})
    return Request(scope)


def _resolve(value):
    """Await *value* when the path is async; a sync path (main's) answers directly."""
    return asyncio.run(value) if inspect.isawaitable(value) else value


def _sees(monkeypatch, module, user: dict | None):
    """Make *module*'s user lookup, through the real gate, answer *user*. Returns the real module.

    Both seams are set (``raising=False``) so the same table judges main, where the
    path read ``get_auth_middleware().get_user_from_request`` without revocation.
    """
    real = load_real_auth_middleware()
    middleware = SimpleNamespace(get_user_from_request=lambda _request: dict(user) if user else None)
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(real, "verify_internal_api_key", lambda provided: provided == INTERNAL_KEY)
    monkeypatch.setattr(module, "resolve_human_user", real.resolve_human_user, raising=False)
    monkeypatch.setattr(module, "get_auth_middleware", lambda: middleware, raising=False)
    return real


def _epoch_says(monkeypatch, revoked: bool) -> None:
    import auth_revocation  # noqa: PLC0415

    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=revoked))


def _admin_gate(monkeypatch):
    real = _sees(monkeypatch, load_real_auth_middleware(), _JWT_ADMIN)
    return lambda request: real.check_admin_permission(request)


def _module_path(name: str, call):
    def build(monkeypatch):
        module = importlib.import_module(name)
        _sees(monkeypatch, module, _JWT_ADMIN)
        return lambda request: call(module, request)

    return build


def _operator_gate(monkeypatch, role: str = "operator"):
    import security.human_admin as human_admin  # noqa: PLC0415

    real = _sees(monkeypatch, human_admin, {**_JWT_ADMIN, "role": role})
    monkeypatch.setattr(human_admin, "auth_middleware", real)  # the gate reads the module at call time
    return lambda request: human_admin.require_human_operator(request)


def _envelope_principal(monkeypatch):
    from user_management.middleware.rbac_middleware import rbac_middleware  # noqa: PLC0415

    monkeypatch.setattr(rbac_middleware, "get_user_permissions", AsyncMock(return_value=[]))
    return _module_path("api.envelope_secrets", lambda m, r: m.principal(r))(monkeypatch)


_PATHS = {
    "auth_middleware.check_admin_permission": _admin_gate,
    "auth_rbac._request_caller (require_permission)": _module_path("auth_rbac", lambda m, r: m._request_caller(r)),
    "auth_rbac.require_role": _module_path("auth_rbac", lambda m, r: m.require_role("admin")(r)),
    "verbatim_memory._require_user": _module_path("api.verbatim_memory", lambda m, r: m._require_user(r)),
    "envelope_secrets.principal": _envelope_principal,
    "session_posture.authenticated_user": _module_path(
        "security.session_posture", lambda m, r: m.authenticated_user("session-1", r)
    ),
    "human_admin.require_human_operator (redis_service /start, /restart)": lambda mp: _operator_gate(mp),
    "chat_shared_links._enforce_require_login": _module_path(
        "api.chat_shared_links", lambda m, r: m._enforce_require_login(SimpleNamespace(require_login=True), r)
    ),
    "auth_me GET /auth/me": _module_path("api.auth_me", lambda m, r: m.get_current_user_info(r)),
}


@pytest.mark.parametrize("path", sorted(_PATHS))
def test_a_password_change_revoked_jwt_is_refused(monkeypatch, path):
    call = _PATHS[path](monkeypatch)
    _epoch_says(monkeypatch, revoked=True)

    with pytest.raises(HTTPException) as exc:
        _resolve(call(_request()))

    assert exc.value.status_code == 401
    assert "password was changed" in exc.value.detail


@pytest.mark.parametrize("path", sorted(_PATHS))
def test_a_fresh_jwt_passes(monkeypatch, path):
    call = _PATHS[path](monkeypatch)
    _epoch_says(monkeypatch, revoked=False)

    _resolve(call(_request()))  # no refusal


@pytest.mark.parametrize("role", ["superadmin", "admin", "operator"])
def test_the_admin_family_and_operator_pass_the_redis_gate(monkeypatch, role):
    """#19125: superadmin is the highest admin -- main's literal {"admin","operator"} refused it."""
    call = _operator_gate(monkeypatch, role)
    _epoch_says(monkeypatch, revoked=False)

    principal = _resolve(call(_request()))
    assert principal["username"] == "alice"  # the audit trail attributes the action to this identity


@pytest.mark.parametrize("role", ["analyst", "user"])
def test_a_role_outside_the_admin_family_is_refused_by_the_redis_gate(monkeypatch, role):
    call = _operator_gate(monkeypatch, role)
    _epoch_says(monkeypatch, revoked=False)

    with pytest.raises(HTTPException) as refused:
        _resolve(call(_request()))
    assert refused.value.status_code == 403


def test_an_epoch_store_that_cannot_answer_denies_the_admin_gate(monkeypatch):
    """Revocation-store failure follows get_current_user's policy: fail closed with a 503 the client
    retries, not a 401 that ends the session (#16411, #18892)."""
    import auth_revocation  # noqa: PLC0415
    from autobot_shared.auth.revocation_unavailable import REVOCATION_UNAVAILABLE_DETAIL  # noqa: PLC0415
    from autobot_shared.user_management.password_epoch import RevocationCheckUnavailable  # noqa: PLC0415

    call = _admin_gate(monkeypatch)
    unavailable = AsyncMock(side_effect=RevocationCheckUnavailable("epoch store unreachable"))
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", unavailable)

    with pytest.raises(HTTPException) as exc:
        _resolve(call(_request()))

    assert exc.value.status_code == 503
    assert exc.value.detail == REVOCATION_UNAVAILABLE_DETAIL
    assert int(exc.value.headers["Retry-After"]) >= 1


def test_the_internal_key_still_passes_the_admin_gate_without_an_epoch_lookup(monkeypatch):
    call = _admin_gate(monkeypatch)
    epoch = AsyncMock(return_value=True)
    import auth_revocation  # noqa: PLC0415

    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", epoch)

    assert _resolve(call(_request({"X-Internal-API-Key": INTERNAL_KEY}))) is True
    epoch.assert_not_called()


def _create_session(monkeypatch):
    """Run ``POST /chat/sessions``'s handler with storage stood in; returns (call, manager)."""
    import api.chat_sessions as chat_sessions  # noqa: PLC0415

    _sees(monkeypatch, chat_sessions, _JWT_ADMIN)
    manager = MagicMock(create_session=AsyncMock(return_value={"id": "s"}))
    monkeypatch.setattr(chat_sessions, "get_chat_history_manager", lambda _request: manager)
    for name in ("_register_session_ownership", "_track_session_in_memory_graph", "_emit_session_create"):
        monkeypatch.setattr(chat_sessions, name, AsyncMock())
    for name in ("log_request_context", "log_chat_event", "audit_record"):
        monkeypatch.setattr(chat_sessions, name, MagicMock())
    body = chat_sessions.SessionCreate(title="t")
    return (lambda request: chat_sessions.create_session(body, request)), manager


def test_a_revoked_jwt_creates_no_session_it_would_own(monkeypatch):
    call, manager = _create_session(monkeypatch)
    _epoch_says(monkeypatch, revoked=True)

    with pytest.raises(HTTPException) as exc:
        _resolve(call(_request()))

    assert exc.value.status_code == 401
    manager.create_session.assert_not_called()


def test_a_fresh_jwt_creates_a_session_owned_by_its_user(monkeypatch):
    call, manager = _create_session(monkeypatch)
    _epoch_says(monkeypatch, revoked=False)

    _resolve(call(_request()))

    assert manager.create_session.await_args.kwargs["metadata"]["owner"] == "alice"


# --- memory_privacy: the target user resolves through the canonical admin gate ------------------

_SERVICE = {"username": "service:slm", "role": "admin", "service": True}


def _target_resolver(monkeypatch, user: dict | None):
    """``_resolve_target_user`` with the REAL admin gate and service-key check behind it."""
    import api.memory_privacy as memory_privacy  # noqa: PLC0415
    import security.human_admin as human_admin  # noqa: PLC0415

    real = _sees(monkeypatch, load_real_auth_middleware(), user)
    monkeypatch.setattr(memory_privacy, "check_admin_permission", real.check_admin_permission)
    monkeypatch.setattr(human_admin, "auth_middleware", real)  # the same key check the gate makes
    return memory_privacy._resolve_target_user


def test_a_human_admin_resolves_another_users_memories(monkeypatch):
    resolve = _target_resolver(monkeypatch, _JWT_ADMIN)
    _epoch_says(monkeypatch, revoked=False)

    assert _resolve(resolve(_JWT_ADMIN, "bob", _request())) == "bob"


def test_a_caller_always_resolves_their_own_memories(monkeypatch):
    resolve = _target_resolver(monkeypatch, None)

    assert _resolve(resolve({"user_id": "bob", "role": "user"}, None, _request())) == "bob"


@pytest.mark.parametrize(
    "caller, headers",
    [
        (_SERVICE, {"X-Internal-API-Key": INTERNAL_KEY}),  # not a tenant admin (owner, 2026-10-17)
        ({"user_id": "carol", "role": "user"}, {}),
    ],
    ids=["service principal", "non-admin"],
)
def test_another_users_memories_are_refused(monkeypatch, caller, headers):
    resolve = _target_resolver(monkeypatch, None if caller is _SERVICE else dict(caller, auth_method="session"))

    with pytest.raises(HTTPException) as exc:
        _resolve(resolve(caller, "bob", _request(headers)))

    assert exc.value.status_code == 403
    assert exc.value.detail == "Only admins may access another user's memory records."


def test_a_revoked_admin_jwt_does_not_reach_another_users_memories(monkeypatch):
    resolve = _target_resolver(monkeypatch, _JWT_ADMIN)
    _epoch_says(monkeypatch, revoked=True)

    with pytest.raises(HTTPException) as exc:
        _resolve(resolve(_JWT_ADMIN, "bob", _request()))

    assert exc.value.status_code == 403


# --- end to end: real middleware, real JWT, real epoch store; nothing about revocation is mocked ---

_SIGNING_SECRET = "s" * 40


@pytest.fixture
def epochs():
    """An in-memory epoch store installed through the canonical seam (#18663); removed after."""
    from autobot_shared.user_management import password_epoch  # noqa: PLC0415

    store: dict[str, int] = {}

    async def get_epoch(subject: str) -> int | None:
        return store.get(subject)

    async def set_epoch(subject: str, *, now: int | None = None) -> int:
        store[subject] = int(time.time()) if now is None else now
        return store[subject]

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)
    yield password_epoch
    password_epoch.reset_epoch_store()


def _admin_route_client(monkeypatch) -> TestClient:
    """``Depends(check_admin_permission)`` of the real module, behind the real JWT-verifying middleware."""
    real = load_real_auth_middleware()
    cls = real.AuthenticationMiddleware
    middleware = cls.__new__(cls)
    middleware.jwt_secret = _SIGNING_SECRET
    middleware.jwt_public_key = None
    middleware.failed_attempts = {}
    middleware.enable_auth = True
    middleware.get_session = {}.get
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    app = FastAPI()
    app.get("/admin-only", dependencies=[Depends(real.check_admin_permission)])(lambda: {"ok": True})
    return TestClient(app, raise_server_exceptions=False)


def _login_jwt(issued_at: int) -> str:
    from autobot_shared.auth.interactive_principal import LOGIN_TOKEN_TYPE  # noqa: PLC0415
    from autobot_shared.auth.jwt_core import encode_jwt  # noqa: PLC0415

    claims = {
        "username": "alice",
        "role": "admin",
        "user_id": str(uuid.uuid4()),
        "token_type": LOGIN_TOKEN_TYPE,
        "iat": issued_at,
    }
    return encode_jwt(claims, secret=_SIGNING_SECRET, expiry_hours=1)


@pytest.mark.parametrize(
    "epoch_age, expected",
    [(0, 401), (60, 200), (None, 200)],
    ids=["epoch after the token", "token after the epoch", "control: no epoch"],
)
def test_a_real_jwt_meets_a_real_epoch_at_the_admin_gate(monkeypatch, epochs, epoch_age, expected):
    now = int(time.time())
    client = _admin_route_client(monkeypatch)
    if epoch_age is not None:
        asyncio.run(epochs.set_password_epoch("alice", now=now - epoch_age))
    token = _login_jwt(now - 10)

    response = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == expected, response.text
    if expected == 401:
        assert "password was changed" in response.json()["detail"]
