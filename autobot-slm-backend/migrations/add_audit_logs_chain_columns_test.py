# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM's audit-chain migration rewrites no row and builds its index concurrently (#17219)."""

import importlib.util
import pathlib
from unittest.mock import MagicMock

import pytest

pytest.importorskip("psycopg2")

_PATH = pathlib.Path(__file__).with_name("add_audit_logs_chain_columns.py")
_CHAIN_COLUMNS = {"chain_seq", "prev_hash", "row_hash", "row_mac", "key_id", "org_ref"}


def _load():
    spec = importlib.util.spec_from_file_location("_audit_logs_chain_migration", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render(statement) -> str:
    """A ``psycopg2.sql.Composed`` as Postgres receives it: identifiers double-quoted."""
    from psycopg2 import sql

    if isinstance(statement, str):
        return statement
    parts = statement.seq if isinstance(statement, sql.Composed) else [statement]
    return "".join(".".join(f'"{s}"' for s in p.strings) if isinstance(p, sql.Identifier) else p.string for p in parts)


def _conn(invalid=()):
    """A connection whose cursor logs ``(autocommit, statement)`` and reports *invalid* index names as INVALID."""
    conn = MagicMock(autocommit=False, log=[])
    cursor = MagicMock()

    def _execute(statement, params=None):
        conn.log.append((conn.autocommit, _render(statement)))
        cursor.fetchone.return_value = (1,) if params and params[0] in set(invalid) else None

    cursor.execute.side_effect = _execute
    conn.cursor.return_value = cursor
    return conn


def test_the_index_is_a_partial_unique_concurrent_build_in_autocommit() -> None:
    conn = _conn()
    _load().build_index_concurrently(conn)
    creates = [(auto, sql) for auto, sql in conn.log if sql.startswith("CREATE")]
    assert len(creates) == 1 and creates[0][0] is True
    assert "UNIQUE INDEX CONCURRENTLY IF NOT EXISTS" in creates[0][1] and "WHERE chain_seq IS NOT NULL" in creates[0][1]


def test_an_invalid_leftover_index_is_rebuilt_not_kept() -> None:
    conn = _conn(invalid={"uq_audit_logs_chain_seq"})
    _load().build_index_concurrently(conn)
    statements = [sql for _auto, sql in conn.log]
    drop = statements.index('DROP INDEX CONCURRENTLY IF EXISTS "uq_audit_logs_chain_seq"')
    assert statements[drop + 1].startswith("CREATE UNIQUE INDEX CONCURRENTLY")


def test_the_migration_adds_nullable_columns_without_defaults_and_rewrites_no_row() -> None:
    module = _load()
    assert {name for name, _ddl in module._COLUMNS} == _CHAIN_COLUMNS
    assert all("NOT NULL" not in ddl and "DEFAULT" not in ddl for _name, ddl in module._COLUMNS)
    source = _PATH.read_text(encoding="utf-8")
    assert not any(verb in source.upper() for verb in ("UPDATE AUDIT_LOGS", "DELETE FROM", "DROP COLUMN", "DROP TABLE"))


def test_the_migration_runs_on_the_user_management_database_and_is_registered() -> None:
    from migrations.runner import MIGRATIONS, TARGET_DB_USER_MANAGEMENT

    assert _load().TARGET_DB == TARGET_DB_USER_MANAGEMENT
    assert "add_audit_logs_chain_columns" in MIGRATIONS
