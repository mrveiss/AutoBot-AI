# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Two guards on the SQL MCP surface (#13520).

Both from the 2026-08-03 SQLi triage, which found **0 confirmed** injection
findings across 33 reports but noted two things worth tightening in the one file
that genuinely builds SQL by string interpolation.

**1. The read-only flag was consulted on `/mcp/execute` and not `/mcp/query`.**
Harmless as it stood — `SQLQueryRequest` already forbids anything but `SELECT`,
and the sync executor never commits — but it left the guarantee resting on a
single check. A read-only database should refuse a write regardless of which
endpoint asks, and regardless of a future edit relaxing the validator.

**2. The comment denylist rejected legitimate queries.** `--` and `/*` were
matched against the raw query text, so `WHERE note = '--'` or a path literal
containing `/*` was refused. Usability, not security — but a security control
that blocks ordinary work gets routed around, which is how it stops being a
control.

The relaxation only holds if literal-stripping **fails closed**, which is what
most of these tests are about: an unterminated quote must not let a real comment
token through.
"""

from __future__ import annotations

import pytest

from api.database_mcp import (
    _is_readonly_statement,
    _strip_sql_string_literals,
    validate_sql_query,
)

# --- literal stripping ------------------------------------------------------


def test_quoted_spans_are_blanked_but_length_is_preserved():
    out = _strip_sql_string_literals("SELECT * FROM t WHERE a = 'xx'")
    assert len(out) == len("SELECT * FROM t WHERE a = 'xx'")
    assert "xx" not in out
    assert out.startswith("SELECT * FROM t WHERE a = ")


def test_a_doubled_quote_escape_is_handled():
    """SQLite escapes a quote by doubling it: 'it''s'."""
    out = _strip_sql_string_literals("SELECT 'it''s' AS x")
    assert "AS x" in out, "the escape ended the literal early and ate the rest"


def test_unbalanced_quoting_returns_the_text_unchanged():
    """Fail closed: otherwise a trailing quote hides everything after it."""
    sql = "SELECT * FROM t WHERE a = 'unterminated -- DROP"
    assert _strip_sql_string_literals(sql) == sql


# --- the comment relaxation -------------------------------------------------


def test_a_comment_token_inside_a_literal_is_allowed():
    """The usability half: this is ordinary SQL, not an injection."""
    assert validate_sql_query("SELECT * FROM notes WHERE body = '--'") is True
    assert validate_sql_query("SELECT * FROM files WHERE path = '/*.py'") is True


def test_a_real_line_comment_is_still_blocked():
    assert validate_sql_query("SELECT * FROM t -- drop everything") is False


def test_a_real_block_comment_is_still_blocked():
    assert validate_sql_query("SELECT * FROM t /* hidden */") is False


def test_a_comment_after_an_unterminated_literal_is_still_blocked():
    """The case that makes fail-closed load-bearing.

    With naive stripping the trailing quote would put `-- ...` "inside a
    literal" and hide precisely what this check exists to catch.
    """
    assert validate_sql_query("SELECT * FROM t WHERE a = 'x -- DROP TABLE t") is False


def test_stacked_statements_are_still_blocked_regardless_of_quoting():
    """Only the comment tokens were relaxed; the rest still match raw text."""
    assert validate_sql_query("SELECT 1; DROP TABLE users") is False
    assert validate_sql_query("SELECT 1; DELETE FROM users") is False
    assert validate_sql_query("SELECT 1 ATTACH DATABASE '/tmp/x' AS y") is False


# --- the read-only gate -----------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    ["SELECT 1", "  select 1", "WITH t AS (SELECT 1) SELECT * FROM t", "EXPLAIN SELECT 1", "PRAGMA table_info(x)"],
)
def test_read_shapes_are_recognised(sql):
    assert _is_readonly_statement(sql) is True


@pytest.mark.parametrize(
    "sql", ["DELETE FROM t", "UPDATE t SET a = 1", "INSERT INTO t VALUES (1)", "DROP TABLE t", "VACUUM"]
)
def test_write_shapes_are_not(sql):
    assert _is_readonly_statement(sql) is False


def test_an_unrecognised_statement_is_treated_as_a_write():
    """Allow-list, not denylist: a keyword nobody thought of must fail closed."""
    assert _is_readonly_statement("REINDEX t") is False
    assert _is_readonly_statement("") is False
    assert _is_readonly_statement("   ") is False
