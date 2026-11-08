# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21039: a dependent registered while a secret delete is in flight is refused, never cascaded.

The dependents check and the delete used to be separate statements. Now every vault-secret delete
route calls ``secrets_guarded_delete.guarded_delete``, which takes the secret row ``FOR UPDATE``
first and lists dependents under it. The seam injected here is the lock: a registration that
commits just before the lock is granted (the window the old check-then-delete lost) must be in
the listing that follows, so the delete answers the same 409 as the main route and the audit trail
records the refusal. The row lock against a real Postgres is proved in
``tests/migrations/test_secret_delete_race_21039.py``.
"""

# flake8: noqa: F811 -- pytest fixtures imported by name are re-requested as parameters

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from api import envelope_secrets_delete_20640_test as env
from api import secrets as secrets_module
from api import secrets_guarded_delete
from api.envelope_secrets_delete_20640_test import _client, _Coordinator, _trail, store  # noqa: F401 -- fixture
from api.secrets_defects_20557_test import _VAULT_KEY, _outcome
from api.secrets_defects_20557_test import _trail as _main_trail
from api.secrets_defects_20557_test import _with_dependents
from api.secrets_system_vault_17731_test import _SECRET_ID, client_and_vault  # noqa: F401 -- fixture
from testkit.fake_async_session import FakeAsyncSession, FakeResult

_LATE = SimpleNamespace(dependent_kind="agent", dependent_id="registered-in-the-window")
_LISTED = [{"dependent_kind": "agent", "dependent_id": "registered-in-the-window"}]


def _register_when_locked(monkeypatch, events: list, register) -> None:
    """The seam: the dependent is registered as the row lock is granted, after the route began."""

    async def lock(session, secret_id) -> None:
        events.append("lock")
        register()

    monkeypatch.setattr(secrets_guarded_delete, "lock_secret_row", lock)


# --- main route -------------------------------------------------------------------------------


def test_main_route_refuses_a_dependent_registered_in_the_window(client_and_vault, monkeypatch) -> None:  # noqa: F811
    client, vault = _with_dependents(client_and_vault, monkeypatch, [])
    ops, events = _main_trail(monkeypatch), []
    _register_when_locked(monkeypatch, events, lambda: vault.dependents.append(("agent", "registered-in-the-window")))

    response = client.delete(f"/api/secrets/{_SECRET_ID}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "secret_has_dependents"
    assert response.json()["detail"]["dependents"] == _LISTED
    assert _VAULT_KEY in vault.store, "the secret must still be stored"
    assert _outcome(ops) == ("denied", {"reason": "has_dependents"})
    assert events == ["lock"]


def test_main_route_without_dependents_still_deletes_under_the_lock(
    client_and_vault, monkeypatch
) -> None:  # noqa: F811
    client, vault = _with_dependents(client_and_vault, monkeypatch, [])
    events: list = []
    _register_when_locked(monkeypatch, events, lambda: None)

    assert client.delete(f"/api/secrets/{_SECRET_ID}").status_code == 200

    assert _VAULT_KEY not in vault.store
    assert events == ["lock"]


# --- envelope user and service routes -----------------------------------------------------------


def test_envelope_routes_refuse_a_dependent_registered_in_the_window(
    env_route, store, monkeypatch
) -> None:  # noqa: F811
    _, url = env_route
    coordinator, events = _Coordinator(), []
    _register_when_locked(monkeypatch, events, lambda: coordinator.dependents.append(_LATE))

    response, client = env._run(coordinator, url, store)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "secret_has_dependents",
        "message": "Dependents use this secret",
        "dependents": _LISTED,
    }
    assert coordinator.vault == {env._SECRET}, "the secret must still be stored"
    assert client.session.commits == 0
    assert _trail(store) == [("attempted", "before_write"), ("denied", "has_dependents")]
    assert events == ["lock"]


def test_envelope_routes_without_dependents_still_delete_under_the_lock(
    env_route, store, monkeypatch
) -> None:  # noqa: F811
    _, url = env_route
    coordinator, events = _Coordinator(), []
    _register_when_locked(monkeypatch, events, lambda: None)

    response, _ = env._run(coordinator, url, store)

    assert response.status_code == 204
    assert coordinator.vault == set()
    assert events == ["lock"]
    assert _trail(store) == [("attempted", "before_write"), ("success", "completed")]


def test_a_confirmed_user_delete_still_takes_the_lock(store, monkeypatch) -> None:  # noqa: F811
    coordinator, events = _Coordinator([env._DEPENDENTS[0]]), []
    _register_when_locked(monkeypatch, events, lambda: None)

    response, _ = env._run(coordinator, "/api/v2/secrets/" + env._SECRET, store, "?confirm_dependents=true")

    assert response.status_code == 204
    assert events == ["lock"]


@pytest.fixture(params=["user", "service"])
def env_route(request):
    return request.param, ("/api/v2/secrets/" if request.param == "user" else "/api/v2/secrets/system/") + env._SECRET


# --- the guard itself ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_lock_precedes_the_listing_which_precedes_the_delete() -> None:
    events: list = []
    session = FakeAsyncSession()

    async def dependents() -> list:
        events.append("list")
        return []

    async def delete() -> None:
        events.append("delete")

    await secrets_guarded_delete.guarded_delete(session, uuid.uuid4(), dependents=dependents, delete=delete)

    assert events == ["list", "delete"]
    assert len(session.statements) == 1, "the lock statement is issued before either callback"


@pytest.mark.asyncio
async def test_the_lock_is_a_for_update_on_the_secret_row() -> None:
    session, secret_id = FakeAsyncSession(), uuid.uuid4()

    await secrets_guarded_delete.lock_secret_row(session, secret_id)

    sql = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert sql.rstrip().endswith("FOR UPDATE")
    assert "secrets.id" in sql


@pytest.mark.asyncio
async def test_a_refusal_never_reaches_the_delete() -> None:
    deleted = AsyncMock()

    async def dependents() -> list:
        return [_LATE]

    with pytest.raises(secrets_guarded_delete.HTTPException) as refused:
        await secrets_guarded_delete.guarded_delete(
            FakeAsyncSession(), uuid.uuid4(), dependents=dependents, delete=deleted
        )

    assert refused.value.status_code == 409
    deleted.assert_not_awaited()


# --- bulk chat delete ----------------------------------------------------------------------------


def _bulk_client(manager, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(secrets_module, "secrets_manager", manager)
    monkeypatch.setattr(secrets_module, "audit_secret_op", AsyncMock())
    monkeypatch.setattr(secrets_module, "check_rate_limit", AsyncMock())
    app = FastAPI()
    app.include_router(secrets_module.router, prefix="/api/secrets")
    app.dependency_overrides[secrets_module.check_admin_permission] = lambda: True
    return TestClient(app, raise_server_exceptions=False)


def _register_attempt(monkeypatch, session, secret_id: uuid.UUID, attempts: list):
    """A ``register_dependency`` against *secret_id*; records how it ended."""
    import asyncio

    from services.envelope_secrets_service import EnvelopeSecretsService, SecretNotFoundError
    from services.secrets_coordinator import SecretsCoordinator

    coordinator = SecretsCoordinator(EnvelopeSecretsService(root_key=bytes(range(32))))
    monkeypatch.setattr(coordinator, "_facts", AsyncMock())
    kwargs = dict(user_id=uuid.uuid4(), permissions=set(), dependent_kind="service", dependent_id="late")

    def attempt() -> None:
        try:
            asyncio.run(coordinator.register_dependency(session, secret_id=secret_id, **kwargs))
        except SecretNotFoundError:
            attempts.append("not_found")

    return attempt


def test_bulk_chat_delete_cannot_race_a_registration(tmp_path, monkeypatch) -> None:
    """A dependent registered while the bulk delete runs has no vault row to attach to.

    ``DELETE /api/secrets/chat/{chat_id}`` removes only the legacy file store's rows. Their ids are
    never in the vault, so ``register_dependency`` raises not-found at the seam and nothing is
    recorded; the delete needs no lock because there is nothing it could cascade.
    """
    from api.schemas_system import ChatSecretScope, SecretCreateRequest
    from api.secrets_defects_20557_test import _manager

    manager = _manager(tmp_path)
    request = SecretCreateRequest(name="k", value="v", scope=ChatSecretScope.CHAT, chat_id="chat-1", type="api_key")
    created = manager.create_secret(request)
    session, attempts = FakeAsyncSession(default_result=FakeResult([])), []
    register = _register_attempt(monkeypatch, session, uuid.UUID(str(created.id)), attempts)
    real_delete = manager.delete_chat_secrets

    def delete_with_a_registration_in_flight(chat_id, secret_ids=None):
        register()
        return real_delete(chat_id, secret_ids)

    monkeypatch.setattr(manager, "delete_chat_secrets", delete_with_a_registration_in_flight)

    response = _bulk_client(manager, monkeypatch).delete("/api/secrets/chat/chat-1")

    assert response.status_code == 200
    assert response.json()["result"]["total_deleted"] == 1
    assert attempts == ["not_found"], "the registration found no vault row"
    assert session.added == [] and session.commits == 0, "no dependent was recorded"
