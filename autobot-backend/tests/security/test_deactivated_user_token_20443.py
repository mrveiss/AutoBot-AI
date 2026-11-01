# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A deactivated or soft-deleted user's already-issued token is refused on its next request (#20443).

A real signed login token goes through the REAL ``AuthenticationMiddleware`` extraction, the real
``get_current_user`` and the real shared epoch check; the user is deactivated or deleted through
the real shared ``UserService``. Only storage is stood in for: the epoch store (in memory) and the
database session.
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
from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.base_service import TenantContext
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
    return SimpleNamespace(username="alice", is_active=True, deleted_at=None, **state)


def _service(user):
    svc = _Bound(MagicMock(flush=AsyncMock(), delete=AsyncMock()), TenantContext())
    svc.get_user = AsyncMock(return_value=user)
    svc._audit_log = AsyncMock()
    return svc


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
async def test_a_deactivated_users_token_is_refused_on_its_next_request(get_current_user, epochs):
    request = _token_request()
    assert (await get_current_user(request))["username"] == "alice"

    await _service(_user()).deactivate_user(uuid.uuid4())

    await _assert_refused(get_current_user, request)


@pytest.mark.asyncio
async def test_a_soft_deleted_users_token_is_refused_on_its_next_request(get_current_user, epochs):
    request = _token_request()
    await _service(_user()).delete_user(uuid.uuid4(), hard_delete=False)

    await _assert_refused(get_current_user, request)


@pytest.mark.asyncio
async def test_a_hard_deleted_users_token_is_refused_on_its_next_request(get_current_user, epochs):
    request = _token_request()
    await _service(_user()).delete_user(uuid.uuid4(), hard_delete=True)

    await _assert_refused(get_current_user, request)


@pytest.mark.asyncio
async def test_another_users_token_is_untouched(get_current_user, epochs):
    await _service(_user()).deactivate_user(uuid.uuid4())

    assert (await get_current_user(_token_request(username="bob")))["username"] == "bob"


@pytest.mark.asyncio
async def test_reactivation_does_not_revive_the_old_token_but_a_new_login_works(get_current_user, epochs):
    """Recorded behaviour: the old token stays void; the user signs in again and the new token passes."""
    old = _token_request(age_seconds=60)
    service = _service(_user())
    await service.deactivate_user(uuid.uuid4())
    await service.activate_user(uuid.uuid4())

    await _assert_refused(get_current_user, old)
    assert (await get_current_user(_token_request(age_seconds=-5)))["username"] == "alice"


@pytest.mark.asyncio
async def test_the_audit_row_records_the_epoch_it_wrote(epochs):
    service = _service(_user())
    await service.deactivate_user(uuid.uuid4())

    details = service._audit_log.await_args.args[3]
    assert details["sessions_revoked_from"] == epochs["alice"]
