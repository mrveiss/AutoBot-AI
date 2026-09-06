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

# `migration_gate` is set here, not inherited: `tests/migrations/conftest.py`
# sets `pytestmark`, and pytest never reads that from a conftest (#15888).
# Without it, `-m migration_gate` DESELECTS these -- they do not even skip,
# so a green run says nothing about them.
pytestmark = [pytest.mark.asyncio, pytest.mark.migration_gate, requires_postgres]

_BEFORE = "20260827_087"
_BACKFILL = "20260906_088"
_AFTER = "20260907_090"
_TABLE = "llc_company_ceos"


async def _seed_company(
    conn,
    *,
    parent_org_id: uuid.UUID | None = None,
    deleted: bool = False,
    llc_status: str = "active",
) -> uuid.UUID:
    """One `organizations` row, as it exists before the migration runs.

    Every NOT NULL column without a ``server_default`` is supplied explicitly.
    Those carry a *client-side* ``default=``, so ``op.create_table`` emits no
    DDL DEFAULT and a raw INSERT omitting them raises NotNullViolation -- which
    fails in setup and makes every test in this file error for a reason
    unrelated to what it asserts.

    The set was enumerated across every migration touching ``organizations``
    rather than taken from the failure. Postgres reports only the first
    violation, so the error names ``max_users`` and stops; ``is_active`` is the
    next column and would have cost a second full CI cycle to discover. A
    constraint error is a lower bound on what is wrong.

    The four are ``name``, ``slug``, ``max_users`` and ``is_active``; every LLC
    column added by ``20260523_023`` carries a ``server_default`` and so needs
    no value here.
    """
    org_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO organizations "
            "(id, name, slug, settings, llc_status, parent_org_id, deleted_at, "
            " max_users, is_active, "
            " issue_counter, budget_monthly_cents, spent_monthly_cents, "
            " require_approval_for_hires, kb_inheritance_weight) "
            "VALUES (:id, :name, :slug, '{}'::jsonb, :llc_status, :parent, "
            "        NULL, -1, true, 0, 0, 0, false, 0.6)"
        ),
        {
            "id": org_id,
            "name": f"company-{org_id.hex[:8]}",
            "slug": f"company-{org_id.hex[:8]}",
            "llc_status": llc_status,
            "parent": parent_org_id,
        },
    )
    if deleted:
        await conn.execute(text("UPDATE organizations SET deleted_at = NOW() WHERE id = :id"), {"id": org_id})
    return org_id


async def _ceo_agent_liveness(conn, company_id: uuid.UUID):
    """The CEO's agent row, joined through the designation.

    `_ceo_of` reads `llc_company_ceos` only, and the repair writes to **two**
    tables. A mutation dropping the scope predicates from the UPDATE while
    keeping them on the DELETE deactivates every CEO agent in the installation
    and leaves every designation intact -- so the API reports each company's CEO
    correctly while none of those agents does anything. An assertion that reads
    only the designation is silent about that.
    """
    return (
        await conn.execute(
            text(
                "SELECT a.status, a.heartbeat_enabled "
                "FROM llc_company_ceos c JOIN agent_org_nodes a ON a.id = c.holder_agent_id "
                "WHERE c.company_id = :c"
            ),
            {"c": company_id},
        )
    ).one_or_none()


async def _ceo_of(conn, company_id: uuid.UUID):
    return (
        await conn.execute(
            text("SELECT holder_type, holder_agent_id FROM llc_company_ceos WHERE company_id = :c"),
            {"c": company_id},
        )
    ).one_or_none()


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
            # Selecting agent_id and company_id says the row exists, not that it
            # runs -- and the repair writes status and heartbeat_enabled in the
            # same pass, on the other side of the same predicates.
            liveness = await _ceo_agent_liveness(conn, company_id)
            assert liveness is not None
            assert liveness.status != "inactive", "the provisioned CEO agent was deactivated"
            assert liveness.heartbeat_enabled is not False, "the provisioned CEO agent will never be scheduled"
    finally:
        await engine.dispose()


