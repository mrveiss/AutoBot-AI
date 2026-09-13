# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ``secrets_audit`` table: schema, writes and reads (#15023).

Extracted from ``secrets_service.py`` because AC3 of #15023 needs the audit trail
to record *failed* credential access, and a lookup that found nothing has no
``secrets(id)`` to record against: the column was ``TEXT NOT NULL`` with a
foreign key to a row that, for a miss, does not exist by definition.

**Schema change.** ``secrets_audit.secret_id`` becomes nullable. The foreign key
stays -- SQLite treats a NULL child column as satisfying it -- so a row that
*does* name a secret is constrained exactly as before, and the rows already on
disk are carried across verbatim by ``_relax_secret_id_not_null``.

**Reversibility.** The widening is backward-compatible at the code level: every
pre-#15023 write supplies a non-NULL ``secret_id`` and every read is a plain
``SELECT``, so rolling the code back needs no schema revert and loses nothing.
A schema revert is deliberately *not* offered -- restoring ``NOT NULL`` would
mean deleting the failed-access rows, and destroying audit history to undo a
widening is not a rollback.

**Never record a credential value.** ``record_failed_access`` takes no value
parameter and ``AuditLookup`` carries only lookup keys -- the name, id, scope and
chat id a caller asked *for*, plus who asked -- so there is no argument through
which a decrypted secret, or anything derived from one (a prefix, a length, a
hash), can reach a row. That is structural rather than a convention: #15080 is
the precedent for a helper that leaked key fragments through its own strings.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Dict, List
from uuid import uuid4

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

#: Action recorded for an access that yielded a secret.
ACTION_ACCESSED = "accessed"
#: Action recorded when an attributable access yielded nothing usable (#15023 AC3).
ACTION_ACCESS_FAILED = "access_failed"

#: Why an access failed. Distinct values because "no such entry" and "the entry
#: expired" are the same ``None`` to the caller and must not be the same row to
#: an auditor -- telling them apart is the point of the failure limb.
REASON_NOT_FOUND = "not_found"
REASON_EXPIRED = "expired"
REASON_TYPE_MISMATCH = "type_mismatch"
REASON_MALFORMED_VALUE = "malformed_value"
REASON_LOOKUP_ERROR = "lookup_error"

#: Every accepted reason. ``build_failure_details`` rejects anything else rather
#: than writing a row whose reason no reader knows how to interpret.
FAILURE_REASONS = (
    REASON_NOT_FOUND,
    REASON_EXPIRED,
    REASON_TYPE_MISMATCH,
    REASON_MALFORMED_VALUE,
    REASON_LOOKUP_ERROR,
)

_CREATE_AUDIT_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS secrets_audit (
        id TEXT PRIMARY KEY,
        secret_id TEXT,
        action TEXT NOT NULL,
        performed_by TEXT,
        performed_at TEXT NOT NULL,
        details TEXT,
        FOREIGN KEY (secret_id) REFERENCES secrets(id)
    )
"""

_INSERT_AUDIT_SQL = (
    "INSERT INTO secrets_audit (id, secret_id, action, performed_by, performed_at, details) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

_SELECT_AUDIT_SQL = (
    "SELECT id, secret_id, action, performed_by, performed_at, details "
    "FROM secrets_audit ORDER BY performed_at DESC LIMIT ?"
)

_SELECT_AUDIT_FOR_ID_SQL = (
    "SELECT id, secret_id, action, performed_by, performed_at, details "
    "FROM secrets_audit WHERE secret_id = ? ORDER BY performed_at DESC LIMIT ?"
)

#: The four statements of the rebuild in ``_relax_secret_id_not_null``, which
#: parks the pre-#15023 table under ``secrets_audit_pre_nullable_secret_id``,
#: recreates it widened, copies every row back, and discards the parked copy.
#:
#: Each is a complete literal, not composed from a table-name variable or a
#: shared column list. SQLite cannot bind an *identifier* -- a table or column
#: name is never a ``?`` parameter -- so "use a parameterised query" has no
#: form to take for these four, and interpolating instead would leave SQL built
#: by string formatting for a scanner to flag and a reader to have to prove
#: safe. The table and its six columns are fixed and known at author time, so
#: the honest shape is a literal with nothing to inject into. It also leaves the
#: migration auditable by reading it, which matters more for a rebuild of the
#: table holding audit history than for any other statement in this module.
_MIGRATION_PARK_TABLE_SQL = "ALTER TABLE secrets_audit RENAME TO secrets_audit_pre_nullable_secret_id"

_MIGRATION_COPY_ROWS_SQL = (
    "INSERT INTO secrets_audit (id, secret_id, action, performed_by, performed_at, details) "
    "SELECT id, secret_id, action, performed_by, performed_at, details "
    "FROM secrets_audit_pre_nullable_secret_id"
)

_MIGRATION_COUNT_PARKED_SQL = "SELECT COUNT(*) FROM secrets_audit_pre_nullable_secret_id"

_MIGRATION_COUNT_REBUILT_SQL = "SELECT COUNT(*) FROM secrets_audit"

_MIGRATION_DISCARD_PARKED_SQL = "DROP TABLE secrets_audit_pre_nullable_secret_id"


@dataclass(frozen=True)
class AuditLookup:
    """What a caller asked for, and who asked -- never what came back.

    Deliberately has no field for a secret's value. See the module docstring:
    the absence is the guarantee.
    """

    name: str | None = None
    secret_id: str | None = None
    scope: str = "general"
    chat_id: str | None = None
    performed_by: str | None = None


def _secret_id_is_not_null(cursor: sqlite3.Cursor) -> bool:
    """True when this database still has the pre-#15023 ``NOT NULL`` column."""
    cursor.execute("PRAGMA table_info(secrets_audit)")
    for column in cursor.fetchall():
        if column[1] == "secret_id":
            return bool(column[3])
    return False


