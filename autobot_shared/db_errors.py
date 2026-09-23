# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Classify a database integrity error into the HTTP answer it deserves (#15775).

A constraint violation that reaches the application unhandled is currently a
500: unactionable for the caller, retried blindly by agents (a 500 reads as
"try again", a 409 does not), and indistinguishable from a real fault in the
logs. The status code is the whole payload of information here — *which*
constraint failed decides whether the caller sent a duplicate (409), pointed at
a row that does not exist (422), or omitted something required (422).

TWO DIALECTS, ONE CODE PATH
---------------------------
Production is PostgreSQL and the test suite runs SQLite, so a classifier that
reads only ``sqlstate`` would be exercised nowhere in CI and a classifier that
reads only SQLite's message text would be wrong in production. Both are read:
the SQLSTATE when the driver provides one, the message prefix when it does not.
``user_service_conflict.py`` records the same constraint for the savepoint it
uses (#15772).

THIS IS A FLOOR, NOT A REPLACEMENT
----------------------------------
A route that catches ``IntegrityError`` itself keeps its own answer, and should:
only the call site knows *which field* collided, and only a SAVEPOINT taken at
the insert leaves the session usable afterwards -- by the time an app-level
handler sees the error, the transaction is already poisoned and nothing
downstream in that request can proceed. What this module removes is the 500
that arrives when nobody handled it at all (#15736, #15752, #15772).
"""

from __future__ import annotations

from enum import Enum
from typing import Iterator

#: PostgreSQL integrity SQLSTATEs (class 23) plus the malformed-literal code
#: that a bad UUID reaches the database as.
_PG_UNIQUE_VIOLATION = "23505"
_PG_FOREIGN_KEY_VIOLATION = "23503"
_PG_NOT_NULL_VIOLATION = "23502"
_PG_CHECK_VIOLATION = "23514"
_PG_INVALID_TEXT_REPRESENTATION = "22P02"

#: SQLite has no SQLSTATE; its DBAPI message is the only signal, and these
#: prefixes are stable across the versions this repository supports.
_SQLITE_PREFIXES = (
    ("UNIQUE constraint failed", "UNIQUE"),
    ("FOREIGN KEY constraint failed", "FOREIGN_KEY"),
    ("NOT NULL constraint failed", "NOT_NULL"),
    ("CHECK constraint failed", "CHECK"),
)


class IntegrityKind(str, Enum):
    """What the database refused, in terms the HTTP layer can answer with."""

    UNIQUE = "UNIQUE"
    FOREIGN_KEY = "FOREIGN_KEY"
    NOT_NULL = "NOT_NULL"
    CHECK = "CHECK"
    MALFORMED_VALUE = "MALFORMED_VALUE"
    UNKNOWN = "UNKNOWN"


#: The status each kind answers with. A duplicate is a conflict the caller can
#: resolve by choosing another value; the rest are unprocessable content. UNKNOWN
#: stays 500 deliberately -- guessing 4xx for a constraint nobody classified
#: would tell the caller their request was wrong when the truth is that we do
#: not know.
_STATUS_BY_KIND = {
    IntegrityKind.UNIQUE: 409,
    IntegrityKind.FOREIGN_KEY: 422,
    IntegrityKind.NOT_NULL: 422,
    IntegrityKind.CHECK: 422,
    IntegrityKind.MALFORMED_VALUE: 422,
    IntegrityKind.UNKNOWN: 500,
}

#: Generic, caller-facing text. Never the driver message: it names tables,
#: columns and constraints, which is schema disclosure to an unauthenticated
#: error path.
_DETAIL_BY_KIND = {
    IntegrityKind.UNIQUE: "A resource with these values already exists",
    IntegrityKind.FOREIGN_KEY: "A referenced resource does not exist",
    IntegrityKind.NOT_NULL: "A required value is missing",
    IntegrityKind.CHECK: "A value is outside the range this resource allows",
    IntegrityKind.MALFORMED_VALUE: "A value is not in the expected format",
    IntegrityKind.UNKNOWN: "Internal server error",
}


def iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    """Every exception reachable from *exc*, each yielded once.

    SQLAlchemy wraps the driver error in ``orig``, and ``raise ... from`` adds
    ``__cause__``/``__context__``, so the SQLSTATE is rarely on the exception
    the handler was given. Cycles are possible once ``__context__`` is involved,
    hence the identity set rather than a plain recursion.
    """
    seen: set[int] = set()
    stack: list[BaseException | None] = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        stack.extend((current.__cause__, current.__context__, getattr(current, "orig", None)))


def sqlstate_of(exc: BaseException) -> str | None:
    """The first SQLSTATE found anywhere in *exc*'s chain, if any."""
    for current in iter_exception_chain(exc):
        sqlstate = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if isinstance(sqlstate, str) and sqlstate:
            return sqlstate
    return None


def classify_integrity_error(exc: BaseException) -> IntegrityKind:
    """Which constraint *exc* violated, read from either dialect."""
    sqlstate = sqlstate_of(exc)
    by_sqlstate = {
        _PG_UNIQUE_VIOLATION: IntegrityKind.UNIQUE,
        _PG_FOREIGN_KEY_VIOLATION: IntegrityKind.FOREIGN_KEY,
        _PG_NOT_NULL_VIOLATION: IntegrityKind.NOT_NULL,
        _PG_CHECK_VIOLATION: IntegrityKind.CHECK,
        _PG_INVALID_TEXT_REPRESENTATION: IntegrityKind.MALFORMED_VALUE,
    }
    if sqlstate in by_sqlstate:
        return by_sqlstate[sqlstate]

    for current in iter_exception_chain(exc):
        message = str(current)
        for prefix, kind in _SQLITE_PREFIXES:
            if prefix in message:
                return IntegrityKind(kind)
    return IntegrityKind.UNKNOWN


def status_for(kind: IntegrityKind) -> int:
    """HTTP status for *kind*; 500 when the constraint went unclassified."""
    return _STATUS_BY_KIND[kind]


def detail_for(kind: IntegrityKind) -> str:
    """Caller-facing text for *kind* -- generic by construction."""
    return _DETAIL_BY_KIND[kind]
