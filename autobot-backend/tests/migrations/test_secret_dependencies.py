# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the secret-dependency graph (#10088 Task 8.2 / 8.4).

Postgres-backed (migration-gate): the 061 migration creates ``secret_dependencies`` on an
``upgrade head`` schema, and SecretDependencyService register/query/idempotency, the
what-depends-on impact list, and FK CASCADE on secret deletion are exercised against it.
"""

import base64
import uuid

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret
from services.secret_dependency_service import SecretDependencyService
from services.envelope_secrets_service import EnvelopeSecretsService
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_OWNER = uuid.uuid4()


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _make_secret(session) -> uuid.UUID:
    svc = EnvelopeSecretsService(root_key=_ROOT)
    secret = await svc.create(
        session,
        owner_vault=VaultRef(VaultKind.USER, str(_OWNER)),
        name="db-pw",
        secret_type="password",
        plaintext=b"v",
        created_by=_OWNER,
    )
    return secret.id


async def test_migration_creates_table(session):
    reg = (await session.execute(text("SELECT to_regclass('public.secret_dependencies')"))).scalar()
    assert reg is not None


async def test_register_query_idempotent_and_unregister(session):
    sid = await _make_secret(session)
    svc = SecretDependencyService()

    a = await svc.register(session, secret_id=sid, dependent_kind="agent", dependent_id="researcher")
    await svc.register(session, secret_id=sid, dependent_kind="workflow", dependent_id="wf-1")
    again = await svc.register(session, secret_id=sid, dependent_kind="agent", dependent_id="researcher")
    assert again.id == a.id  # idempotent — same row, no duplicate

    deps = await svc.what_depends_on(session, secret_id=sid)
    assert {(d.dependent_kind, d.dependent_id) for d in deps} == {("agent", "researcher"), ("workflow", "wf-1")}

    assert await svc.secrets_for_dependent(session, dependent_kind="agent", dependent_id="researcher") == [sid]

    removed = await svc.unregister(session, secret_id=sid, dependent_kind="agent", dependent_id="researcher")
    assert removed == 1
    assert [(d.dependent_kind, d.dependent_id) for d in await svc.what_depends_on(session, secret_id=sid)] == [
        ("workflow", "wf-1")
    ]


async def test_register_rejects_unknown_kind(session):
    sid = await _make_secret(session)
    with pytest.raises(ValueError):
        await SecretDependencyService().register(session, secret_id=sid, dependent_kind="bogus", dependent_id="x")


async def test_secret_deletion_cascades_dependencies(session):
    sid = await _make_secret(session)
    svc = SecretDependencyService()
    await svc.register(session, secret_id=sid, dependent_kind="service", dependent_id="connector:gitlab")
    await session.commit()

    await session.execute(delete(Secret).where(Secret.id == sid))
    await session.commit()

    assert await svc.what_depends_on(session, secret_id=sid) == []  # FK ondelete CASCADE


async def test_coordinator_describe_dependencies_authz(session):
    # The /dependencies endpoint routes through coordinator.describe_dependencies, gated on manage
    # (share) authority — owner/admin may view the impact list; a stranger may not.
    from services.secrets_coordinator import SecretsCoordinator
    from services.envelope_secrets_service import SecretAccessError, SecretNotFoundError

    coord = SecretsCoordinator(service=EnvelopeSecretsService(root_key=_ROOT))
    owner = VaultRef(VaultKind.USER, str(_OWNER))
    secret = await coord.create(
        session, user_id=_OWNER, permissions=set(), owner_vault=owner, name="x", secret_type="password", plaintext=b"v"
    )
    await SecretDependencyService().register(
        session, secret_id=secret.id, dependent_kind="workflow", dependent_id="wf-7"
    )
    await session.commit()

    deps = await coord.describe_dependencies(session, user_id=_OWNER, permissions=set(), secret_id=secret.id)
    assert [(d.dependent_kind, d.dependent_id) for d in deps] == [("workflow", "wf-7")]

    with pytest.raises(SecretAccessError):
        await coord.describe_dependencies(session, user_id=uuid.uuid4(), permissions=set(), secret_id=secret.id)

    admin_deps = await coord.describe_dependencies(
        session, user_id=uuid.uuid4(), permissions={"admin:access"}, secret_id=secret.id
    )
    assert len(admin_deps) == 1

    with pytest.raises(SecretNotFoundError):
        await coord.describe_dependencies(session, user_id=_OWNER, permissions=set(), secret_id=uuid.uuid4())
