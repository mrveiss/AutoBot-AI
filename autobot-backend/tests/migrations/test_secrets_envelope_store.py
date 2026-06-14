# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration 20260614_057 builds the unified envelope secrets store (#10088 / Task 2.1)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]


async def _scalar(url: str, sql: str):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql))).scalar()
    finally:
        await engine.dispose()


async def test_envelope_schema_present_at_head(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0

    for column in ("owner_vault", "sealed_value", "version"):
        present = await _scalar(
            fresh_db_url,
            f"SELECT count(*) FROM information_schema.columns "
            f"WHERE table_name='secrets' AND column_name='{column}'",
        )
        assert present == 1, f"secrets.{column} missing at head"

    # Legacy Fernet column is relaxed to nullable so envelope rows need no blob.
    nullable = await _scalar(
        fresh_db_url,
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name='secrets' AND column_name='encrypted_value'",
    )
    assert nullable == "YES"

    assert (
        await _scalar(fresh_db_url, "SELECT count(*) FROM information_schema.tables WHERE table_name='secret_grants'")
        == 1
    )
    assert (
        await _scalar(
            fresh_db_url, "SELECT count(*) FROM pg_constraint WHERE conname='uq_secret_grants_secret_grantee'"
        )
        == 1
    )
    assert (
        await _scalar(fresh_db_url, "SELECT count(*) FROM pg_indexes WHERE indexname='ix_secret_grants_grantee'") == 1
    )


async def test_grant_unique_constraint_enforced(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            sid = (
                await conn.execute(
                    text(
                        "INSERT INTO secrets (id, owner_id, name, type, scope, team_ids, shared_with, tags, "
                        "extra_data, is_active, version, owner_vault, sealed_value) "
                        "VALUES (gen_random_uuid(), gen_random_uuid(), 's', 'api_key', 'user', '[]', '[]', '[]', "
                        "'{}', true, 1, 'user:alice', '{}'::jsonb) RETURNING id"
                    )
                )
            ).scalar()
            await conn.execute(
                text(
                    "INSERT INTO secret_grants (id, secret_id, grantee, wrapped_dek) "
                    "VALUES (gen_random_uuid(), :sid, 'user:alice', '{}'::jsonb)"
                ),
                {"sid": sid},
            )
        # Same (secret_id, grantee) again must violate the unique constraint.
        with pytest.raises(Exception):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO secret_grants (id, secret_id, grantee, wrapped_dek) "
                        "VALUES (gen_random_uuid(), :sid, 'user:alice', '{}'::jsonb)"
                    ),
                    {"sid": sid},
                )
    finally:
        await engine.dispose()
