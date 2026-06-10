# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for migration helpers' table-awareness (#9785).

On a fresh DB the target table may not exist when add_column/create_index run
(migration ordering). The helpers must skip cleanly instead of emitting an
ALTER/CREATE that errors with 'relation "<t>" does not exist'.
"""

from migrations import utils


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
