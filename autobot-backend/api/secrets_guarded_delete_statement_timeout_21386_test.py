# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#21386: a lock timeout on ANY statement of the guarded delete is the 503, not a raw database error.

The transaction-local ``lock_timeout`` set before the row lock stays in force for the re-listing under the
lock and for the delete itself; a wait there that expires (SQLSTATE 55P03) used to escape as a 500.
"""

import uuid

import pytest
from sqlalchemy.exc import OperationalError

from api import secrets_guarded_delete as guard
from api.secrets_delete_lock_discipline_21039_test import _db_error
from testkit.fake_async_session import FakeAsyncSession

_RETRY_AFTER = str(max(1, -(-guard.SECRET_DELETE_LOCK_TIMEOUT_MS // 1000)))


async def _run(session: FakeAsyncSession, monkeypatch, stage: str, sqlstate: str) -> None:
    """Run the guarded delete (row lock stubbed) with the statement named by *stage* raising *sqlstate*."""
    listings = 0

    async def lock(_session, _secret_id) -> None:
        return None

    async def dependents() -> list:
        nonlocal listings
        listings += 1
        if stage == "relisting" and listings == 2:
            raise _db_error(sqlstate)
        return []

    async def delete() -> None:
        if stage == "delete":
            raise _db_error(sqlstate)

    monkeypatch.setattr(guard, "lock_secret_row", lock)
    await guard.guarded_delete(session, uuid.uuid4(), dependents=dependents, delete=delete)


@pytest.mark.parametrize("stage", ["relisting", "delete"])
@pytest.mark.asyncio
async def test_a_lock_timeout_on_a_later_statement_is_the_503_with_a_retry_hint(stage, monkeypatch) -> None:
    session = FakeAsyncSession()

    with pytest.raises(guard.HTTPException) as refused:
        await _run(session, monkeypatch, stage, "55P03")

    assert refused.value.status_code == 503
    assert refused.value.detail["code"] == "secret_lock_timeout"
    assert refused.value.headers["Retry-After"] == _RETRY_AFTER
    assert isinstance(refused.value.__cause__, OperationalError)
    assert session.rollbacks == 1
    assert session.commits == 0


@pytest.mark.parametrize("stage", ["relisting", "delete"])
@pytest.mark.asyncio
async def test_any_other_error_on_a_later_statement_is_not_mistaken_for_a_lock_timeout(stage, monkeypatch) -> None:
    session = FakeAsyncSession()

    with pytest.raises(OperationalError):
        await _run(session, monkeypatch, stage, "40001")

    assert session.rollbacks == 1
