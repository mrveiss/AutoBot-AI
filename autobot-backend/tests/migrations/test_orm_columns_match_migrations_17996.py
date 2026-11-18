# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ORM columns vs the schema ``alembic upgrade head`` builds (#17996).

A fixture built with ``create_all`` takes its schema from the ORM, so it cannot see a column
the migrations never created: migration 093 omitted the ``created_at`` / ``updated_at`` that
``Base`` adds, ``release_for_run`` selected both, and every heartbeat run failed at its
finish step on a migrated database while every test passed.

Needs the disposable Postgres the migration gate provides (skipped without it).
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from autobot_shared.time_utils import now_utc
from tests.migrations.conftest import requires_postgres, run_alembic


def orm_column_drift(tables, migrated: dict[str, set[str]]) -> tuple[dict[str, list[str]], list[str]]:
    """Return ({table: ORM columns the migrated table lacks}, names of the tables compared)."""
    drift: dict[str, list[str]] = {}
    compared: list[str] = []
    for table in tables:
        if table.name not in migrated:
            continue  # a table with no migration is a different defect, not column drift
        compared.append(table.name)
        missing = sorted({c.name for c in table.columns} - migrated[table.name])
        if missing:
            drift[table.name] = missing
    return drift, compared


def _orm_tables():
    import canvas.models  # noqa: F401
    import llc.models  # noqa: F401
    import models.process_run  # noqa: F401
    import user_management.models  # noqa: F401
    from models.push_subscription import PushSubscription  # noqa: F401
    from user_management.models import Base

    return Base.metadata.sorted_tables


def test_drift_check_reports_a_column_the_table_lacks():
    """The #17996 shape: Base's updated_at missing from the migrated table must be named."""
    tables = _orm_tables()
    lease = next(t for t in tables if t.name == "llc_workspace_leases")
    migrated = {"llc_workspace_leases": {c.name for c in lease.columns} - {"updated_at"}}
    drift, compared = orm_column_drift(tables, migrated)
    assert drift == {"llc_workspace_leases": ["updated_at"]}
    assert compared == ["llc_workspace_leases"]


def test_llc_workspace_leases_is_an_orm_table_the_guard_compares():
    """The guard cannot pass on zero tables: the lease table must be among those compared."""
    tables = _orm_tables()
    names = {t.name for t in tables}
    assert "llc_workspace_leases" in names
    _, compared = orm_column_drift(tables, {t.name: {c.name for c in t.columns} for t in tables})
    assert "llc_workspace_leases" in compared and len(compared) == len(names)


async def _migrated_columns(engine) -> dict[str, set[str]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public'")
        )
        columns: dict[str, set[str]] = {}
        for table, column in rows:
            columns.setdefault(table, set()).add(column)
    return columns


@pytest.mark.migration_gate
@requires_postgres
async def test_every_orm_column_exists_in_the_migrated_schema(fresh_db_url):
    """Any ORM column the migration chain lacks is a query that fails in production."""
    tables = _orm_tables()

    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        migrated = await _migrated_columns(engine)
    finally:
        await engine.dispose()

    drift, compared = orm_column_drift(tables, migrated)
    assert "llc_workspace_leases" in compared, f"guard compared no lease table: {compared}"
    assert not drift, f"ORM columns absent from the migrated schema: {drift}"


@pytest.mark.migration_gate
@requires_postgres
async def test_release_for_run_runs_against_a_migrated_schema(fresh_db_url):
    """The query that failed on 2026-10-03: ``release_for_run`` on a migration-built table."""
    from llc.models.workspace_lease import LLCWorkspaceLease
    from llc.services.workspace_lease import release_for_run

    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            now = now_utc()
            lease = LLCWorkspaceLease(
                company_id=uuid.uuid4(),
                path="/ws/a",
                owner="agent",
                purpose="test",
                expires_at=now + timedelta(hours=1),
            )
            session.add(lease)
            await session.commit()
            # Full-entity SELECT of the table, as the sweep and the per-run release issue it.
            assert await release_for_run(session, uuid.uuid4(), "no lease held by this run") == []
            fetched = (await session.execute(select(LLCWorkspaceLease))).scalars().all()
            assert [row.id for row in fetched] == [lease.id]
            assert fetched[0].created_at is not None and fetched[0].updated_at is not None
    finally:
        await engine.dispose()


@pytest.mark.migration_gate
@requires_postgres
async def test_downgrade_keeps_columns_that_predate_the_revision(fresh_db_url):
    """A create_all-built table already had both columns; downgrading 103 must not drop them."""
    assert run_alembic(["upgrade", "20261012_102"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            for col in ("created_at", "updated_at"):
                await conn.execute(
                    text(f"ALTER TABLE llc_workspace_leases ADD COLUMN {col} timestamptz NOT NULL DEFAULT now()")
                )
            await conn.execute(
                text(
                    "INSERT INTO llc_workspace_leases (company_id, path, owner, purpose, expires_at, created_at) "
                    "VALUES (gen_random_uuid(), '/ws/x', 'a', 'p', now(), '2020-01-01T00:00:00Z')"
                )
            )
        assert run_alembic(["upgrade", "20261024_103"], fresh_db_url).returncode == 0
        assert run_alembic(["downgrade", "20261012_102"], fresh_db_url).returncode == 0
        async with engine.connect() as conn:
            cols = {
                r[0]
                for r in await conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='llc_workspace_leases'")
                )
            }
            year = (await conn.execute(text("SELECT extract(year FROM created_at) FROM llc_workspace_leases"))).scalar()
        assert {"created_at", "updated_at"} <= cols
        assert year == 2020
    finally:
        await engine.dispose()
