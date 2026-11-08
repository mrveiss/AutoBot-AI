# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A dependent registered while a secret delete is in flight is never cascade-deleted (#21039).

``guarded_delete`` takes the secret row ``FOR UPDATE`` and lists dependents under it. Registering a
dependent takes ``FOR KEY SHARE`` on that row through the foreign key, which conflicts, so the two
serialize in either order:

* registration first, uncommitted: the delete waits, then its listing sees the committed dependent
  and refuses (409), leaving the secret and the dependent;
* delete first, uncommitted: the registration waits, then fails the foreign key because the secret
  is gone, so no dependent is ever lost without a confirmation.

Real Postgres only -- SQLite has no row locks (``AUTOBOT_MIGRATION_TEST_ADMIN_URL``).
"""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.secrets_guarded_delete import guarded_delete
from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret
from models.secret_dependency import SecretDependency
from services.envelope_secrets_service import EnvelopeSecretsService
from services.secret_dependency_service import SecretDependencyService
from services.secrets_coordinator import SecretsCoordinator
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.asyncio, pytest.mark.migration_gate, requires_postgres]

_SYSTEM = VaultRef(VaultKind.SYSTEM)
_ROOT = bytes(range(32))
_VALUE = b"v"  # pragma: allowlist secret
#: Long enough that a statement which is NOT waiting on the lock has finished.
_BLOCKED_PROBE_SECONDS = 1.0


@pytest.fixture()
async def maker(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture()
def coordinator():
    return SecretsCoordinator(EnvelopeSecretsService(root_key=_ROOT))


async def _seed(maker, coordinator):  # noqa: ANN001
    async with maker() as session:
        secret = await coordinator.service_create(
            session,
            owner_vault=_SYSTEM,
            name="fleet",
            secret_type="token",  # pragma: allowlist secret
            plaintext=_VALUE,
            service_id="test",
        )
        await session.commit()
        return secret.id


def _delete_guarded(session, coordinator, secret_id):  # noqa: ANN001
    async def dependents() -> list:
        return await coordinator.service_describe_dependencies(session, secret_id=secret_id, vault=_SYSTEM)

    async def delete() -> None:
        await coordinator.service_delete(session, secret_id=secret_id, vault=_SYSTEM)

    return guarded_delete(session, secret_id, dependents=dependents, delete=delete)


async def _state(maker, secret_id):  # noqa: ANN001
    async with maker() as session:
        secrets = (await session.execute(select(Secret.id).where(Secret.id == secret_id))).scalars().all()
        deps = (await session.execute(select(SecretDependency.dependent_id))).scalars().all()
    return len(secrets), deps


async def test_a_registration_in_flight_makes_the_delete_wait_then_refuse(maker, coordinator):  # noqa: ANN001
    secret_id = await _seed(maker, coordinator)

    async with maker() as registering, maker() as deleting:
        await SecretDependencyService().register(
            registering, secret_id=secret_id, dependent_kind="service", dependent_id="late"
        )
        delete = asyncio.create_task(_delete_guarded(deleting, coordinator, secret_id))
        done, _ = await asyncio.wait({delete}, timeout=_BLOCKED_PROBE_SECONDS)
        assert not done, "the delete did not wait for the in-flight registration"
        await registering.commit()
        with pytest.raises(HTTPException) as refused:
            await delete
        await deleting.rollback()

    assert refused.value.status_code == 409
    assert refused.value.detail["dependents"] == [{"dependent_kind": "service", "dependent_id": "late"}]
    assert await _state(maker, secret_id) == (1, ["late"])


async def test_a_delete_in_flight_makes_the_registration_wait_then_fail(maker, coordinator):  # noqa: ANN001
    secret_id = await _seed(maker, coordinator)

    async with maker() as deleting, maker() as registering:
        await _delete_guarded(deleting, coordinator, secret_id)
        register = asyncio.create_task(
            SecretDependencyService().register(
                registering, secret_id=secret_id, dependent_kind="service", dependent_id="late"
            )
        )
        done, _ = await asyncio.wait({register}, timeout=_BLOCKED_PROBE_SECONDS)
        assert not done, "the registration did not wait for the delete's row lock"
        await deleting.commit()
        with pytest.raises(IntegrityError):
            await register
        await registering.rollback()

    assert await _state(maker, secret_id) == (0, [])


async def test_a_delete_with_no_dependents_commits(maker, coordinator):  # noqa: ANN001
    secret_id = await _seed(maker, coordinator)

    async with maker() as session:
        await _delete_guarded(session, coordinator, secret_id)
        await session.commit()

    assert await _state(maker, secret_id) == (0, [])
