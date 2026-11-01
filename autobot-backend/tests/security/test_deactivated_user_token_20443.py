# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A deactivated or deleted user's already-issued tokens and sessions are refused (#20443).

A real signed login token goes through the REAL ``AuthenticationMiddleware`` extraction, the real
``get_current_user`` and the real shared epoch check; the user is deactivated or deleted through
the real shared ``UserService``. The marker is written after the commit, so each test commits the
session's queued callbacks (or does not). Only storage is stood in for: the epoch store (in
memory) and the database session.
"""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from autobot_shared.auth.interactive_principal import LOGIN_TOKEN_TYPE
from autobot_shared.auth.jwt_core import encode_jwt
from autobot_shared.db_session import (
    POST_COMMIT_CALLBACKS,
    PostCommitCallbackError,
    _run_post_commit_callbacks,
    async_session_scope,
)
from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.base_service import TenantContext
from autobot_shared.user_management.password_epoch import (
    EPOCH_MARGIN_SECONDS,
    LOGIN_TOKEN_LIFETIME_SECONDS,
    PASSWORD_EPOCH_TTL_SECONDS,
    REFRESH_GRACE_SECONDS,
)
from autobot_shared.user_management.user_service import UserService
from tests.security._credential_harness import PLATFORM_SECRET, real_middleware


class _Bound(UserService):
    user_model = MagicMock()


@pytest.fixture
def epochs():
    """The real epoch rule over an in-memory store."""
    store: dict[str, int] = {}

    async def get_epoch(subject):
        return store.get(subject)

    async def set_epoch(subject, *, now=None):
        store[subject] = int(time.time()) if now is None else now
        return store[subject]

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)
    yield store
    password_epoch.reset_epoch_store()


@pytest.fixture
def get_current_user(real_auth_middleware, monkeypatch):
    middleware = real_middleware(real_auth_middleware, enable_auth=True)
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(real_auth_middleware, "verify_internal_api_key", lambda _provided: False)
    return real_auth_middleware.get_current_user


def _user(**state):
    return SimpleNamespace(id=uuid.uuid4(), username="alice", is_active=True, deleted_at=None, **state)


def _service(user):
    session = MagicMock(flush=AsyncMock(), delete=AsyncMock())
    session.info = {POST_COMMIT_CALLBACKS: []}
    svc = _Bound(session, TenantContext())
    svc.get_user = AsyncMock(return_value=user)
    svc._audit_log = AsyncMock()
    svc._queue_membership_epoch_bumps = AsyncMock()  # #19670's subject, tested there
    return svc


async def _commit(service) -> None:
    """The commit succeeded: run what the session queued for after it."""
    await _run_post_commit_callbacks(service.session)


def _token_request(age_seconds: int = 60, username: str = "alice") -> Request:
    claims = {"username": username, "role": "user", "token_type": LOGIN_TOKEN_TYPE}
    claims["iat"] = int(time.time()) - age_seconds
    token = encode_jwt(claims, secret=PLATFORM_SECRET, expiry_hours=24)
    headers = [(b"authorization", f"Bearer {token}".encode())]
    scope = {"type": "http", "method": "GET", "path": "/api/chat", "query_string": b"", "headers": headers}
    return Request({**scope, "client": ("testclient", 5), "app": FastAPI()})


async def _assert_refused(get_current_user, request) -> HTTPException:
    with pytest.raises(HTTPException) as denied:
        await get_current_user(request)
    assert denied.value.status_code == 401
    return denied.value


@pytest.mark.asyncio
async def test_a_live_users_token_is_admitted(get_current_user, epochs):
    """The control: the refusals below come from the lifecycle change, not from the harness."""
    assert (await get_current_user(_token_request()))["username"] == "alice"


@pytest.mark.asyncio
async def test_a_deactivated_users_token_is_refused_once_the_change_commits(get_current_user, epochs):
    request = _token_request()
    service = _service(_user())
    await service.deactivate_user(uuid.uuid4())

    assert epochs == {}, "nothing is written before the commit"
    await _commit(service)
    await _assert_refused(get_current_user, request)


@pytest.mark.asyncio
async def test_a_soft_deleted_users_token_is_refused_once_the_change_commits(get_current_user, epochs):
    request = _token_request()
    service = _service(_user())
    await service.delete_user(uuid.uuid4(), hard_delete=False)
    await _commit(service)

    await _assert_refused(get_current_user, request)


@pytest.mark.asyncio
async def test_a_hard_deleted_users_token_is_refused_once_the_change_commits(get_current_user, epochs):
    request = _token_request()
    service = _service(_user())
    await service.delete_user(uuid.uuid4(), hard_delete=True)
    await _commit(service)

    await _assert_refused(get_current_user, request)


@pytest.mark.asyncio
async def test_a_token_minted_in_the_second_of_the_deactivation_is_refused_too(get_current_user, epochs):
    """``iat >= epoch`` would admit it: the deactivation epoch lies one second ahead (#20443)."""
    same_second = _token_request(age_seconds=0)
    service = _service(_user())
    await service.deactivate_user(uuid.uuid4())
    await _commit(service)

    await _assert_refused(get_current_user, same_second)


@pytest.mark.asyncio
async def test_another_users_token_is_untouched(get_current_user, epochs):
    service = _service(_user())
    await service.deactivate_user(uuid.uuid4())
    await _commit(service)

    assert (await get_current_user(_token_request(username="bob")))["username"] == "bob"


@pytest.mark.asyncio
async def test_reactivation_does_not_revive_the_old_token_but_a_new_login_works(get_current_user, epochs):
    """Recorded behaviour: the old token stays void; the user signs in again and the new token passes."""
    old = _token_request(age_seconds=60)
    service = _service(_user())
    await service.deactivate_user(uuid.uuid4())
    await _commit(service)
    await service.activate_user(uuid.uuid4())

    await _assert_refused(get_current_user, old)
    assert (await get_current_user(_token_request(age_seconds=-5)))["username"] == "alice"


@pytest.mark.asyncio
async def test_a_login_in_the_second_before_the_epoch_is_the_only_one_a_reactivation_refuses(get_current_user, epochs):
    """The cost of the one-second lead, measured: a login at the deactivation second fails, the next works."""
    service = _service(_user())
    await service.deactivate_user(uuid.uuid4())
    await _commit(service)
    epoch = epochs["alice"]

    await _assert_refused(get_current_user, _token_request(age_seconds=int(time.time()) - (epoch - 1)))
    assert (await get_current_user(_token_request(age_seconds=int(time.time()) - epoch)))["username"] == "alice"


@pytest.mark.asyncio
async def test_the_audit_row_says_the_revocation_is_queued_not_a_written_epoch(epochs):
    service = _service(_user())
    await service.deactivate_user(uuid.uuid4())

    details = service._audit_log.await_args.args[3]
    assert details == {"sessions_revocation": "queued_after_commit"}
    assert "sessions_revoked_from" not in details


class _FailingCommitSession:
    """What ``async_session_scope`` opens: commit raises, as a deferred constraint can."""

    def __init__(self):
        self.info = {}
        self.flush = AsyncMock()
        self.commit = AsyncMock(side_effect=RuntimeError("deferred constraint"))
        self.rollback = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["deactivate", "soft_delete"])
