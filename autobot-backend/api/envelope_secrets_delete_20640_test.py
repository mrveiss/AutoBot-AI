# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20640: the envelope deletes refuse a secret with dependents and record intent and outcome.

``DELETE /api/secrets/{id}`` (#20557) refuses while dependents exist and writes the record
before and after the write. The two envelope deletes -- the user route and the service-identity
system route -- reached the same store with neither. Every assertion is on the coordinator's
store (what was deleted) and on the audit store's events, not on the status code alone.

The bulk chat delete (``DELETE /api/secrets/chat/{chat_id}``) needs no dependents check: it
deletes only the legacy file store's rows (``SecretsManager.delete_chat_secrets``), whose ids
are random uuid4 values the vault never holds, and ``register_dependency`` needs the vault row.
``test_a_legacy_secret_cannot_have_dependents`` pins that.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import envelope_secrets
from api import secrets_audit_store_18648_test as base
from services.envelope_secrets_service import SecretAccessError, SecretNotFoundError
from testkit.fake_async_session import FakeAsyncSession

store = base.store  # the same fixture: the canonical audit logger with a faked final write

_SECRET = "11111111-1111-4111-8111-111111111111"
_DEPENDENTS = [SimpleNamespace(dependent_kind="service", dependent_id="scheduler")]
_LISTED = [{"dependent_kind": "service", "dependent_id": "scheduler"}]


class _Coordinator:
    """The envelope coordinator surface the two delete routes call; `vault` is what it holds."""

    def __init__(self, dependents=(), error=None):
        self.dependents, self.error, self.vault = list(dependents), error, {_SECRET}

    async def describe_dependencies(self, session, **_kw):
        return self.dependents

    async def service_describe_dependencies(self, session, **_kw):
        return self.dependents

    async def _remove(self):
        if self.error:
            raise self.error
        self.vault.clear()

    async def delete(self, session, **_kw):
        await self._remove()

    async def service_delete(self, session, **_kw):
        await self._remove()


def _client(coordinator: _Coordinator):
    app = FastAPI()
    app.include_router(envelope_secrets.router, prefix="/api/v2/secrets")
    session = FakeAsyncSession()
    app.dependency_overrides[envelope_secrets.get_session] = lambda: session
    app.dependency_overrides[envelope_secrets.get_coordinator] = lambda: coordinator
    app.dependency_overrides[envelope_secrets.principal] = lambda: (uuid.uuid4(), {"admin"})
    app.dependency_overrides[envelope_secrets.service_principal] = lambda: "slm-backend"
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"user_id": "user-42"}
    with patch("api.secrets_audit.get_auth_middleware", return_value=auth):
        with TestClient(app, raise_server_exceptions=False) as client:
            client.session = session
            yield client


@pytest.fixture(params=["user", "service"])
def route(request):
    """(url, how a caller deletes) for each envelope delete route."""
    return request.param, ("/api/v2/secrets/" if request.param == "user" else "/api/v2/secrets/system/") + _SECRET


def _trail(store) -> list[tuple[str, str | None]]:
    return [
        (e.outcome, e.metadata["details"].get("phase") or e.metadata["details"].get("reason")) for e in store.events
    ]


def _run(coordinator, url, store, suffix=""):
    gen = _client(coordinator)
    client = next(gen)
    try:
        return client.delete(url + suffix), client
    finally:
        gen.close()


def test_a_delete_with_dependents_is_refused_with_the_main_routes_409(route, store) -> None:
    _, url = route
    coordinator = _Coordinator(_DEPENDENTS)

    response, client = _run(coordinator, url, store)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "secret_has_dependents",
        "message": "Dependents use this secret",
        "dependents": _LISTED,
    }
    assert coordinator.vault == {_SECRET}, "the secret must still be stored"
    assert client.session.commits == 0


def test_a_refused_delete_records_the_intent_then_the_refusal(route, store) -> None:
    _, url = route

    _run(_Coordinator(_DEPENDENTS), url, store)

    assert _trail(store) == [("attempted", "before_write"), ("denied", "has_dependents")]


def test_a_user_can_confirm_past_dependents_but_a_service_cannot(route, store) -> None:
    kind, url = route
    coordinator = _Coordinator(_DEPENDENTS)

    response, _ = _run(coordinator, url, store, "?confirm_dependents=true")

    if kind == "user":
        assert response.status_code == 204
        assert coordinator.vault == set()
        assert _trail(store) == [("attempted", "before_write"), ("success", "completed")]
    else:
        assert response.status_code == 409, "an automatic actor never confirms (#17038)"
        assert coordinator.vault == {_SECRET}


def test_a_delete_without_dependents_records_intent_then_success(route, store) -> None:
    _, url = route
    coordinator = _Coordinator()

    response, client = _run(coordinator, url, store)

    assert response.status_code == 204
    assert coordinator.vault == set()
    assert _trail(store) == [("attempted", "before_write"), ("success", "completed")]
    assert client.session.commits == 1


def test_a_failed_delete_leaves_no_record_claiming_success(route, store) -> None:
    _, url = route
    coordinator = _Coordinator(error=RuntimeError("db down"))

    response, _ = _run(coordinator, url, store)

    assert response.status_code == 500
    assert _trail(store) == [("attempted", "before_write"), ("failed", "RuntimeError")]


@pytest.mark.parametrize(
    "error, status, expected",
    [
        (SecretAccessError("no"), 403, ("denied", "permission_denied")),
        (SecretNotFoundError("x"), 404, ("failed", "not_found")),
    ],
    ids=["not-authorized", "not-found"],
)
def test_a_refused_or_missing_delete_is_recorded_and_mapped(route, store, error, status, expected) -> None:
    _, url = route

    response, _ = _run(_Coordinator(error=error), url, store)

    assert response.status_code == status
    assert _trail(store) == [("attempted", "before_write"), expected]


def test_an_unrecorded_delete_deletes_nothing(route, store) -> None:
    _, url = route
    coordinator = _Coordinator()

    with patch("api.secrets_audit.audit_log", AsyncMock(return_value=False)):
        response, _ = _run(coordinator, url, store)

    assert response.status_code == 503
    assert coordinator.vault == {_SECRET}, "no credential is destroyed without its paper trail (#17038)"


def test_the_service_record_names_the_service_never_a_value(store) -> None:
    _run(_Coordinator(), "/api/v2/secrets/system/" + _SECRET, store)

    assert {e.metadata["details"].get("service") for e in store.events} == {"slm-backend"}


def test_a_legacy_secret_cannot_have_dependents() -> None:
    """The bulk chat delete's rows are legacy ids; dependents attach only to a vault row."""
    from api.schemas_system import SecretModel

    legacy_id = SecretModel(name="n", type="api_key", scope="general").id
    import inspect

    from services.secrets_coordinator import SecretsCoordinator

    assert len(legacy_id) == 36 and legacy_id[14] == "4", "a random uuid4, minted by SecretModel"
    assert "_owner_vault(session, secret_id)" in inspect.getsource(SecretsCoordinator.register_dependency)
