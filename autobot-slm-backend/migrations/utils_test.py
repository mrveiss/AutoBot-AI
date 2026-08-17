# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for migration helpers' table-awareness (#9785).

On a fresh DB the target table may not exist when add_column/create_index run
(migration ordering). The helpers must skip cleanly instead of emitting an
ALTER/CREATE that errors with 'relation "<t>" does not exist'.
"""

import pytest

from migrations import utils


@pytest.fixture(autouse=True)
def _clear_deferrals():
    """``_DEFERRED`` is module state, so without this the column tests above
    leak entries into the index assertions below and vice versa."""
    utils.reset_deferrals()
    yield
    utils.reset_deferrals()


class _FakeCursor:
    """Minimal psycopg2-cursor stub.

    `table_present` drives the table_exists() EXISTS probe; `columns` drives
    get_table_columns(). All executed statements are recorded for assertions.
    """

    def __init__(self, table_present: bool, columns=None, index_present=False):
        self._table_present = table_present
        self._columns = list(columns or [])
        self._index_present = index_present
        self.executed: list[str] = []
        self._last = ""

    def execute(self, sql, params=None):
        self.executed.append(sql)
        self._last = sql

    def fetchone(self):
        if "information_schema.tables" in self._last:
            return (self._table_present,)
        if "pg_indexes" in self._last:
            return (self._index_present,)
        return (None,)

    def fetchall(self):
        if "information_schema.columns" in self._last:
            return [(c,) for c in self._columns]
        return []

    def ran(self, fragment: str) -> bool:
        return any(fragment in s for s in self.executed)


def test_add_column_skips_when_table_absent():
    cur = _FakeCursor(table_present=False)
    assert utils.add_column_if_not_exists(cur, "nodes", "ssh_user", "VARCHAR(64)") is False
    assert not cur.ran("ALTER TABLE")  # no doomed ALTER on a missing table


def test_add_column_adds_when_table_present_and_column_missing():
    cur = _FakeCursor(table_present=True, columns=["id"])
    assert utils.add_column_if_not_exists(cur, "nodes", "ssh_user", "VARCHAR(64)") is True
    assert cur.ran("ALTER TABLE nodes ADD COLUMN ssh_user")


def test_add_column_noop_when_column_exists():
    cur = _FakeCursor(table_present=True, columns=["id", "ssh_user"])
    assert utils.add_column_if_not_exists(cur, "nodes", "ssh_user", "VARCHAR(64)") is False
    assert not cur.ran("ALTER TABLE")


def test_create_index_skips_when_table_absent():
    cur = _FakeCursor(table_present=False)
    assert utils.create_index_if_not_exists(cur, "ix_nodes_name", "nodes", "name") is False
    assert not cur.ran("CREATE INDEX")


def test_create_index_creates_when_table_present_and_index_missing():
    cur = _FakeCursor(table_present=True, index_present=False)
    assert utils.create_index_if_not_exists(cur, "ix_nodes_name", "nodes", "name") is True
    assert cur.ran("CREATE INDEX ix_nodes_name")


def test_create_index_records_a_deferral_when_the_table_is_absent():
    """The fix for #14327.

    Skipping is right (#9785) — an index on a missing table is a Postgres
    ERROR. Skipping *silently* is what made it permanent: the runner marks the
    migration applied, so the index is never created once the table appears, or
    when the table lives in a different database than the one the runner
    connects to. That is #14300's audit_logs scenario, for indexes.
    """
    cur = _FakeCursor(table_present=False)

    assert utils.create_index_if_not_exists(cur, "ix_nodes_name", "nodes", "name") is False
    assert not cur.ran("CREATE INDEX")
    assert utils.deferrals() == ["nodes.ix_nodes_name"]


def test_create_index_records_nothing_when_it_creates_the_index():
    """A deferral recorded on the success path would make every re-run refuse to
    mark the migration applied, forever — the mirror-image failure."""
    cur = _FakeCursor(table_present=True, index_present=False)

    assert utils.create_index_if_not_exists(cur, "ix_nodes_name", "nodes", "name") is True
    assert utils.deferrals() == []


def test_create_index_records_nothing_when_the_index_already_exists():
    cur = _FakeCursor(table_present=True, index_present=True)

    assert utils.create_index_if_not_exists(cur, "ix_nodes_name", "nodes", "name") is False
    assert not cur.ran("CREATE INDEX")
    assert utils.deferrals() == []


def test_both_helpers_feed_the_one_record_the_runner_reads():
    """The invariant, rather than either helper in isolation.

    ``run_all_migrations`` consults ``deferrals()`` and declines to mark a
    migration applied when it is non-empty. That gate is generic — it never
    asks which helper deferred. So the property that matters is that both
    helpers write to the same record; a helper that skips without recording is
    invisible to the gate no matter how correct the gate is.

    #14327 existed because only the column helper did.
    """
    cur = _FakeCursor(table_present=False)

    utils.add_column_if_not_exists(cur, "audit_logs", "updated_at", "TIMESTAMP")
    utils.create_index_if_not_exists(cur, "ix_audit_logs_updated_at", "audit_logs", "updated_at")

    assert utils.deferrals() == [
        "audit_logs.updated_at",
        "audit_logs.ix_audit_logs_updated_at",
    ]
