# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Regression tests for SQL-injection hardening of identifier interpolation.

Covers the fixes for CodeQL/semgrep ``autobot-sql-string-format`` alerts
(Issue #12284): identifiers that cannot be bound as parameters are validated
against a strict allowlist (SQLite value queries) or safely quoted/escaped
(SQLite/MySQL identifier grammar) so SQL metacharacters are treated as data,
never executed.

Direct unit tests for the allowlist validator itself now live alongside its
single shared implementation at
``autobot_shared/security/sql_identifier_test.py`` (#13393). This module keeps
only the tests that exercise the validator indirectly through
``DatabaseUtils`` and the migration-quoting helper.
"""

import importlib.util
import sqlite3
from pathlib import Path

from utils.common import DatabaseUtils

# Payload containing SQL metacharacters that must never be executed.
INJECTION = "widgets; DROP TABLE widgets;--"


def _seed_db() -> sqlite3.Connection:
    """Return an in-memory DB with a 'widgets' table holding three rows."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany(
        "INSERT INTO widgets (name) VALUES (?)",
        [("a",), ("b",), ("c",)],
    )
    conn.commit()
    return conn


def test_get_table_row_count_returns_correct_result():
    """A valid identifier yields the true row count."""
    conn = _seed_db()
    try:
        assert DatabaseUtils.get_table_row_count(conn, "widgets") == 3
    finally:
        conn.close()


def test_get_table_row_count_treats_metacharacters_as_data():
    """A metacharacter-laden name is rejected, not executed as SQL."""
    conn = _seed_db()
    try:
        # Malicious name fails allowlist validation -> caught -> 0.
        assert DatabaseUtils.get_table_row_count(conn, INJECTION) == 0
        # Crucially, the injected drop never ran: the table still holds 3 rows.
        remaining = conn.execute("SELECT COUNT(*) FROM widgets").fetchone()[0]
        assert remaining == 3
    finally:
        conn.close()


def _load_migration_module():
    """Import the 001 migration module (non-identifier filename) by path."""
    path = Path(__file__).resolve().parent.parent / "database" / "migrations" / "001_create_conversation_files.py"
    spec = importlib.util.spec_from_file_location("migration_001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quote_sqlite_identifier_neutralises_injection():
    """Quoting doubles embedded quotes so a malicious name stays a name."""
    module = _load_migration_module()
    quote = module._quote_sqlite_identifier
    # Simple names round-trip unchanged in meaning (just quoted).
    assert quote("widgets") == chr(34) + "widgets" + chr(34)
    # A crafted name with a closing quote + statement is fully contained.
    crafted = 'v"; DROP TABLE t;--'
    quoted = quote(crafted)
    assert quoted.startswith(chr(34)) and quoted.endswith(chr(34))
    # Embedded double-quote is escaped by doubling, so it cannot terminate.
    assert chr(34) + chr(34) in quoted

    # Prove it in a real engine: a view whose name contains metacharacters can
    # be dropped via the quoted identifier without executing the payload.
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE t (id INTEGER)")
        # `quoted` is the escaped output of the function under test; the identifier
        # is safely double-quoted (metacharacters inert) and can't be bind-parameterized. (#12284)
        conn.execute(f"CREATE VIEW {quoted} AS SELECT 1")  # nosemgrep: autobot-sql-string-format
        # Same quoted identifier; the assertion below proves the payload never executed. (#12284)
        conn.execute(f"DROP VIEW IF EXISTS {quoted}")  # nosemgrep: autobot-sql-string-format
        conn.commit()
        # Table t survived: the injected drop never executed.
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='t'").fetchone() is not None
    finally:
        conn.close()