def _relax_secret_id_not_null(cursor: sqlite3.Cursor) -> None:
    """Rebuild ``secrets_audit`` with a nullable ``secret_id``, carrying every row.

    SQLite cannot drop ``NOT NULL`` in place, so this is the rename/copy/discard
    rebuild. It runs inside one explicit transaction: Python's sqlite3 leaves DDL
    in autocommit, and a rebuild whose rename autocommits would, if interrupted,
    leave the history parked under another name with an empty table in its place.
    The row count is compared before the parked table goes -- a copy that lost
    rows aborts the transaction instead of completing.
    """
    conn = cursor.connection
    own_transaction = not conn.in_transaction
    if own_transaction:
        cursor.execute("BEGIN IMMEDIATE")
    try:
        cursor.execute(_MIGRATION_PARK_TABLE_SQL)
        cursor.execute(_CREATE_AUDIT_TABLE_SQL)
        cursor.execute(_MIGRATION_COPY_ROWS_SQL)
        cursor.execute(_MIGRATION_COUNT_PARKED_SQL)
        carried = cursor.fetchone()[0]
        cursor.execute(_MIGRATION_COUNT_REBUILT_SQL)
        if cursor.fetchone()[0] != carried:
            raise sqlite3.IntegrityError("secrets_audit rebuild would lose audit rows; refusing to complete")
        cursor.execute(_MIGRATION_DISCARD_PARKED_SQL)
    except Exception:
        if own_transaction:
            conn.rollback()
        raise
    if own_transaction:
        conn.commit()
    logger.info("Migrated secrets_audit to a nullable secret_id (%d existing rows carried)", carried)


def ensure_audit_schema(cursor: sqlite3.Cursor) -> None:
    """Create the audit table, and widen a pre-#15023 one already on disk."""
    cursor.execute(_CREATE_AUDIT_TABLE_SQL)
    if _secret_id_is_not_null(cursor):
        _relax_secret_id_not_null(cursor)


def record_action(
    cursor: sqlite3.Cursor,
    secret_id: str | None,
    action: str,
    performed_by: str | None = None,
    details: Dict | None = None,
) -> None:
    """Append one audit row. ``secret_id`` is None only for a failed access."""
    cursor.execute(
        _INSERT_AUDIT_SQL,
        (
            str(uuid4()),
            secret_id,
            action,
            performed_by,
            now_utc().isoformat(),
            json.dumps(details) if details else None,
        ),
    )


def build_failure_details(lookup: AuditLookup, reason: str) -> Dict:
    """The context that makes a failed row useful: what was looked for, and why it failed.

    Composed field by field from ``lookup``'s keys rather than by serialising an
    object wholesale, so a field added to some future lookup type cannot become a
    recorded field here without someone writing the line that records it.

    Raises:
        ValueError: for a reason outside ``FAILURE_REASONS``.
    """
    if reason not in FAILURE_REASONS:
        raise ValueError(f"unknown failed-access reason: {reason}")
    details: Dict = {"reason": reason, "scope": lookup.scope}
    if lookup.name:
        details["requested_name"] = lookup.name
    if lookup.secret_id:
        details["requested_secret_id"] = lookup.secret_id
    if lookup.chat_id:
        details["chat_id"] = lookup.chat_id
    return details


def record_failed_access(
    cursor: sqlite3.Cursor,
    lookup: AuditLookup,
    reason: str,
    secret_id: str | None = None,
) -> None:
    """Record a failed access on an open cursor, and commit it.

    ``secret_id`` is the row the access resolved to when there was one -- an
    expired entry, or one rejected for its type -- and None when the lookup
    matched nothing at all.

    A lookup with no ``performed_by`` is not recorded, for the same reason the
    success limb only audits when a value is actually handed over: an access
    that does not name its caller is not attributable, and a row that cannot say
    who tried is not an audit record. The commit is here because a failed access
    ends its caller's transaction -- there is no value to hand back after it.
    """
    if lookup.performed_by is None:
        return
    record_action(
        cursor,
        secret_id,
        ACTION_ACCESS_FAILED,
        lookup.performed_by,
        build_failure_details(lookup, reason),
    )
    cursor.connection.commit()


def record_standalone_failed_access(
    db_path: str,
    lookup: AuditLookup,
    reason: str,
    secret_id: str | None = None,
) -> None:
    """Record a failed access for a caller that holds no cursor of its own."""
    conn = sqlite3.connect(db_path)
    try:
        record_failed_access(conn.cursor(), lookup, reason, secret_id)
    finally:
        conn.close()


def fetch_audit_log(db_path: str, secret_id: str | None = None, limit: int = 100) -> List[Dict]:
    """Read audit entries, newest first.

    Filtering by secret id excludes failed rows that never resolved to one --
    pass no id to see those.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        if secret_id:
            cursor.execute(_SELECT_AUDIT_FOR_ID_SQL, (secret_id, limit))
        else:
            cursor.execute(_SELECT_AUDIT_SQL, (limit,))
        return [
            {
                "id": row[0],
                "secret_id": row[1],
                "action": row[2],
                "performed_by": row[3],
                "performed_at": row[4],
                "details": json.loads(row[5]) if row[5] else {},
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()