async def test_a_top_level_company_keeps_its_ceo(fresh_db_url):
    """First, because everything else is satisfied by a repair that empties both tables.

    A cleanup that deleted every row would pass all three exclusion assertions
    below and destroy the feature. This is the assertion that makes them mean
    something.
    """
    assert run_alembic(["upgrade", _BEFORE], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            company = await _seed_company(conn)
    finally:
        await engine.dispose()

    assert run_alembic(["upgrade", _AFTER], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.connect() as conn:
            row = await _ceo_of(conn, company)
            liveness = await _ceo_agent_liveness(conn, company)
    finally:
        await engine.dispose()

    assert row is not None, "a top-level, non-deleted company lost its CEO to the repair"
    assert row.holder_type == "agent"
    # The designation surviving is half the claim. The repair writes to two
    # tables, and a mutation scoped on only one leaves every company reporting a
    # CEO that is dormant.
    assert liveness is not None, "the CEO designation survived but its agent row did not"
    assert liveness.status != "inactive", (
        "the designation is intact and its agent is deactivated -- the company reports a CEO that "
        "does nothing. Dropping the scope predicates from the UPDATE alone produces exactly this."
    )
    assert liveness.heartbeat_enabled is not False, "the surviving CEO agent will never be scheduled"


async def test_a_sub_organization_does_not_get_a_ceo(fresh_db_url):
    """`parent_org_id IS NULL` is half the discriminator (llc/services/company.py:144)."""
    assert run_alembic(["upgrade", _BEFORE], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            parent = await _seed_company(conn)
            child = await _seed_company(conn, parent_org_id=parent)
    finally:
        await engine.dispose()

    assert run_alembic(["upgrade", _AFTER], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.connect() as conn:
            assert await _ceo_of(conn, child) is None, "a sub-organization was left with a CEO"
            assert await _ceo_of(conn, parent) is not None, "the parent lost its CEO"
            dormant = (
                await conn.execute(
                    text("SELECT status, heartbeat_enabled FROM agent_org_nodes WHERE agent_id = :s"),
                    {"s": f"ceo-{child}"},
                )
            ).one_or_none()
    finally:
        await engine.dispose()

    assert dormant is not None, (
        "the sub-organization's agent row was deleted; it is an entity other tables "
        "resolve by id, so removing it converts a wrong row into a dangling one"
    )
    assert dormant.heartbeat_enabled is False
    assert dormant.status == "inactive"


async def test_a_soft_deleted_organization_does_not_get_a_ceo(fresh_db_url):
    """`deleted_at IS NULL` is the other half."""
    assert run_alembic(["upgrade", _BEFORE], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            gone = await _seed_company(conn, deleted=True)
    finally:
        await engine.dispose()

    assert run_alembic(["upgrade", _AFTER], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.connect() as conn:
            assert await _ceo_of(conn, gone) is None, "a soft-deleted organization was left asserting it has a CEO"
    finally:
        await engine.dispose()


async def test_an_archived_company_keeps_its_ceo(fresh_db_url):
    """Scope is structural and says nothing about `llc_status`.

    The designation is a structural fact; liveness is controlled by status
    elsewhere. Un-archiving into a silently headless company is the harder
    failure to notice.
    """
    assert run_alembic(["upgrade", _BEFORE], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            archived = await _seed_company(conn, llc_status="archived")
    finally:
        await engine.dispose()

    assert run_alembic(["upgrade", _AFTER], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.connect() as conn:
            assert (
                await _ceo_of(conn, archived) is not None
            ), "an archived company lost its CEO; scope is structural, not lifecycle"
            archived_liveness = await _ceo_agent_liveness(conn, archived)
            assert archived_liveness is not None
            assert archived_liveness.status != "inactive", "an archived company's CEO agent was deactivated"
            assert archived_liveness.heartbeat_enabled is not False
    finally:
        await engine.dispose()


async def test_a_hand_edited_ceo_row_is_left_alone(fresh_db_url):
    """The constraint that governs both statements, and the one most easily omitted.

    An owner who has since chosen a human CEO for a sub-organization must not
    lose that choice to a cleanup for a bug they never saw. Written as a test
    rather than trusted to a WHERE clause -- an unconditional DELETE satisfies
    every other assertion here.
    """
    assert run_alembic(["upgrade", _BEFORE], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            parent = await _seed_company(conn)
            child = await _seed_company(conn, parent_org_id=parent)
    finally:
        await engine.dispose()

    # Run only the backfill, then edit its row the way an owner would.
    assert run_alembic(["upgrade", _BACKFILL], fresh_db_url).returncode == 0

    chosen = uuid.uuid4()
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE llc_company_ceos SET holder_type = 'user', holder_user_id = :u, "
                    "holder_agent_id = NULL WHERE company_id = :c"
                ),
                {"u": chosen, "c": child},
            )
    finally:
        await engine.dispose()

    assert run_alembic(["upgrade", _AFTER], fresh_db_url).returncode == 0

    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT holder_type, holder_user_id FROM llc_company_ceos WHERE company_id = :c"),
                    {"c": child},
                )
            ).one_or_none()
    finally:
        await engine.dispose()

    assert row is not None, "the repair deleted a CEO a human had chosen"
    assert row.holder_type == "user"
    assert row.holder_user_id == chosen


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
