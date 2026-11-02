# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared by the #20443 revocation tests: an in-memory epoch store and a real signed login token.

The token goes through the REAL ``AuthenticationMiddleware`` extraction, the real ``get_current_user``
and the real shared epoch check; only the epoch store is in memory.
"""

import time

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from autobot_shared.auth.interactive_principal import LOGIN_TOKEN_TYPE
from autobot_shared.auth.jwt_core import encode_jwt
from autobot_shared.auth.permissions import Role
from autobot_shared.user_management import password_epoch
from tests.security._credential_harness import PLATFORM_SECRET, real_middleware


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


def token_request(age_seconds: int = 60, username: str = "alice") -> Request:
    claims = {"username": username, "role": Role.USER.value, "token_type": LOGIN_TOKEN_TYPE}
    claims["iat"] = int(time.time()) - age_seconds
    token = encode_jwt(claims, secret=PLATFORM_SECRET, expiry_hours=24)
    headers = [(b"authorization", f"Bearer {token}".encode())]
    scope = {"type": "http", "method": "GET", "path": "/api/chat", "query_string": b"", "headers": headers}
    return Request({**scope, "client": ("testclient", 5), "app": FastAPI()})


async def assert_refused(get_current_user, request) -> HTTPException:
    with pytest.raises(HTTPException) as denied:
        await get_current_user(request)
    assert denied.value.status_code == 401
    return denied.value