async def test_a_failed_commit_leaves_no_marker_on_the_user(epochs, method):
    session = _FailingCommitSession()
    with pytest.raises(RuntimeError):
        async with async_session_scope(lambda: session) as scoped:
            service = _Bound(scoped, TenantContext())
            service.get_user = AsyncMock(return_value=_user())
            service._audit_log = AsyncMock()
            if method == "deactivate":
                await service.deactivate_user(uuid.uuid4())
            else:
                await service.delete_user(uuid.uuid4(), hard_delete=False)

    assert epochs == {}


@pytest.mark.asyncio
async def test_a_store_that_raises_after_the_commit_surfaces_and_the_audit_row_stays_queued(monkeypatch):
    async def broken_set(_subject, *, now=None):
        raise ConnectionError("store down")

    password_epoch.use_epoch_store(get_epoch=AsyncMock(return_value=None), set_epoch=broken_set)
    try:
        service = _service(_user())
        await service.deactivate_user(uuid.uuid4())
        with pytest.raises(PostCommitCallbackError):
            await _commit(service)
    finally:
        password_epoch.reset_epoch_store()
    assert service._audit_log.await_args.args[3] == {"sessions_revocation": "queued_after_commit"}


@pytest.mark.asyncio
async def test_renaming_a_user_voids_the_tokens_that_carry_the_old_name(get_current_user, epochs):
    """Rename then deactivate used to miss them: the marker is keyed by the name the token carries."""
    old = _token_request(username="alice")
    user = _user()
    service = _service(user)
    service.get_user_by_username = AsyncMock(return_value=None)
    await service.update_user(uuid.uuid4(), username="alicia")
    await _commit(service)

    await _assert_refused(get_current_user, old)
    assert "alicia" not in epochs


