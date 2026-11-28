# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21039: authorize before locking, bound the lock wait, release before auditing, bind a confirmation.

The guarded delete (``secrets_guarded_delete.guarded_delete``) reads the dependents unlocked first (that read
enforces the caller's authority), then takes the row lock with a timeout, then re-lists under the lock. A
confirmation names the set the person saw (``dependents_digest``): a dependent registered after that listing
makes the confirmed retry refuse again. Every failure rolls back before the caller writes its audit record.
"""

# flake8: noqa: F811 -- pytest fixtures imported by name are re-requested as parameters

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from api import envelope_secrets_delete as envelope_delete
from api import envelope_secrets_delete_20640_test as env
from api import secrets_guarded_delete as guard
from api.envelope_secrets_delete_20640_test import _Coordinator, store  # noqa: F401 -- fixture
from api.secrets_defects_20557_test import _digest, _with_dependents
from api.secrets_system_vault_17731_test import _SECRET_ID, client_and_vault  # noqa: F401 -- fixture
from services.envelope_secrets_service import SecretAccessError
from testkit.fake_async_session import FakeAsyncSession

_LATE = SimpleNamespace(dependent_kind="agent", dependent_id="registered-after-the-listing")
_SEEN = env._DEPENDENTS[0]


class _Pg(Exception):
    """A driver error carrying a PostgreSQL SQLSTATE, as asyncpg's do."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def _db_error(sqlstate: str) -> OperationalError:
    return OperationalError("SELECT ... FOR UPDATE", {}, _Pg(sqlstate))


class _LockingSession(FakeAsyncSession):
    """Raises ``error`` on the FOR UPDATE statement (the second execute)."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self._error = error

    async def execute(self, statement, *args, **kwargs):
        if len(self.statements) == 1:
            self.statements.append(statement)
            raise self._error
        return await super().execute(statement, *args, **kwargs)


# --- authorize before the lock ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_caller_who_may_not_delete_never_takes_the_lock(monkeypatch) -> None:
    locked: list = []

    async def lock(session, secret_id) -> None:
        locked.append(secret_id)

    monkeypatch.setattr(guard, "lock_secret_row", lock)
    session = FakeAsyncSession()

    async def dependents() -> list:
        raise SecretAccessError("not authorized")

    async def delete() -> None:
        raise AssertionError("never reached")

    with pytest.raises(SecretAccessError):
        await guard.guarded_delete(session, uuid.uuid4(), dependents=dependents, delete=delete)

    assert locked == [], "the unlocked read refused the caller before any lock"
    assert session.rollbacks == 1


# --- the lock wait is bounded -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_lock_timeout_is_a_503_with_a_retry_hint_and_a_rollback() -> None:
    session = _LockingSession(_db_error("55P03"))

    async def dependents() -> list:
        return []

    with pytest.raises(guard.HTTPException) as refused:
        await guard.guarded_delete(session, uuid.uuid4(), dependents=dependents, delete=pytest.fail)

    assert refused.value.status_code == 503
    assert refused.value.detail["code"] == "secret_lock_timeout"
    assert refused.value.headers["Retry-After"] == str(max(1, -(-guard.SECRET_DELETE_LOCK_TIMEOUT_MS // 1000)))
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_any_other_database_error_is_not_mistaken_for_a_lock_timeout() -> None:
    session = _LockingSession(_db_error("40001"))

    async def dependents() -> list:
        return []

    with pytest.raises(OperationalError):
        await guard.guarded_delete(session, uuid.uuid4(), dependents=dependents, delete=pytest.fail)


def test_the_timeout_is_env_backed_and_registered() -> None:
    from autobot_shared.env_registry import REGISTRY

    spec = REGISTRY["AUTOBOT_SECRET_DELETE_LOCK_TIMEOUT_MS"]
    assert (spec.default, spec.range) == (5000, (100, 60000))
    assert guard.SECRET_DELETE_LOCK_TIMEOUT_MS == 5000


# --- the lock is released before the audit record -------------------------------------------------------


def test_the_envelope_denied_record_is_written_after_the_rollback(store, monkeypatch) -> None:
    order: list = []
    real = envelope_delete.audit_secret_op

    async def audit(*args, **kwargs):
        order.append(("audit", args[3] if len(args) > 3 else kwargs.get("phase")))
        return await real(*args, **kwargs)

    monkeypatch.setattr(envelope_delete, "audit_secret_op", audit)
    gen = env._client(_Coordinator([_SEEN]))
    client = next(gen)
    rollback = client.session.rollback

    async def spy() -> None:
        order.append(("rollback", None))
        await rollback()

    client.session.rollback = spy
    try:
        response = client.delete("/api/v2/secrets/" + env._SECRET)
    finally:
        gen.close()

    assert response.status_code == 409
    assert order == [("audit", "attempted"), ("rollback", None), ("audit", "denied")]


# --- a confirmation names the set that was listed --------------------------------------------------------


def test_the_409_carries_the_digest_of_the_listed_set(store) -> None:
    response, _ = env._run(_Coordinator([_SEEN]), "/api/v2/secrets/" + env._SECRET, store)

    assert response.json()["detail"]["dependents_digest"] == guard.dependents_digest([_SEEN])


def test_a_bare_confirm_flag_no_longer_confirms(store) -> None:
    coordinator = _Coordinator([_SEEN])

    response, _ = env._run(coordinator, "/api/v2/secrets/" + env._SECRET, store, "?confirm_dependents=true")

    assert response.status_code == 409
    assert coordinator.vault == {env._SECRET}


def test_a_dependent_added_after_the_listing_makes_the_confirmed_user_delete_refuse(store) -> None:
    coordinator = _Coordinator([_SEEN, _LATE])  # registered between the 409 the person saw and the retry
    stale = f"?dependents_digest={guard.dependents_digest([_SEEN])}"

    response, client = env._run(coordinator, "/api/v2/secrets/" + env._SECRET, store, stale)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert {d["dependent_id"] for d in detail["dependents"]} == {"scheduler", "registered-after-the-listing"}
    assert detail["dependents_digest"] == guard.dependents_digest([_SEEN, _LATE])
    assert coordinator.vault == {env._SECRET}, "the secret must still be stored"
    assert client.session.commits == 0


def test_a_dependent_added_after_the_listing_makes_the_confirmed_main_delete_refuse(
    client_and_vault, monkeypatch
) -> None:
    client, vault = _with_dependents(client_and_vault, monkeypatch, [("service", "scheduler"), ("agent", "late")])
    stale = _digest([("service", "scheduler")])

    response = client.delete(f"/api/secrets/{_SECRET_ID}?dependents_digest={stale}")

    assert response.status_code == 409
    assert response.json()["detail"]["dependents_digest"] == _digest([("service", "scheduler"), ("agent", "late")])
    assert uuid.UUID(_SECRET_ID) in vault.store, "the secret must still be stored"


def test_the_digest_does_not_depend_on_listing_order() -> None:
    other = SimpleNamespace(dependent_kind="agent", dependent_id="a-1")
    assert guard.dependents_digest([_SEEN, other]) == guard.dependents_digest([other, _SEEN])
