# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit_logs index builds run concurrently, outside any transaction (#17225)."""

import importlib.util
import pathlib

import pytest

pytest.importorskip("psycopg2")

_PATH = pathlib.Path(__file__).with_name("add_audit_logs_canonical_columns.py")


def _load():
    spec = importlib.util.spec_from_file_location("_audit_logs_columns_migration", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render(statement) -> str:
    """A ``psycopg2.sql.Composed`` as Postgres receives it: identifiers double-quoted."""
    from psycopg2 import sql

    if isinstance(statement, str):
        return statement
    parts = statement.seq if isinstance(statement, sql.Composed) else [statement]
    out = []
    for part in parts:
        if isinstance(part, sql.Identifier):
            out.append(".".join(f'"{s}"' for s in part.strings))
        else:
            out.append(part.string)
    return "".join(out)


class _Cursor:
    def __init__(self, conn, invalid):
        self.conn, self.invalid, self._row = conn, invalid, None

    def execute(self, sql, params=None):
        self.conn.log.append((self.conn.autocommit, _render(sql)))
        self._row = (1,) if params and params[0] in self.invalid else None

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, invalid=()):
        self.autocommit, self.log, self.invalid = False, [], set(invalid)

    def cursor(self):
        return _Cursor(self, self.invalid)


def test_every_index_statement_runs_concurrently_in_autocommit():
    conn = _Conn()
    _load().build_indexes_concurrently(conn)
    creates = [(auto, sql) for auto, sql in conn.log if sql.startswith("CREATE INDEX")]
    assert len(creates) == 2
    assert all(auto and "CONCURRENTLY IF NOT EXISTS" in sql for auto, sql in creates)


def test_an_invalid_leftover_index_is_rebuilt_not_kept():
    conn = _Conn(invalid={"ix_audit_logs_category"})
    _load().build_indexes_concurrently(conn)
    statements = [sql for _auto, sql in conn.log]
    drop = statements.index('DROP INDEX CONCURRENTLY IF EXISTS "ix_audit_logs_category"')
    assert statements[drop + 1].startswith("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_category")
    assert not any("DROP" in s and "idx_audit_actor_created" in s for s in statements)