# -- sessions (X-Session-ID) ---------------------------------------------------------------------


def _session_request(real_auth_middleware, created_at: str | None):
    from tests.security._credential_harness import SESSION_ID

    middleware = real_middleware(real_auth_middleware, enable_auth=True)
    stored = {"user_data": {"username": "alice", "role": "user"}}
    if created_at is not None:
        stored["created_at"] = created_at
    middleware.get_session = lambda _sid: dict(stored)
    scope = {"type": "http", "method": "GET", "path": "/x", "query_string": b"", "client": ("t", 1), "app": FastAPI()}
    scope["headers"] = [(b"x-session-id", SESSION_ID.encode())]
    return middleware, Request(scope)


def _iso(age_seconds: int) -> str:
    import datetime  # noqa: PLC0415

    return (datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(seconds=age_seconds)).isoformat()


@pytest.mark.asyncio
async def test_a_session_opened_before_the_deactivation_is_refused(real_auth_middleware, epochs):
    from auth_revocation import resolve_human_user_via  # noqa: PLC0415

    middleware, request = _session_request(real_auth_middleware, _iso(60))
    assert (await resolve_human_user_via(middleware, request))["username"] == "alice"

    service = _service(_user())
    await service.deactivate_user(uuid.uuid4())
    await _commit(service)

    with pytest.raises(HTTPException) as denied:
        await resolve_human_user_via(middleware, request)
    assert denied.value.status_code == 401


@pytest.mark.asyncio
async def test_a_session_opened_after_the_epoch_is_admitted(real_auth_middleware, epochs):
    from auth_revocation import resolve_human_user_via  # noqa: PLC0415

    epochs["alice"] = int(time.time()) - 30
    middleware, request = _session_request(real_auth_middleware, _iso(5))
    assert (await resolve_human_user_via(middleware, request))["username"] == "alice"


@pytest.mark.asyncio
async def test_a_session_with_no_readable_creation_time_is_refused(real_auth_middleware, epochs):
    from auth_revocation import resolve_human_user_via  # noqa: PLC0415

    middleware, request = _session_request(real_auth_middleware, None)
    assert await resolve_human_user_via(middleware, request) is None


# -- the marker outlives every token that could predate it ---------------------------------------


def test_the_marker_outlives_a_token_and_its_refresh_grace():
    """The TTL is derived from the lifetime, the grace and a margin, never a second literal."""
    assert PASSWORD_EPOCH_TTL_SECONDS == LOGIN_TOKEN_LIFETIME_SECONDS + REFRESH_GRACE_SECONDS + EPOCH_MARGIN_SECONDS
    assert PASSWORD_EPOCH_TTL_SECONDS > LOGIN_TOKEN_LIFETIME_SECONDS + REFRESH_GRACE_SECONDS


def test_the_middleware_and_the_refresh_use_the_constants_the_marker_is_derived_from(real_auth_middleware):
    import inspect  # noqa: PLC0415

    import auth_refresh  # noqa: PLC0415

    init = inspect.getsource(real_auth_middleware.AuthenticationMiddleware.__init__)
    assert "LOGIN_TOKEN_LIFETIME_SECONDS" in init
    assert "REFRESH_GRACE_SECONDS" in inspect.getsource(auth_refresh.decode_refresh_token)
