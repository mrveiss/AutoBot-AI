# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The CEO backfill runs against a real database, not just a text scan (#15770).

#15770's third criterion asked that existing companies acquire a CEO, *proven by
a test against a company created before this change*. It was ticked on the
migration's SQL plus four tests that read the migration as text -- which is
existence, not execution, and the test file that carried them said so outright.

Those text tests pass unchanged if the SQL is syntactically invalid, if
``gen_random_uuid()`` is unavailable, or if the ``llc_status IS NOT NULL`` filter
excludes the real company population. None of those is hypothetical: the backfill
is Postgres-only precisely because it uses constructs the unit suite's SQLite has
no equivalent for, so the unit suite could never have executed it.

This runs the migration. The company is inserted at the revision **before** the
one under test, which is what makes it a company that predates the change rather
than one the creation path built.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.asyncio, requires_postgres]

_BEFORE = "20260827_087"
_AFTER = "20260906_088"
_TABLE = "llc_company_ceos"


async def _seed_company(conn, *, llc_status: str | None) -> uuid.UUID:
    """One `organizations` row, as it exists before the migration runs."""
    org_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO organizations (id, name, slug, settings, llc_status) "
            "VALUES (:id, :name, :slug, '{}'::jsonb, :llc_status)"
        ),
        {
            "id": org_id,
            "name": f"company-{org_id.hex[:8]}",
            "slug": f"company-{org_id.hex[:8]}",
            "llc_status": llc_status,
        },
    )
    return org_id


async def test_a_company_created_before_this_change_acquires_an_agent_ceo(fresh_db_url):
    """AC3, executed.

    The company is inserted at 087 -- before `llc_company_ceos` exists -- so it
    cannot have been provisioned by the creation path.
    """
    assert run_alembic(["upgrade", _BEFORE], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            # The table must not exist yet, or this proves nothing about the
            # backfill -- the same contrast the device-capability test makes.
            exists = await conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{_TABLE}"})
            assert exists.scalar() is None, (
                f"{_TABLE} already exists at {_BEFORE}; this test would then be "
                "asserting about a table the migration did not create"
            )
            company_id = await _seed_company(conn, llc_status="active")
    finally:
        await engine.dispose()

    assert run_alembic(["upgrade", _AFTER], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT holder_type, holder_agent_id, holder_user_id " f"FROM {_TABLE} WHERE company_id = :c"),
                    {"c": company_id},
                )
            ).one_or_none()
            assert row is not None, "the pre-existing company was not provisioned a CEO"
            assert row.holder_type == "agent"
            assert row.holder_agent_id is not None
            assert row.holder_user_id is None

            agent = (
                await conn.execute(
                    text("SELECT agent_id, company_id FROM agent_org_nodes WHERE id = :a"),
                    {"a": row.holder_agent_id},
                )
            ).one()
            assert agent.agent_id == f"ceo-{company_id}"
            assert agent.company_id == company_id
    finally:
        await engine.dispose()


async def test_a_non_llc_organization_is_left_alone(fresh_db_url):
    """The contrast case: the filter must exclude something.

    Without this, a backfill that dropped `llc_status IS NOT NULL` and
    provisioned a CEO for every organization in the table would satisfy the
    test above perfectly.
    """
    assert run_alembic(["upgrade", _BEFORE], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            plain_org = await _seed_company(conn, llc_status=None)
            llc_org = await _seed_company(conn, llc_status="active")
    finally:
        await engine.dispose()

    assert run_alembic(["upgrade", _AFTER], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.connect() as conn:
            provisioned = set((await conn.execute(text(f"SELECT company_id FROM {_TABLE}"))).scalars().all())
    finally:
        await engine.dispose()

    assert llc_org in provisioned
    assert plain_org not in provisioned, (
        "an organization with no llc_status was given a CEO; the backfill's " "scope filter is not doing anything"
    )


async def test_running_the_migration_twice_provisions_one_ceo(fresh_db_url):
    """`upgrade` creates the table only when absent but always reaches the
    backfill, so a re-run must be a no-op rather than a unique violation."""
    assert run_alembic(["upgrade", _BEFORE], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            company_id = await _seed_company(conn, llc_status="active")
    finally:
        await engine.dispose()

    assert run_alembic(["upgrade", _AFTER], fresh_db_url).returncode == 0
    # Down and up again: the table is dropped, the provisioned agent is not, so
    # the second pass exercises the adopt-by-slug path rather than the insert.
    assert run_alembic(["downgrade", _BEFORE], fresh_db_url).returncode == 0
    assert run_alembic(["upgrade", _AFTER], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.connect() as conn:
            ceos = (
                await conn.execute(
                    text(f"SELECT COUNT(*) FROM {_TABLE} WHERE company_id = :c"),
                    {"c": company_id},
                )
            ).scalar()
            agents = (
                await conn.execute(
                    text("SELECT COUNT(*) FROM agent_org_nodes WHERE agent_id = :s"),
                    {"s": f"ceo-{company_id}"},
                )
            ).scalar()
    finally:
        await engine.dispose()

    assert ceos == 1, f"expected exactly one CEO row after two upgrades, found {ceos}"
    assert agents == 1, f"expected exactly one default CEO agent, found {agents}"
