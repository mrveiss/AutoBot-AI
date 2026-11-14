# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``DELETE /api/secrets/{id}`` against a REAL Postgres row lock, through the route (#21386).

The per-route race tests inject the concurrent registration through a patched lock function, and the
database test in ``test_secret_delete_race_21039`` calls the shared helper, not the route. Here the request
goes through the secrets router (``httpx`` over ASGI) into ``delete_system_vault_secret``,
``guarded_delete`` and a real session; the concurrent registration is a second real session holding
``FOR KEY SHARE`` on the secret row through the foreign key. Only the authority is faked (the principal, and
a coordinator that delegates the dependents listing and the delete the way ``_delete_guarded`` does), plus
the rate limiter, the session lookup and the audit sink, whose records are asserted.

Real Postgres only -- SQLite has no row locks (``AUTOBOT_MIGRATION_TEST_ADMIN_URL``).
"""

# flake8: noqa: F811 -- pytest fixtures imported by name are re-requested as parameters

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api import secrets as secrets_module
from api import secrets_guarded_delete, secrets_system_vault
from services.secret_dependency_service import SecretDependencyService
from tests.migrations.conftest import requires_postgres
from tests.migrations.test_secret_delete_race_21039 import (  # noqa: F401 -- fixtures and helpers
    _SYSTEM,
    _seed,
    _state,
    _wait_until_blocked,
    coordinator,
    maker,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.migration_gate, requires_postgres]

_ADMIN_ID = str(uuid.uuid4())
#: Shorter than the default so a stuck registration is refused quickly; the ``Retry-After`` it implies is 1 s.
_SHORT_LOCK_TIMEOUT_MS = 200


class _DelegatingAuthority:
    """The coordinator surface ``_guarded_vault_delete`` calls, with the authority check left out."""

    def __init__(self, coordinator) -> None:  # noqa: ANN001
        self._coordinator = coordinator

    async def describe_dependencies(self, session, *, user_id, permissions, secret_id):  # noqa: ANN001
        return await self._coordinator.service_describe_dependencies(session, secret_id=secret_id, vault=_SYSTEM)

    async def delete(self, session, *, user_id, permissions, secret_id):  # noqa: ANN001
        await self._coordinator.service_delete(session, secret_id=secret_id, vault=_SYSTEM)


@pytest.fixture()
async def route(maker, coordinator, monkeypatch):  # noqa: ANN001
    """(client, audit sink): the secrets router over the real database, every seam patched where the route reads it."""
    opened: list = []

    async def real_sessions():
        session = maker()
        opened.append(session)
        yield session

    audit = AsyncMock()
    legacy = MagicMock()
    legacy.delete_secret.return_value = False  # not a legacy file secret, so the vault path decides
    authority = _DelegatingAuthority(coordinator)
    monkeypatch.setattr(secrets_module, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(secrets_module, "audit_secret_op", audit)
    monkeypatch.setattr(secrets_module, "audit_record", MagicMock())
    monkeypatch.setattr(secrets_module, "secrets_manager", legacy)
    monkeypatch.setattr(
        secrets_module,
        "get_auth_middleware",
        lambda: SimpleNamespace(get_user_from_request=lambda _request: {"user_id": _ADMIN_ID}),
    )
    monkeypatch.setattr(secrets_system_vault, "_coordinator_or_none", lambda: authority)
    monkeypatch.setattr(secrets_system_vault, "_principal", AsyncMock(return_value=(uuid.UUID(_ADMIN_ID), set())))
    monkeypatch.setattr("llc.deps.get_session", real_sessions)
    app = FastAPI()
    app.include_router(secrets_module.router, prefix="/api/secrets")
    app.dependency_overrides[secrets_module.check_admin_permission] = lambda: True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, audit
    for session in opened:
        await session.close()


def _records(audit: AsyncMock) -> list:
    """(result, reason) of each record that names one: the intent first, then the outcome."""
    return [(call.args[3], call.kwargs.get("reason")) for call in audit.await_args_list if len(call.args) > 3]


async def test_a_registration_in_flight_makes_the_route_wait_then_answer_409(route, maker, coordinator):  # noqa: ANN001
    client, audit = route
    secret_id = await _seed(maker, coordinator)

    async with maker() as registering:
        await SecretDependencyService().register(
            registering, secret_id=secret_id, dependent_kind="service", dependent_id="late"
        )
        request = asyncio.create_task(client.delete(f"/api/secrets/{secret_id}"))
        await _wait_until_blocked(maker, request)
        await registering.commit()
        response = await request

    assert response.status_code == 409
    assert response.json()["detail"]["dependents"] == [{"dependent_kind": "service", "dependent_id": "late"}]
    assert await _state(maker, secret_id) == (1, ["late"])
    assert _records(audit) == [("attempted", None), ("denied", "has_dependents")]


async def test_a_lock_held_past_the_timeout_is_a_503_with_an_outcome_record(
    route, maker, coordinator, monkeypatch
):  # noqa: ANN001
    client, audit = route
    monkeypatch.setattr(secrets_guarded_delete, "SECRET_DELETE_LOCK_TIMEOUT_MS", _SHORT_LOCK_TIMEOUT_MS)
    secret_id = await _seed(maker, coordinator)

    async with maker() as registering:
        await SecretDependencyService().register(
            registering, secret_id=secret_id, dependent_kind="service", dependent_id="late"
        )
        response = await asyncio.wait_for(client.delete(f"/api/secrets/{secret_id}"), timeout=10)
        await registering.rollback()

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["detail"]["code"] == "secret_lock_timeout"
    assert await _state(maker, secret_id) == (1, [])
    assert _records(audit) == [("attempted", None), ("denied", "http_503")]
