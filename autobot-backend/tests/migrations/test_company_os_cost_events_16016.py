# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration 20261031_106 -- per-event cost rows: the downgrade refuses to drop data (#16016).

Runs on SQLite through alembic's own ``Operations`` so the real ``upgrade``/``downgrade``
bodies execute; the Postgres chain tests cover the table in the full migration history.
"""

import importlib

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

migration = importlib.import_module("migrations.versions.20261031_106_company_os_cost_events")


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            yield connection


def test_upgrade_creates_the_table_and_is_idempotent(conn):
    migration.upgrade()
    migration.upgrade()
    assert sa.inspect(conn).has_table("company_os_cost_events")
    assert migration.down_revision == "20261030_105"


def test_downgrade_refuses_while_events_exist_then_drops_when_empty(conn):
    migration.upgrade()
    conn.execute(
        sa.text(
            "INSERT INTO company_os_cost_events"
            " (id, company_id, agent_id, model, tokens_in, tokens_out, cost, created_at, updated_at)"
            " VALUES ('00000000000000000000000000000001', 'c', 'a', 'm', 1, 1, 0.5, '2026-10-31', '2026-10-31')"
        )
    )
    with pytest.raises(NotImplementedError, match="1 cost event"):
        migration.downgrade()
    assert sa.inspect(conn).has_table("company_os_cost_events")
    conn.execute(sa.text("DELETE FROM company_os_cost_events"))
    migration.downgrade()
    assert not sa.inspect(conn).has_table("company_os_cost_events")
