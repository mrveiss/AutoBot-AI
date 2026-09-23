# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Constraint classification, on both dialects (#15775).

SQLite errors are raised by a real SQLite, not constructed: the message text is
the only signal that dialect gives, so a hand-written fixture would be testing
this module against my memory of SQLite rather than against SQLite. The
PostgreSQL side has no driver in the test environment, so its SQLSTATE carrier
is a stand-in -- which is honest, because the only thing this module reads from
a psycopg error is the ``sqlstate`` attribute.
"""

from __future__ import annotations

import sqlite3

import pytest

from autobot_shared.db_errors import (
    IntegrityKind,
    classify_integrity_error,
    detail_for,
    iter_exception_chain,
    sqlstate_of,
    status_for,
)


def _sqlite_error(setup: str, *rows: str) -> sqlite3.IntegrityError:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for statement in setup.split(";"):
        if statement.strip():
            connection.execute(statement)
    with pytest.raises(sqlite3.IntegrityError) as exc:
        for row in rows:
            connection.execute(row)
    return exc.value


class _PsycopgLike(Exception):
    """Stands in for the driver error: sqlstate is all this module reads."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"driver error {sqlstate}")
        self.sqlstate = sqlstate


class _SQLAlchemyLike(Exception):
    """Stands in for the SQLAlchemy wrapper, which carries ``orig``."""

    def __init__(self, orig: BaseException) -> None:
        super().__init__("(wrapped) constraint violation")
        self.orig = orig


class TestSQLite:
    def test_unique_violation_is_a_conflict(self):
        error = _sqlite_error(
            "CREATE TABLE t (a TEXT UNIQUE)", "INSERT INTO t VALUES ('x')", "INSERT INTO t VALUES ('x')"
        )

        assert classify_integrity_error(error) is IntegrityKind.UNIQUE
        assert status_for(IntegrityKind.UNIQUE) == 409

    def test_not_null_violation_is_unprocessable(self):
        error = _sqlite_error("CREATE TABLE t (a TEXT NOT NULL)", "INSERT INTO t VALUES (NULL)")

        assert classify_integrity_error(error) is IntegrityKind.NOT_NULL
        assert status_for(IntegrityKind.NOT_NULL) == 422

    def test_foreign_key_violation_is_unprocessable(self):
        error = _sqlite_error(
            "CREATE TABLE parent (id INTEGER PRIMARY KEY); CREATE TABLE child (p INTEGER REFERENCES parent(id))",
            "INSERT INTO child VALUES (999)",
        )

        assert classify_integrity_error(error) is IntegrityKind.FOREIGN_KEY
        assert status_for(IntegrityKind.FOREIGN_KEY) == 422


class TestPostgresSQLState:
    @pytest.mark.parametrize(
        ("sqlstate", "kind"),
        [
            ("23505", IntegrityKind.UNIQUE),
            ("23503", IntegrityKind.FOREIGN_KEY),
            ("23502", IntegrityKind.NOT_NULL),
            ("23514", IntegrityKind.CHECK),
            ("22P02", IntegrityKind.MALFORMED_VALUE),
        ],
    )
    def test_sqlstate_decides(self, sqlstate: str, kind: IntegrityKind):
        assert classify_integrity_error(_PsycopgLike(sqlstate)) is kind

    def test_sqlstate_is_found_through_the_sqlalchemy_wrapper(self):
        """The handler is never given the driver error directly."""
        wrapped = _SQLAlchemyLike(_PsycopgLike("23505"))

        assert sqlstate_of(wrapped) == "23505"
        assert classify_integrity_error(wrapped) is IntegrityKind.UNIQUE

    def test_sqlstate_is_found_through_a_raise_from_chain(self):
        try:
            try:
                raise _PsycopgLike("23503")
            except _PsycopgLike as cause:
                raise RuntimeError("service layer") from cause
        except RuntimeError as exc:
            assert classify_integrity_error(exc) is IntegrityKind.FOREIGN_KEY


class TestUnknownStaysA500:
    def test_an_unclassified_error_is_not_guessed_into_a_4xx(self):
        """Telling a caller their request was wrong when we do not know is worse
        than admitting the server does not know."""
        assert classify_integrity_error(RuntimeError("something else entirely")) is IntegrityKind.UNKNOWN
        assert status_for(IntegrityKind.UNKNOWN) == 500

    def test_an_unknown_sqlstate_is_not_forced_into_a_kind(self):
        assert classify_integrity_error(_PsycopgLike("42P01")) is IntegrityKind.UNKNOWN


class TestDisclosure:
    def test_no_caller_facing_detail_names_a_table_or_constraint(self):
        error = _sqlite_error(
            "CREATE TABLE users (email TEXT UNIQUE)",
            "INSERT INTO users VALUES ('a@b')",
            "INSERT INTO users VALUES ('a@b')",
        )
        kind = classify_integrity_error(error)

        assert "users" in str(error), "precondition: the driver message does name the table"
        assert "users" not in detail_for(kind)
        assert "email" not in detail_for(kind)

    def test_every_kind_has_a_generic_detail(self):
        for kind in IntegrityKind:
            assert detail_for(kind), f"{kind} has no caller-facing text"


class TestChainWalk:
    def test_a_cycle_terminates(self):
        """__context__ can point back; the walk must not spin on it."""
        first, second = RuntimeError("first"), RuntimeError("second")
        first.__context__ = second
        second.__context__ = first

        assert len(list(iter_exception_chain(first))) == 2
