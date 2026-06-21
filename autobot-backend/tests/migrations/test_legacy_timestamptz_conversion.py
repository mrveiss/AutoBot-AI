# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Case 2 of #10026 (umbrella #9920): 018 TIMESTAMPTZ conversion on legacy naive tables.

The skills/process_run tables (``process_runs``, ``agent_sessions``, ``skill_*``) are
``create_all``-only — no migration creates them (#9759). Migration 018 converts their
naive ``TIMESTAMP`` columns to ``TIMESTAMPTZ`` *when the table is present*, and skips it
*when absent* (the current tz-aware models build them post-018 already).

The untested fleet state (#10026 case 2): a database where an **old** ``create_all`` built
those tables in pre-#9989 **naive** shape and the DB is stamped **before** 018. Here 018
must run the conversion against the legacy naive columns, and a tz-aware datetime must then
round-trip with its offset intact. This asserts that data-correctness directly.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_PRE_018 = "20260324_017"  # 018.down_revision
_REV_018 = "20260422_018"

# 018's 8 (table, column) naive→TIMESTAMPTZ conversions.
_NAIVE_TABLES: dict[str, list[str]] = {
    "process_runs": ["started_at", "completed_at"],
    "agent_sessions": ["expires_at"],
    "skill_packages": ["created_at", "promoted_at"],
    "skill_repos": ["last_synced"],
    "skill_approvals": ["requested_at", "reviewed_at"],
}


async def _seed_absent_create_all_tables(url: str) -> None:
    """Build the genuinely create_all-only tables (skill_*) in pre-#9989 naive shape.

    ``process_runs`` / ``agent_sessions`` are migration-created and are already naive at
    rev 017, so they need no seeding; the ``skill_*`` tables are create_all-only (absent
    from the migration-built schema) — recreate them naive to model a legacy fleet DB.
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            for table, cols in _NAIVE_TABLES.items():
                present = (await conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"})).scalar()
                if present is not None:
                    continue  # migration-created, already naive at 017
                coldefs = ", ".join(f"{c} TIMESTAMP" for c in cols)  # naive — no time zone
                await conn.execute(text(f"CREATE TABLE {table} (id TEXT PRIMARY KEY, {coldefs})"))
    finally:
        await engine.dispose()


async def _column_type(url: str, table: str, column: str) -> str:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT data_type FROM information_schema.columns " "WHERE table_name = :t AND column_name = :c"),
                {"t": table, "c": column},
            )
            return result.scalar()
    finally:
        await engine.dispose()


async def test_018_converts_legacy_naive_columns(fresh_db_url):
    # Legacy fleet state: migration-created process_runs/agent_sessions are naive at 017, and
    # the create_all-only skill_* tables existed naive — all stamped pre-018.
    assert run_alembic(["upgrade", _PRE_018], fresh_db_url).returncode == 0
    await _seed_absent_create_all_tables(fresh_db_url)
    # precondition: a migration-created table's column is naive before 018
    assert await _column_type(fresh_db_url, "process_runs", "started_at") == "timestamp without time zone"

    result = run_alembic(["upgrade", _REV_018], fresh_db_url)
    assert result.returncode == 0, result.stderr

    # every one of 018's 8 columns is now timezone-aware
    for table, cols in _NAIVE_TABLES.items():
        for column in cols:
            assert await _column_type(fresh_db_url, table, column) == "timestamp with time zone", f"{table}.{column}"


async def test_018_tz_aware_datetime_round_trips_on_converted_column(fresh_db_url):
    assert run_alembic(["upgrade", _PRE_018], fresh_db_url).returncode == 0
    await _seed_absent_create_all_tables(fresh_db_url)
    assert run_alembic(["upgrade", _REV_018], fresh_db_url).returncode == 0

    # round-trip on a create_all-only table we control (skill_packages, id TEXT) after conversion
    stamped = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("INSERT INTO skill_packages (id, created_at) VALUES ('p1', :ts)"), {"ts": stamped})
        async with engine.connect() as conn:
            got = (await conn.execute(text("SELECT created_at FROM skill_packages WHERE id = 'p1'"))).scalar()
    finally:
        await engine.dispose()

    assert got.tzinfo is not None  # converted column preserves the offset
    assert got == stamped
