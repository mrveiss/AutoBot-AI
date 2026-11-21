# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One envelope secret per (owner_vault, name) (#17850), against a real disposable Postgres.

AC 1: the migration refuses while duplicates exist, naming them by vault and id, and picks nothing.
AC 2: two creates of one (owner_vault, name) yield one row and one id -- also when they race.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret
from services.envelope_secrets_service import AmbiguousSecretError, EnvelopeSecretsService, SecretConflictError
from services.provider_key_vault import _find_system_secret_id
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = bytes(range(32))
_VAULT = VaultRef(VaultKind.SYSTEM)
_USER = uuid.UUID("00000000-0000-0000-0000-000000000000")
_BEFORE = "20261120_116"
_CONSTRAINT = "uq_secrets_owner_vault_name"


@pytest.fixture()
async def maker(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _create(session, name="SOME_KEY", value=b"v1"):
    svc = EnvelopeSecretsService(root_key=_ROOT)
    return await svc.create(
        session,
        owner_vault=_VAULT,
        name=name,
        secret_type="api_key",  # pragma: allowlist secret
        plaintext=value,
        created_by=_USER,  # pragma: allowlist secret
    )


async def _count(session, name="SOME_KEY") -> int:
    return (await session.execute(select(func.count()).select_from(Secret).where(Secret.name == name))).scalar_one()


async def test_two_creates_of_one_name_and_value_yield_one_row_and_one_id(maker):
    async with maker() as s:
        first = await _create(s, value=b"first")
        await s.commit()
        assert first.already_existed is False
        second = await _create(s, value=b"first")
        await s.commit()
        assert second.id == first.id and second.already_existed is True
        assert await _count(s) == 1


async def test_a_create_with_a_different_value_is_refused_and_the_stored_value_kept(maker):
    async with maker() as s:
        first = await _create(s, value=b"first")
        await s.commit()
        with pytest.raises(SecretConflictError) as refused:
            await _create(s, value=b"second")
        assert refused.value.reason == "value_differs" and refused.value.secret_id == first.id
        value = await EnvelopeSecretsService(root_key=_ROOT).read(s, secret_id=first.id, accessible_vaults={_VAULT})
        assert value == b"first" and await _count(s) == 1


async def test_a_deactivated_secret_keeps_its_name_and_is_neither_reused_nor_found_by_the_vault_lookup(maker):
    async with maker() as s:
        first = await _create(s)
        first.is_active = False
        await s.commit()
        with pytest.raises(SecretConflictError) as refused:
            await _create(s)
        assert refused.value.reason == "inactive"
        assert await _find_system_secret_id(s, "SOME_KEY") is None
        assert await _count(s) == 1


async def test_concurrent_first_creates_meet_at_the_constraint(maker):
    async def one():
        async with maker() as s:
            secret = await _create(s)
            await s.commit()
            return secret.id

    ids = await asyncio.gather(*(one() for _ in range(5)))
    assert len(set(ids)) == 1
    async with maker() as s:
        assert await _count(s) == 1


async def _insert_duplicates(maker) -> list[uuid.UUID]:
    """Drop the constraint, then mint two rows under one name -- the state an old installation is in."""
    async with maker() as s:
        await s.execute(text(f"ALTER TABLE secrets DROP CONSTRAINT {_CONSTRAINT}"))
        ids = []
        for _ in range(2):
            row = Secret(
                id=uuid.uuid4(), owner_id=_USER, name="DUP_KEY", type="api_key", scope="system",
                owner_vault=_VAULT.to_str(), sealed_value={"v": 1}, version=1,
            )  # fmt: skip
            s.add(row)
            ids.append(row.id)
        await s.commit()
    return ids


async def test_the_migration_refuses_duplicates_and_names_them_by_id(maker, fresh_db_url):
    ids = await _insert_duplicates(maker)
    assert run_alembic(["downgrade", _BEFORE], fresh_db_url).returncode == 0
    refused = run_alembic(["upgrade", "head"], fresh_db_url)
    assert refused.returncode != 0
    assert all(str(i) in refused.stderr for i in ids), "the refusal must name the duplicate ids"
    assert "DUP_KEY" not in refused.stderr, "the refusal must not carry the secret's name"
    async with maker() as s:
        assert await _count(s, "DUP_KEY") == 2, "the migration must not choose or delete a copy"
        await s.execute(text("DELETE FROM secrets WHERE id = :i"), {"i": ids[0]})
        await s.commit()
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0


async def test_create_refuses_to_choose_among_existing_duplicates(maker):
    await _insert_duplicates(maker)
    async with maker() as s:
        with pytest.raises(AmbiguousSecretError) as raised:
            await _create(s, name="DUP_KEY")
        assert "DUP_KEY" not in str(raised.value)
