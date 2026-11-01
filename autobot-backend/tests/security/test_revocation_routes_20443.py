# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The deactivate and delete routes answer when the revocation marker could not be written (#20443, option B).

The REAL user and organisation routers, the real dependency chain (``get_current_user`` overridden to an
admin, then the real platform-admin gate, tenant context, ``get_db_session`` and ``async_session_scope``),
the real services, driven over ASGI. Before this change the marker was written in the dependency's
teardown, after the response: the caller got 200 whatever the store did. Only storage is stood in for: the
epoch store, and a fake session that answers by reading the statement it was given (so a ``deleted_at IS
NULL`` filter is honoured, which a retry of a soft delete depends on).
"""

import datetime
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

import user_management.database as umdb
from api.user_management import dependencies as deps
from api.user_management.organizations import router as org_router
from api.user_management.users import router as user_router
from autobot_shared import membership_epoch
from autobot_shared.auth.permissions import Role
from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.revocation_outcome import REVOCATION_INCOMPLETE_MESSAGE
from testkit.fake_async_session import FakeAsyncSession, FakeResult

ORG = uuid.uuid4()
MEMBERS = ("alice", "bob")
NOW = datetime.datetime.now(datetime.timezone.utc)


def _user(uid):
    return SimpleNamespace(
        id=uid, username="alice", email="a@x.io", display_name="A", bio=None, avatar_url=None, org_id=ORG,
        is_active=True, deleted_at=None, is_verified=True, mfa_enabled=False, is_platform_admin=False,
        preferences={}, roles=[], last_login_at=None, created_at=NOW, updated_at=NOW,
    )  # fmt: skip


def _org():
    return SimpleNamespace(
        id=ORG, name="Acme", slug="acme", description=None, settings={}, max_users=-1, is_active=True,
        deleted_at=None, created_at=NOW, updated_at=NOW,
    )  # fmt: skip


def _answer(user, org):
    """Answer the statements the routes issue, honouring the soft-delete filter like the database."""

    def answer(stmt):
        text = " ".join(str(stmt).split())
        if "FROM organizations" in text:
            return FakeResult([] if "deleted_at IS NULL" in text and org.deleted_at else [org])
        if text.startswith("SELECT users.username FROM users"):
            return FakeResult(list(MEMBERS))
        return FakeResult([] if "deleted_at IS NULL" in text and user.deleted_at else [user])

    return answer


class Store:
    """The epoch store: records writes, and fails them while ``down``."""

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


@pytest.fixture
def world(monkeypatch):
    """The user, the organisation, the session they live in, and a client onto the real routers."""
    user, org = _user(uuid.uuid4()), _org()
    session = FakeAsyncSession(default_result=_answer(user, org))
    session.info = {}
    monkeypatch.setattr(umdb, "get_async_session_factory", lambda: (lambda: session))
    app = FastAPI()
    app.include_router(user_router)
    app.include_router(org_router)
    admin = {"username": "root", "role": Role.ADMIN.value, "is_platform_admin": True}
    app.dependency_overrides[deps.get_current_user] = lambda: admin
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    client = httpx.AsyncClient(transport=transport, base_url="http://t")
    return SimpleNamespace(user=user, org=org, session=session, transport=transport, client=client)


def _reconnect(world):
    """A second request, as a retry would be: the first closed the client."""
    world.client = httpx.AsyncClient(transport=world.transport, base_url="http://t")


async def _post(world, path):
    async with world.client as client:
        return await client.post(path)


async def _delete(world, path):
    async with world.client as client:
        return await client.delete(path)


@pytest.mark.asyncio
async def test_user_deactivate_success_answers_200_and_writes_the_marker_once(world, store):
    response = await _post(world, f"/users/{world.user.id}/deactivate")

    assert response.status_code == 200 and response.json()["is_active"] is False
    assert store.tries == ["alice"], "written once: the scope's own exit does not run it again"


@pytest.mark.asyncio
async def test_user_deactivate_answers_503_when_the_marker_cannot_be_written_and_the_change_stands(world, store):
    store.down = True
    response = await _post(world, f"/users/{world.user.id}/deactivate")

    assert response.status_code == 503
    assert response.json() == {"detail": REVOCATION_INCOMPLETE_MESSAGE}
    assert "alice" not in response.text
    assert world.user.is_active is False and world.session.commits == 1
    assert store.tries == ["alice"] * password_epoch.MEMBERSHIP_EPOCH_BUMP_ATTEMPTS, "the retries ran once, not twice"


@pytest.mark.asyncio
async def test_repeating_a_user_deactivate_after_a_503_writes_the_marker(world, store):
    store.down = True
    assert (await _post(world, f"/users/{world.user.id}/deactivate")).status_code == 503
    store.down = False
    _reconnect(world)

    assert world.user.is_active is False, "the retry meets an already inactive user"
    assert (await _post(world, f"/users/{world.user.id}/deactivate")).status_code == 200
    assert "alice" in store.epochs


@pytest.mark.asyncio
async def test_a_failed_commit_writes_no_marker_and_is_not_reported_as_a_revocation_failure(world, store):
    world.session.commit_error = RuntimeError("deferred constraint")
    with pytest.raises(RuntimeError, match="deferred constraint"):
        await _post(world, f"/users/{world.user.id}/deactivate")

    assert store.tries == []


@pytest.mark.asyncio
async def test_user_soft_delete_503_then_the_repeat_finds_the_soft_deleted_user_and_writes_the_marker(world, store):
    store.down = True
    assert (await _delete(world, f"/users/{world.user.id}")).status_code == 503
    assert world.user.deleted_at is not None
    deleted_at = world.user.deleted_at
    store.down = False
    _reconnect(world)

    assert (await _delete(world, f"/users/{world.user.id}")).status_code == 200
    assert "alice" in store.epochs and world.user.deleted_at == deleted_at, "the first deletion time is kept"


@pytest.mark.asyncio
async def test_org_deactivate_success_marks_every_member_and_answers_200(world, store):
    response = await _post(world, f"/organizations/{ORG}/deactivate")

    assert response.status_code == 200 and response.json()["is_active"] is False
    assert set(store.epochs) == set(MEMBERS)


@pytest.mark.asyncio
async def test_org_deactivate_answers_503_when_markers_fail_the_org_stays_deactivated_and_a_repeat_retries(
    world, store
):
    store.down = True
    response = await _post(world, f"/organizations/{ORG}/deactivate")

    assert response.status_code == 503 and response.json() == {"detail": REVOCATION_INCOMPLETE_MESSAGE}
    assert world.org.is_active is False and world.session.commits == 1
    assert not any(name in response.text for name in MEMBERS)
    store.down = False
    _reconnect(world)

    assert (await _post(world, f"/organizations/{ORG}/deactivate")).status_code == 200
    assert set(store.epochs) == set(MEMBERS)


@pytest.mark.asyncio
async def test_org_soft_delete_repeat_finds_the_soft_deleted_organisation(world, store):
    store.down = True
    assert (await _delete(world, f"/organizations/{ORG}")).status_code == 503
    assert world.org.deleted_at is not None
    store.down = False
    _reconnect(world)

    assert (await _delete(world, f"/organizations/{ORG}")).status_code == 200
    assert set(store.epochs) == set(MEMBERS)


@pytest.mark.asyncio
async def test_a_failed_org_commit_writes_no_markers(world, store):
    world.session.commit_error = RuntimeError("deferred constraint")
    with pytest.raises(RuntimeError, match="deferred constraint"):
        await _post(world, f"/organizations/{ORG}/deactivate")

    assert store.tries == []


@pytest.mark.asyncio
async def test_the_other_callbacks_on_the_session_still_run_when_the_markers_fail(world, store, monkeypatch):
    bumped = []
    monkeypatch.setattr(membership_epoch, "_bump_once", AsyncMock(side_effect=lambda org_id: bumped.append(org_id)))
    store.down = True
    response = await _delete(world, f"/organizations/{ORG}?hard_delete=true")

    assert response.status_code == 503
    assert bumped == [ORG], "the membership bump ran although the markers failed"
