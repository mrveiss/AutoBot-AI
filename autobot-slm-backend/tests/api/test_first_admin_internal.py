# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10200: the first admin, password hash included, goes only to a holder of the internal key."""

import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

_SPEC = importlib.util.spec_from_file_location(
    "_first_admin_internal", Path(__file__).parents[2] / "api" / "first_admin_internal.py"
)
route = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(route)


@pytest.fixture(autouse=True)
def _not_the_last_admin():
    """These tests are about the push, not the last-admin guard (tested below and in #21018's own file)."""
    with patch.object(route, "ensure_not_last_platform_admin", AsyncMock()):
        yield


def _session(admin):
    found = MagicMock()
    found.scalars.return_value.first.return_value = admin
    return SimpleNamespace(execute=AsyncMock(return_value=found))


async def _get(admin, key_ok=True):
    with patch.object(route, "verify_internal_api_key", return_value=key_ok):
        return await route.get_first_admin(_session(admin), "key")


@pytest.mark.asyncio
async def test_without_the_internal_key_nothing_is_read():
    session = _session("admin")
    with patch.object(route, "verify_internal_api_key", return_value=False), pytest.raises(HTTPException) as refused:
        await route.get_first_admin(session, None)
    assert refused.value.status_code == 403
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_key_holder_gets_the_admin():
    assert await _get("admin") == "admin"


@pytest.mark.asyncio
async def test_an_slm_without_an_admin_says_so():
    with pytest.raises(HTTPException) as missing:
        await _get(None)
    assert missing.value.status_code == 404


def _copy_body(is_active=False):
    return route.PersonCopyRequest(slm_user_id=uuid.uuid4(), password_hash="new", is_active=is_active)


@pytest.mark.asyncio
async def test_a_person_copy_needs_the_internal_key():
    session = SimpleNamespace(get=AsyncMock(), commit=AsyncMock())
    with patch.object(route, "verify_internal_api_key", return_value=False), pytest.raises(HTTPException) as refused:
        await route.update_person_copy(_copy_body(), session, None)
    assert refused.value.status_code == 403
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_person_copy_updates_password_and_deactivates():
    user = SimpleNamespace(username="alice", password_hash="old", is_active=True)
    session = SimpleNamespace(get=AsyncMock(return_value=user), commit=AsyncMock())
    with (
        patch.object(route, "verify_internal_api_key", return_value=True),
        patch.object(route, "record_password_epoch", AsyncMock()) as revoke,
    ):
        await route.update_person_copy(_copy_body(), session, "key")
    assert (user.password_hash, user.is_active) == ("new", False)
    revoke.assert_awaited_once_with("alice", lead_seconds=route.DEACTIVATION_EPOCH_LEAD_SECONDS)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_person_copy_for_nobody_is_a_404():
    session = SimpleNamespace(get=AsyncMock(return_value=None), commit=AsyncMock())
    with patch.object(route, "verify_internal_api_key", return_value=True), pytest.raises(HTTPException) as missing:
        await route.update_person_copy(_copy_body(), session, "key")
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_no_hash_never_wipes_the_password_but_still_deactivates():
    user = SimpleNamespace(username="alice", password_hash="old", is_active=True)
    session = SimpleNamespace(get=AsyncMock(return_value=user), commit=AsyncMock())
    body = route.PersonCopyRequest(slm_user_id=uuid.uuid4(), password_hash=None, is_active=False)
    with (
        patch.object(route, "verify_internal_api_key", return_value=True),
        patch.object(route, "record_password_epoch", AsyncMock()),
    ):
        await route.update_person_copy(body, session, "key")
    assert (user.password_hash, user.is_active) == ("old", False)


# The route is mounted on the unauthenticated health router (api/__init__.py), so the handler's own
# internal-key check is the ONLY gate. These drive the real route over HTTP with the real
# `verify_internal_api_key`: only the key's expected value is set, and no user auth can substitute.
_KEY = "internal-key-for-test"


def _client(admin):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(route.router, prefix="/api")

    async def _session_override():
        return _session(admin)

    app.dependency_overrides[route.get_slm_session] = _session_override
    return TestClient(app)


@pytest.fixture
def key_configured():
    with patch("autobot_shared.auth.internal_api_key.node_proxy.internal_api_key", return_value=_KEY):
        yield


def test_over_http_no_key_is_refused(key_configured):
    admin = SimpleNamespace()
    response = _client(admin).get("/api/internal/first-admin")
    assert response.status_code == 403
    assert "password_hash" not in response.text


def test_over_http_a_user_token_without_the_key_is_refused(key_configured):
    response = _client(SimpleNamespace()).get(
        "/api/internal/first-admin", headers={"Authorization": "Bearer an-admin-session-token"}
    )
    assert response.status_code == 403
    assert "password_hash" not in response.text


def test_over_http_a_wrong_key_is_refused(key_configured):
    response = _client(SimpleNamespace()).get("/api/internal/first-admin", headers={"X-Internal-API-Key": "nope"})
    assert response.status_code == 403


def test_over_http_the_valid_key_gets_the_admin(key_configured):
    import uuid

    admin = SimpleNamespace(
        id=uuid.uuid4(), username="root", email="r@example.test", display_name=None, password_hash="h"
    )
    response = _client(admin).get("/api/internal/first-admin", headers={"X-Internal-API-Key": _KEY})
    assert response.status_code == 200
    assert response.json()["password_hash"] == "h"


@pytest.mark.asyncio
async def test_a_person_copy_cannot_deactivate_the_only_active_admin():
    """#21018: refused with the stable code, before the epoch write, so nothing changes."""
    from autobot_shared.user_management.last_platform_admin import LAST_PLATFORM_ADMIN_CODE, LastPlatformAdminError

    user = SimpleNamespace(id=uuid.uuid4(), username="alice", password_hash="old", is_active=True)
    session = SimpleNamespace(get=AsyncMock(return_value=user), commit=AsyncMock())
    with (
        patch.object(route, "verify_internal_api_key", return_value=True),
        patch.object(route, "ensure_not_last_platform_admin", AsyncMock(side_effect=LastPlatformAdminError())),
        patch.object(route, "record_password_epoch", AsyncMock()) as revoke,
        pytest.raises(HTTPException) as refused,
    ):
        await route.update_person_copy(_copy_body(is_active=False), session, "key")

    assert refused.value.status_code == 409 and refused.value.detail["code"] == LAST_PLATFORM_ADMIN_CODE
    revoke.assert_not_awaited()
    assert user.is_active is True
