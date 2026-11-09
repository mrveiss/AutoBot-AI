# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin status is changed in one place, and the change reaches the next request (#20670).

``is_platform_admin`` alone decides a login token's ``role``. Nothing used to write it after the
account was created, and the role routes (``UserRole`` rows) never reached it. These tests drive
the real ``UserService.set_platform_admin``, the real ``commit_or_503`` and the real epoch check
against a real signed token through the real ``get_current_user``; only the epoch store (in
memory) and the database session are stood in for.
"""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.schemas_admin_status import AdminStatusRequest
from api.user_management.admin_status import set_admin_status
from api.user_management.dependencies import get_current_user as route_get_current_user
from api.user_management.router import router as user_management_router
from autobot_shared.db_session import POST_COMMIT_CALLBACKS
from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.base_service import TenantContext
from autobot_shared.user_management.models.audit import AuditResourceType, IdentityAuditAction
from autobot_shared.user_management.user_service import UserService
from tests.security._credential_harness import real_middleware
from tests.security._revocation_harness import assert_refused as _assert_refused
from tests.security._revocation_harness import token_request as _token_request


class _Bound(UserService):
    user_model = MagicMock()


def _user(is_admin: bool):
    return SimpleNamespace(
        id=uuid.uuid4(), username="alice", is_active=True, deleted_at=None, is_platform_admin=is_admin
    )


def _service(user, audits=None):
    """A service over a session whose audit table is *audits*: the rows the committed changes wrote."""
    audits = [] if audits is None else audits

    async def write_audit(action, _resource_type, _resource_id, details, _outcome="success") -> None:
        audits.append(SimpleNamespace(action=action, details=details))

    async def read_latest(_statement) -> SimpleNamespace:
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [a.details for a in audits]))

    session = MagicMock(flush=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock(), execute=read_latest)
    session.info = {POST_COMMIT_CALLBACKS: []}
    svc = _Bound(session, TenantContext())
    svc.get_user = AsyncMock(return_value=user)
    svc._audit_log = AsyncMock(side_effect=write_audit)
    svc._guard_last_admin = AsyncMock()  # the last-admin guard has its own tests (#21018)
    svc._guard_demotion_before_target_lock = AsyncMock()  # ... and so does its lock order
    return svc


async def _change(service, is_admin: bool):
    """The route body: change, then commit (which runs the queued revocation)."""
    return await set_admin_status(uuid.uuid4(), AdminStatusRequest(is_platform_admin=is_admin), service)


@pytest.mark.asyncio
async def test_an_admins_token_is_admitted_before_any_change(get_current_user, epochs):
    """The control: the refusals below come from the change, not from the harness."""
    claims = await get_current_user(_token_request(role="admin"))
    assert claims["username"] == "alice"


@pytest.mark.asyncio
async def test_revoking_admin_voids_the_old_admin_token_on_the_next_request(get_current_user, epochs):
    old = _token_request(role="admin")
    user = _user(True)
    result = await _change(_service(user), False)

    assert user.is_platform_admin is False and result.changed is True
    await _assert_refused(get_current_user, old)


@pytest.mark.asyncio
async def test_a_token_minted_in_the_second_of_the_demotion_is_void_too(get_current_user, epochs):
    same_second = _token_request(age_seconds=0, role="admin")
    await _change(_service(_user(True)), False)

    await _assert_refused(get_current_user, same_second)


@pytest.mark.asyncio
async def test_another_admins_token_is_untouched(get_current_user, epochs):
    await _change(_service(_user(True)), False)

    assert (await get_current_user(_token_request(username="bob", role="admin")))["username"] == "bob"


@pytest.mark.asyncio
async def test_granting_admin_voids_the_old_token_so_the_next_login_carries_admin(get_current_user, epochs):
    old = _token_request(role="user")
    user = _user(False)
    result = await _change(_service(user), True)

    assert user.is_platform_admin is True and result.changed is True
    await _assert_refused(get_current_user, old)
    issued_role = UserService.account_role(user)  # the one derivation login uses for the token's role
    assert issued_role == "admin"
    assert (await get_current_user(_token_request(age_seconds=-5, role=issued_role)))["username"] == "alice"


def _rs256_middleware(real_auth_middleware):
    """The real middleware with a throwaway RS256 pair, so the real ``create_jwt_token`` signs."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = serialization.Encoding.PEM
    middleware = real_middleware(real_auth_middleware, enable_auth=True)
    middleware.jwt_private_key = key.private_bytes(
        pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    middleware.jwt_public_key = (
        key.public_key().public_bytes(pem, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    )
    middleware.jwt_kid, middleware.jwt_expiry_hours = "test-kid", 24
    middleware.is_account_locked = lambda _username: False
    return middleware


@pytest.mark.asyncio
async def test_the_real_login_after_a_promotion_issues_an_admin_token_that_survives_the_epoch(
    real_auth_middleware, epochs, monkeypatch
):
    """Drives ``_authenticate_and_build_user_data`` (the login helper), not ``account_role`` alone."""
    from api import auth as auth_api

    user = _user(False)
    stale = {"username": "alice", "role": "user", "iat": int(time.time()) - 60}  # minted before the promotion
    await _change(_service(user), True)
    monkeypatch.setattr(auth_api, "db_session_context", MagicMock())
    monkeypatch.setattr(auth_api.UserService, "authenticate", AsyncMock(return_value=user))
    user.last_login_at, user.org_id, user.email = None, None, "alice@example.invalid"

    user_data = await auth_api._authenticate_and_build_user_data("alice", "pw", "203.0.113.1")
    middleware = _rs256_middleware(real_auth_middleware)
    claims = middleware.verify_jwt_token(middleware.create_jwt_token(user_data))

    assert claims["role"] == "admin" and claims["username"] == "alice"
    assert await password_epoch.is_token_revoked_by_password_change(claims) is False
    assert await password_epoch.is_token_revoked_by_password_change(stale) is True


@pytest.mark.asyncio
async def test_setting_the_status_it_already_has_changes_nothing(get_current_user, epochs):
    service = _service(_user(True))
    result = await _change(service, True)

    assert result.changed is False and result.sessions_revoked is False
    assert epochs == {}
    service._audit_log.assert_not_awaited()
    assert (await get_current_user(_token_request(role="admin")))["username"] == "alice"


@pytest.mark.asyncio
@pytest.mark.parametrize("is_admin", [True, False])
async def test_the_change_is_audited_with_before_and_after(epochs, is_admin):
    user = _user(not is_admin)
    service = _service(user)
    await _change(service, is_admin)

    action, resource_type, resource_id, details = service._audit_log.await_args.args
    assert action == IdentityAuditAction.PLATFORM_ADMIN_CHANGED
    assert resource_type == AuditResourceType.USER
    assert {k: details[k] for k in ("from", "to", "revision", "sessions_revocation")} == {
        "from": not is_admin,
        "to": is_admin,
        "revision": 1,
        "sessions_revocation": "queued_after_commit",
    }
    assert isinstance(details["recorded_at"], int)


@pytest.mark.asyncio
async def test_an_unknown_user_is_a_404_and_revokes_nothing(epochs):
    service = _service(None)
    with pytest.raises(HTTPException) as missing:
        await _change(service, True)
    assert missing.value.status_code == 404
    assert epochs == {}


@pytest.mark.asyncio
async def test_a_store_that_cannot_record_is_a_503_and_the_change_stays_committed(monkeypatch):
    """Redis down: the caller is told the sessions may not have been revoked (fail mode)."""
    monkeypatch.setattr(password_epoch, "MEMBERSHIP_EPOCH_BUMP_BACKOFF_SECONDS", 0.0)
    password_epoch.use_epoch_store(get_epoch=AsyncMock(return_value=None), set_epoch=AsyncMock(return_value=None))
    try:
        user = _user(True)
        with pytest.raises(HTTPException) as failed:
            await _change(_service(user), False)
    finally:
        password_epoch.reset_epoch_store()
    assert failed.value.status_code == 503
    assert user.is_platform_admin is False, "the demotion is not rolled back"


def test_a_non_admin_cannot_change_admin_status_and_no_session_is_reached():
    """Through the real route gate: a user-role caller is refused 403 before any service runs."""
    app = FastAPI()
    app.include_router(user_management_router)
    app.dependency_overrides[route_get_current_user] = lambda: {"username": "mallory", "role": "user"}
    response = TestClient(app).put(f"/user-management/users/{uuid.uuid4()}/admin", json={"is_platform_admin": True})

    assert response.status_code == 403


def _restore_epoch_store(store: dict) -> None:
    """Put the in-memory store the ``epochs`` fixture installed back ("the store is back").

    ``reset_epoch_store`` would fall through to the default Redis store, which a CI runner does not have.
    """

    async def get_epoch(subject):
        return store.get(subject)

    async def set_epoch(subject, *, now=None):
        store[subject] = int(time.time()) if now is None else now
        return store[subject]

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)


@pytest.mark.asyncio
async def test_repeating_a_demotion_after_a_503_finishes_the_revocation(get_current_user, epochs, monkeypatch):
    """The 503 contract: the flag committed, the marker did not; the repeat must revoke, not answer all-clear."""
    monkeypatch.setattr(password_epoch, "MEMBERSHIP_EPOCH_BUMP_BACKOFF_SECONDS", 0.0)
    old = _token_request(role="admin")
    user, audits = _user(True), []
    password_epoch.use_epoch_store(get_epoch=AsyncMock(return_value=None), set_epoch=AsyncMock(return_value=None))
    try:
        with pytest.raises(HTTPException) as failed:
            await _change(_service(user, audits), False)
    finally:
        _restore_epoch_store(epochs)
    assert failed.value.status_code == 503 and user.is_platform_admin is False
    assert epochs == {}

    retry = await _change(_service(user, audits), False)  # the store is back
    assert retry.changed is False and retry.sessions_revoked is True
    await _assert_refused(get_current_user, old)


@pytest.mark.asyncio
async def test_repeating_a_completed_demotion_signs_nobody_out(get_current_user, epochs):
    """Counter-test: the revocation is confirmed, so a no-op demotion writes no epoch."""
    user, audits = _user(True), []
    await _change(_service(user, audits), False)
    marker = dict(epochs)
    fresh = _token_request(age_seconds=-5, role="user")

    repeat = await _change(_service(user, audits), False)

    assert repeat.changed is False and repeat.sessions_revoked is False
    assert epochs == marker, "no second epoch write"
    assert (await get_current_user(fresh))["username"] == "alice"


@pytest.mark.asyncio
async def test_demoting_a_user_who_was_never_an_admin_signs_nobody_out(get_current_user, epochs):
    """Control: no recorded admin change, so nothing is pending and nothing is revoked."""
    result = await _change(_service(_user(False), []), False)

    assert result.changed is False and result.sessions_revoked is False and epochs == {}
    assert (await get_current_user(_token_request(role="user")))["username"] == "alice"


@pytest.mark.asyncio
async def test_a_store_that_cannot_answer_the_pending_check_is_a_503(epochs):
    user, audits = _user(True), []
    await _change(_service(user, audits), False)
    password_epoch.use_epoch_store(
        get_epoch=AsyncMock(side_effect=password_epoch.RevocationCheckUnavailable("down")), set_epoch=AsyncMock()
    )
    try:
        with pytest.raises(HTTPException) as failed:
            await _change(_service(user, audits), False)
    finally:
        password_epoch.reset_epoch_store()
    assert failed.value.status_code == 503


@pytest.mark.asyncio
async def test_repeating_a_grant_queues_no_revocation(get_current_user, epochs):
    """The admin target's same-value path is unchanged: no marker, no audit."""
    service = _service(_user(True))
    result = await _change(service, True)

    assert result.changed is False and epochs == {}
    service._audit_log.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_row_is_locked_for_the_read_modify_write(epochs):
    service = _service(_user(True))
    await _change(service, False)

    assert service.session.refresh.await_args.kwargs == {"with_for_update": True}
