# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SCIM deprovisioning answers when the revocation marker could not be written (#20443, option B).

The REAL SCIM router and the real shared ``UserService`` logic, driven over ASGI with the real
``async_session_scope`` as the session dependency. Before this change the marker was written in the
dependency's teardown, after the response, so the IdP was told 200/204 whatever the store did. Only
storage is stood in for: the epoch store, the session, and the user lookup (this package stubs the ORM, so
the lookup is a small override that honours ``include_deleted`` as the database filter does).
"""

import datetime
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from autobot_shared.db_session import async_session_scope
from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.revocation_outcome import REVOCATION_INCOMPLETE_MESSAGE
from testkit.fake_async_session import FakeAsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_orm_import import import_modules_with_real_orm  # noqa: E402

scim, base_service, user_service = import_modules_with_real_orm(
    ("api.scim", "autobot_shared.user_management.base_service", "autobot_shared.user_management.user_service")
)
TenantContext, UserService = base_service.TenantContext, user_service.UserService
from fastapi import FastAPI  # noqa: E402

#: The package guard replaces ``httpx.AsyncClient`` while a test runs (it refuses a live health poll). This test
#: talks to an in-process ASGI app, not the network, so it keeps the class as it stood at import.
_AsyncClient = httpx.AsyncClient

NOW = datetime.datetime.now(datetime.timezone.utc)


def _user(active=True):
    return SimpleNamespace(
        id=uuid.uuid4(), username="alice", email="a@x.io", display_name="A", full_name="A B", is_active=active,
        deleted_at=None, scim_external_id=None, created_at=NOW, updated_at=NOW,
    )  # fmt: skip


class Store:
    def __init__(self):
        self.epochs, self.tries, self.down = {}, [], False

    async def get_epoch(self, subject):
        return self.epochs.get(subject)

    async def set_epoch(self, subject, *, now=None):
        self.tries.append(subject)
        if self.down:
            raise ConnectionError("store down")
        self.epochs[subject] = now or int(time.time())
        return self.epochs[subject]


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(password_epoch, "MEMBERSHIP_EPOCH_BUMP_BACKOFF_SECONDS", 0.0)
    store = Store()
    password_epoch.use_epoch_store(get_epoch=store.get_epoch, set_epoch=store.set_epoch)
    yield store
    password_epoch.reset_epoch_store()


def _client(user, monkeypatch):
    class Service(UserService):
        user_model = SimpleNamespace()

        async def get_user(self, user_id, *, include_deleted=False):
            return None if user.deleted_at and not include_deleted else user

        async def _audit_log(self, *args, **kwargs):
            return None

    monkeypatch.setattr(scim, "UserService", Service)
    monkeypatch.setattr(scim, "TenantContext", TenantContext)
    session = FakeAsyncSession()
    session.info = {}

    async def db():
        async with async_session_scope(lambda: session) as scoped:
            yield scoped

    app = FastAPI()
    app.include_router(scim.router)
    app.dependency_overrides[scim._get_slm_db] = db
    app.dependency_overrides[scim._require_scim_bearer] = lambda: None
    return session, httpx.ASGITransport(app=app, raise_app_exceptions=True)


def _patch_inactive():
    return {"Operations": [{"op": "replace", "path": "active", "value": False}]}


async def _call(transport, method, path, **kwargs):
    async with _AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_deprovisioning_answers_200_and_writes_the_marker_once(store, monkeypatch):
    user = _user()
    _session, transport = _client(user, monkeypatch)
    response = await _call(transport, "PATCH", f"/scim/v2/Users/{user.id}", json=_patch_inactive())

    assert response.status_code == 200 and user.is_active is False
    assert store.tries == ["alice"]


@pytest.mark.asyncio
async def test_deprovisioning_answers_a_scim_503_when_the_marker_fails_and_the_change_stands(store, monkeypatch):
    user = _user()
    session, transport = _client(user, monkeypatch)
    store.down = True
    response = await _call(transport, "PATCH", f"/scim/v2/Users/{user.id}", json=_patch_inactive())

    assert response.status_code == 503
    # The module's own error shape: the SCIM body sits under ``detail`` (as for its 401 and 409), with no scimType.
    assert response.json() == {
        "detail": {"schemas": [scim._SCIM_ERROR_SCHEMA], "detail": REVOCATION_INCOMPLETE_MESSAGE, "status": "503"}
    }
    assert user.is_active is False and session.commits == 1
    assert store.tries == ["alice"] * password_epoch.MEMBERSHIP_EPOCH_BUMP_ATTEMPTS, "run once, not again at scope exit"


@pytest.mark.asyncio
async def test_repeating_the_request_for_an_already_inactive_user_writes_the_marker(store, monkeypatch):
    user = _user()
    _session, transport = _client(user, monkeypatch)
    store.down = True
    assert (await _call(transport, "PATCH", f"/scim/v2/Users/{user.id}", json=_patch_inactive())).status_code == 503
    store.down = False

    assert user.is_active is False, "the repeat meets an already inactive user"
    assert (await _call(transport, "PATCH", f"/scim/v2/Users/{user.id}", json=_patch_inactive())).status_code == 200
    assert "alice" in store.epochs


@pytest.mark.asyncio
async def test_a_failed_commit_writes_no_marker(store, monkeypatch):
    user = _user()
    session, transport = _client(user, monkeypatch)
    session.commit_error = RuntimeError("deferred constraint")
    with pytest.raises(RuntimeError, match="deferred constraint"):
        await _call(transport, "PATCH", f"/scim/v2/Users/{user.id}", json=_patch_inactive())

    assert store.tries == []


@pytest.mark.asyncio
async def test_delete_answers_503_then_a_repeat_finds_the_soft_deleted_user(store, monkeypatch):
    user = _user()
    _session, transport = _client(user, monkeypatch)
    store.down = True
    assert (await _call(transport, "DELETE", f"/scim/v2/Users/{user.id}")).status_code == 503
    assert user.deleted_at is not None
    store.down = False

    assert (await _call(transport, "DELETE", f"/scim/v2/Users/{user.id}")).status_code == 204
    assert "alice" in store.epochs
