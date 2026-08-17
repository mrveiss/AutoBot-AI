# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration 20260822_082 — workflows loses its global PK, no row is lost (#14271).

``workflows.workflow_id`` was a *global* primary key while every route/service
above it treats the identity as company-scoped. This migration replaces it
with a surrogate ``id`` primary key plus ``UNIQUE (company_id, workflow_id)``.

The load-bearing assertion is data survival: this seeds rows with raw SQL
against the OLD shape (revision 076, workflow_id as PK) — including a
``company_id IS NULL`` row, exactly what
``services/workflow_redis_backfill.py`` writes for unattributable legacy
workflows — runs the migration, and checks every row is still there,
unmodified in its business columns, each now carrying a distinct surrogate
``id``.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_PRE_MIGRATION_REVISION = "20260821_081"
_TARGET_REVISION = "20260822_082"


async def _seed_pre_migration_row(conn, *, workflow_id: str, company_id: str | None, name: str) -> None:
    """Insert directly, matching the OLD (076) table shape: workflow_id is the PK."""
    await conn.execute(
        text(
            "INSERT INTO workflows (workflow_id, company_id, name, status, source, definition) "
            "VALUES (:workflow_id, :company_id, :name, 'planned', 'created', '{}'::jsonb)"
        ),
        {"workflow_id": workflow_id, "company_id": company_id, "name": name},
    )


async def test_existing_rows_survive_including_null_company(fresh_db_url):
    """NO DATA LOSS: every pre-existing row, including company_id IS NULL, survives."""
    assert run_alembic(["upgrade", _PRE_MIGRATION_REVISION], fresh_db_url).returncode == 0

    company_a = str(uuid.uuid4())
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            await _seed_pre_migration_row(conn, workflow_id="wf-owned", company_id=company_a, name="Owned")
            await _seed_pre_migration_row(conn, workflow_id="wf-legacy", company_id=None, name="Recovered from Redis")
    finally:
        await engine.dispose()

    up = run_alembic(["upgrade", _TARGET_REVISION], fresh_db_url)
    assert up.returncode == 0, f"upgrade to {_TARGET_REVISION} failed:\nstdout:\n{up.stdout}\nstderr:\n{up.stderr}"

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(text("SELECT id, workflow_id, company_id, name FROM workflows ORDER BY workflow_id"))
            ).all()
    finally:
        await engine.dispose()

    assert len(rows) == 2, f"expected both pre-existing rows to survive, got {rows}"
    by_workflow_id = {row.workflow_id: row for row in rows}

    owned = by_workflow_id["wf-owned"]
    assert str(owned.company_id) == company_a
    assert owned.name == "Owned"
    assert owned.id is not None

    legacy = by_workflow_id["wf-legacy"]
    assert legacy.company_id is None, "company_id=NULL legacy row must stay NULL — never guessed at"
    assert legacy.name == "Recovered from Redis"
    assert legacy.id is not None

    assert owned.id != legacy.id, "each row gets its own distinct surrogate primary key"


async def test_two_companies_can_share_a_workflow_id_after_migration(fresh_db_url):
    """The collision this migration exists to allow: two companies, one workflow_id string."""
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0

    company_a, company_b = str(uuid.uuid4()), str(uuid.uuid4())
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO workflows (id, workflow_id, company_id, name, status, source, definition) "
                    "VALUES (gen_random_uuid(), :wf, :company_id, :name, 'planned', 'created', '{}'::jsonb)"
                ),
                {"wf": "prod-deploy", "company_id": company_a, "name": "A"},
            )
            # Same workflow_id, different company — must succeed, not raise.
            await conn.execute(
                text(
                    "INSERT INTO workflows (id, workflow_id, company_id, name, status, source, definition) "
                    "VALUES (gen_random_uuid(), :wf, :company_id, :name, 'planned', 'created', '{}'::jsonb)"
                ),
                {"wf": "prod-deploy", "company_id": company_b, "name": "B"},
            )

        async with engine.connect() as conn:
            count = (
                await conn.execute(
                    text("SELECT count(*) FROM workflows WHERE workflow_id = 'prod-deploy'"),
                )
            ).scalar()
        assert count == 2
    finally:
        await engine.dispose()


async def test_same_company_duplicate_workflow_id_still_conflicts(fresh_db_url):
    """The uniqueness that must remain: one company cannot hold the same workflow_id twice."""
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0

    company_a = str(uuid.uuid4())
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO workflows (id, workflow_id, company_id, name, status, source, definition) "
                    "VALUES (gen_random_uuid(), :wf, :company_id, :name, 'planned', 'created', '{}'::jsonb)"
                ),
                {"wf": "dup", "company_id": company_a, "name": "First"},
            )

        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO workflows (id, workflow_id, company_id, name, status, source, definition) "
                        "VALUES (gen_random_uuid(), :wf, :company_id, :name, 'planned', 'created', '{}'::jsonb)"
                    ),
                    {"wf": "dup", "company_id": company_a, "name": "Second"},
                )
    finally:
        await engine.dispose()
