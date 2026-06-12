# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Phase E (#10026 / #10002): downgrade path stays exercised.

Matrix case (d): head → downgrade -1 → head. Guards against migrations whose
``downgrade()`` was never run anywhere (the upgrade path gets exercised by
every other case; the downgrade path only here).
"""

import pytest

from tests.migrations.conftest import (
    fetch_version_rows,
    requires_postgres,
    run_alembic,
    script_head,
)

pytestmark = [pytest.mark.migration_gate, requires_postgres]


async def test_downgrade_one_and_back_to_head(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0

    down = run_alembic(["downgrade", "-1"], fresh_db_url)
    assert down.returncode == 0, f"downgrade -1 from head failed:\nstdout:\n{down.stdout}\nstderr:\n{down.stderr}"
    assert await fetch_version_rows(fresh_db_url) != [script_head()]

    up = run_alembic(["upgrade", "head"], fresh_db_url)
    assert up.returncode == 0, f"re-upgrade after downgrade failed:\nstdout:\n{up.stdout}\nstderr:\n{up.stderr}"
    assert await fetch_version_rows(fresh_db_url) == [script_head()]
