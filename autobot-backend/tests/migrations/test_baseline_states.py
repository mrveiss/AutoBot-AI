# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Phase B (#10001): every branch of the baseline adoption state machine.

States (see migrations/baseline.py):
1. EMPTY            → exit 0, upgrade runs the full chain
2. STAMPED known    → exit 0, no-op
3. SCHEMA_NO_STAMP  → adopt (stamp head / probe-ladder bracket) or refuse (3)
4. STAMPED unknown  → refuse (4) unless in the compatibility table
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import pytest

from tests.migrations.conftest import (
    create_all_schema,
    drop_alembic_version,
    fetch_version_rows,
    requires_postgres,
    run_alembic,
    run_baseline,
    script_head,
)

pytestmark = [pytest.mark.migration_gate, requires_postgres]

OLD_REV = "20260315_010"  # deliberately old schema: process_runs era
PRE_LLC_REV = "20260522_021"


async def _exec(db_url: str, sql: str) -> None:
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(text(sql))
    await engine.dispose()


# ---------------------------------------------------------------- state 1


async def test_empty_db_proceeds(fresh_db_url):
    """State 1: empty database — baseline is a no-op, full chain applies."""
    result = run_baseline(fresh_db_url)
    assert result.returncode == 0, result.stderr
    assert "EMPTY" in result.stderr + result.stdout

    upgrade = run_alembic(["upgrade", "head"], fresh_db_url)
    assert upgrade.returncode == 0, upgrade.stderr
    assert await fetch_version_rows(fresh_db_url) == [script_head()]


# ---------------------------------------------------------------- state 2


async def test_stamped_at_head_noop(fresh_db_url):
    """State 2: a stamped database is left untouched."""
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    before = await fetch_version_rows(fresh_db_url)

    result = run_baseline(fresh_db_url)
    assert result.returncode == 0, result.stderr
    assert "STAMPED" in result.stderr + result.stdout
    assert await fetch_version_rows(fresh_db_url) == before


async def test_stamped_intermediate_noop(fresh_db_url):
    """State 2: an intermediate stamp is normal — upgrade continues from it.

    Also covers #10026 case 1 (intermediate-stamp upgrade with the repaired
    chain files).
    """
    assert run_alembic(["upgrade", PRE_LLC_REV], fresh_db_url).returncode == 0

    result = run_baseline(fresh_db_url)
    assert result.returncode == 0, result.stderr
    assert await fetch_version_rows(fresh_db_url) == [PRE_LLC_REV]

    upgrade = run_alembic(["upgrade", "head"], fresh_db_url)
    assert upgrade.returncode == 0, upgrade.stderr
    assert await fetch_version_rows(fresh_db_url) == [script_head()]


# ---------------------------------------------------------------- state 3


async def test_head_schema_unstamped_stamps_head(fresh_db_url):
    """State 3b: schema already at head — adopt by stamping head."""
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    await drop_alembic_version(fresh_db_url)

    result = run_baseline(fresh_db_url)
    assert result.returncode == 0, result.stderr
    assert await fetch_version_rows(fresh_db_url) == [script_head()]

    upgrade = run_alembic(["upgrade", "head"], fresh_db_url)
    assert upgrade.returncode == 0, upgrade.stderr


async def test_old_schema_bracketed_by_probe_ladder(fresh_db_url):
    """State 3c: deliberately old schema — ladder stamps the exact revision."""
    assert run_alembic(["upgrade", OLD_REV], fresh_db_url).returncode == 0
    await drop_alembic_version(fresh_db_url)

    result = run_baseline(fresh_db_url)
    assert result.returncode == 0, result.stderr
    assert await fetch_version_rows(fresh_db_url) == [OLD_REV], (
        "probe ladder must bracket a 010-era schema at exactly 20260315_010\n"
        f"stderr:\n{result.stderr}"
    )

    upgrade = run_alembic(["upgrade", "head"], fresh_db_url)
    assert upgrade.returncode == 0, upgrade.stderr
    assert await fetch_version_rows(fresh_db_url) == [script_head()]


async def test_dry_run_writes_nothing(fresh_db_url):
    """--dry-run reports the decision but never stamps."""
    assert run_alembic(["upgrade", OLD_REV], fresh_db_url).returncode == 0
    await drop_alembic_version(fresh_db_url)

    result = run_baseline(fresh_db_url, extra_args=["--dry-run"])
    assert result.returncode == 0, result.stderr
    assert OLD_REV in result.stderr + result.stdout
    assert await fetch_version_rows(fresh_db_url) == []


async def test_mixed_schema_refuses_loudly(fresh_db_url):
    """State 3d: a later revision's table on an old schema → refuse, exit 3."""
    assert run_alembic(["upgrade", PRE_LLC_REV], fresh_db_url).returncode == 0
    await drop_alembic_version(fresh_db_url)
    # Shell of llc_routines (created by 20260523_034) — schema now matches no
    # single point in the chain.
    await _exec(fresh_db_url, "CREATE TABLE llc_routines (id UUID PRIMARY KEY)")

    result = run_baseline(fresh_db_url)
    assert result.returncode == 3, (
        f"expected ambiguous-refusal exit 3, got {result.returncode}\n"
        f"stderr:\n{result.stderr}"
    )
    output = result.stderr + result.stdout
    assert "REFUSING" in output
    assert "docs/operations/migration-recovery.md" in output
    assert await fetch_version_rows(fresh_db_url) == [], "refusal must not stamp"


async def test_interleaved_create_all_refuses(fresh_db_url):
    """State 3d: current-code UM-only create_all interleaves with LLC revisions.

    Such a schema (LLC tables absent but post-LLC Base tables like
    push_subscriptions present) matches no chain point — any stamp would make
    `upgrade head` either collide or silently skip creations. Must refuse.
    """
    await create_all_schema(fresh_db_url)

    result = run_baseline(fresh_db_url)
    assert result.returncode == 3, (
        f"expected ambiguous-refusal exit 3, got {result.returncode}\n"
        f"stderr:\n{result.stderr}"
    )
    assert await fetch_version_rows(fresh_db_url) == []


# ---------------------------------------------------------------- state 4


async def test_unknown_revision_refuses(fresh_db_url):
    """State 4: a stamp the chain does not know → refuse, exit 4."""
    assert run_alembic(["upgrade", PRE_LLC_REV], fresh_db_url).returncode == 0
    await _exec(
        fresh_db_url,
        "UPDATE alembic_version SET version_num = 'deadbeef0001'",
    )

    result = run_baseline(fresh_db_url)
    assert result.returncode == 4, (
        f"expected foreign-revision exit 4, got {result.returncode}\n"
        f"stderr:\n{result.stderr}"
    )
    output = result.stderr + result.stdout
    assert "deadbeef0001" in output
    assert "docs/operations/migration-recovery.md" in output
    assert await fetch_version_rows(fresh_db_url) == ["deadbeef0001"], (
        "refusal must leave the foreign stamp untouched"
    )
