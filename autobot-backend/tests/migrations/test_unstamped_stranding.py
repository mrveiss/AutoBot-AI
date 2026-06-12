# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Phase A (#10001/#10026): reproduce the unstamped-database stranding.

Native deployments built their schema via ``metadata.create_all`` while the
Ansible alembic task silently failed (no ``-c migrations/alembic.ini`` +
``failed_when: false``). Those databases have a full schema and NO
``alembic_version`` stamp. 32 of 37 table-creating migrations use unguarded
``op.create_table``, so a strict ``alembic upgrade head`` aborts at migration
001 with DuplicateTable — making the invocation strict (#10026) before
baseline adoption exists (#10001) strands every such database.

Two tests:

* ``test_raw_upgrade_on_unstamped_schema_fails`` pins the stranding mechanism
  itself. It must stay green forever — if it ever fails, either migrations
  grew guards (good, update this file) or the reproduction environment broke.
* ``test_bootstrap_adopts_unstamped_schema_and_reaches_head`` runs the
  production bootstrap sequence (baseline adoption, then upgrade). RED until
  the Phase B baseline logic exists; it is the acceptance test for #10001.
"""

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

# The newest revision whose schema a pre-LLC code version's create_all would
# have produced — the realistic stranded-fleet shape (#10026 case 3).
PRE_LLC_REV = "20260522_021"

pytestmark = [pytest.mark.migration_gate, requires_postgres]


async def test_raw_upgrade_on_unstamped_schema_fails(fresh_db_url):
    """An unstamped create_all-built DB cannot run `upgrade head` directly.

    This documents WHY the baseline step must run first: alembic starts the
    full chain from base and migration 001's unguarded create_table collides
    with the existing schema.
    """
    await create_all_schema(fresh_db_url)
    assert await fetch_version_rows(fresh_db_url) == []

    result = run_alembic(["upgrade", "head"], fresh_db_url)

    assert result.returncode != 0, (
        "upgrade head unexpectedly succeeded on an unstamped populated DB — "
        "if migrations became fully guarded, re-evaluate the baseline design.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = (result.stdout + result.stderr).lower()
    assert "already exists" in combined or "duplicatetable" in combined, (
        "expected a relation-already-exists failure, got:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # The failed run must not have stamped anything — the DB stays adoptable.
    assert await fetch_version_rows(fresh_db_url) == []


async def test_bootstrap_adopts_unstamped_schema_and_reaches_head(fresh_db_url):
    """The production bootstrap (baseline → upgrade) adopts an unstamped DB.

    Acceptance test for #10001: a pre-LLC-era schema (exactly what an old
    code-version's create_all built) with no alembic_version is bracketed by
    the probe ladder, stamped, and `upgrade head` then completes the
    remainder of the chain.
    """
    build = run_alembic(["upgrade", PRE_LLC_REV], fresh_db_url)
    assert build.returncode == 0, f"fixture build failed:\n{build.stderr}"
    await drop_alembic_version(fresh_db_url)
    assert await fetch_version_rows(fresh_db_url) == []

    baseline = run_baseline(fresh_db_url)
    assert baseline.returncode == 0, (
        "baseline adoption failed on a bracketable unstamped legacy DB:\n"
        f"stdout:\n{baseline.stdout}\nstderr:\n{baseline.stderr}"
    )

    upgrade = run_alembic(["upgrade", "head"], fresh_db_url)
    assert upgrade.returncode == 0, (
        f"upgrade head failed after baseline adoption:\n"
        f"stdout:\n{upgrade.stdout}\nstderr:\n{upgrade.stderr}"
    )

    assert await fetch_version_rows(fresh_db_url) == [script_head()]
