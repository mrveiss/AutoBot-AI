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
from api.secrets_guarded_delete import dependents_digest as guarded_digest
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
        "dependents_digest": guarded_digest([_LATE]),
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

    response, _ = env._run(coordinator, "/api/v2/secrets/" + env._SECRET, store, f"?dependents_digest={env._DIGEST}")

    assert response.status_code == 204
    assert events == ["lock"]


@pytest.fixture(params=["user", "service"])
def env_route(request):
    return request.param, ("/api/v2/secrets/" if request.param == "user" else "/api/v2/secrets/system/") + env._SECRET


# --- the guard itself ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_then_lock_then_list_then_delete(monkeypatch) -> None:
    events: list = []
    session = FakeAsyncSession()
    _register_when_locked(monkeypatch, events, lambda: None)

    async def dependents() -> list:
        events.append("list")
        return []

    async def delete() -> None:
        events.append("delete")

    await secrets_guarded_delete.guarded_delete(session, uuid.uuid4(), dependents=dependents, delete=delete)

    assert events == ["list", "lock", "list", "delete"], "authorize (unlocked), lock, list under the lock, delete"


@pytest.mark.asyncio
async def test_the_lock_is_a_for_update_on_the_secret_row() -> None:
    session, secret_id = FakeAsyncSession(), uuid.uuid4()

    await secrets_guarded_delete.lock_secret_row(session, secret_id)

    timeout, lock = (str(st.compile(dialect=postgresql.dialect())) for st in session.statements)
    assert "set_config('lock_timeout'" in timeout, "the wait is bounded before the lock is requested"
    assert lock.rstrip().endswith("FOR UPDATE")
    assert "secrets.id" in lock


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


def test_a_registration_against_a_legacy_chat_secret_id_finds_no_vault_row(tmp_path, monkeypatch) -> None:
    """A registration against a legacy chat-secret id finds no vault row (against a FAKE session).

    This shows only what the fake session returns -- no row for any id -- so it does not prove the
    id spaces are disjoint (``test_the_bulk_route_never_reaches_the_vault_or_the_guarded_delete`` and
    the importer's fresh id carry that argument). It pins that the bulk route, run with a registration
    in flight, deletes the legacy rows and records no dependent.
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


def test_the_bulk_route_never_reaches_the_vault_or_the_guarded_delete() -> None:
    """Structural: the bulk handler has no path to the vault ``secrets`` table, so it needs no row lock."""
    import ast
    import inspect
    import textwrap

    handler = next(
        r.endpoint for r in secrets_module.router.routes if r.path == "/chat/{chat_id}" and "DELETE" in r.methods
    )
    tree = ast.parse(textwrap.dedent(inspect.getsource(handler)))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }

    forbidden = {"guarded_delete", "delete_system_vault_secret", "lock_secret_row", "get_coordinator", "get_session"}
    assert not names & forbidden, sorted(names & forbidden)
    assert "delete_chat_secrets" in names, "the handler deletes through the legacy file store"
