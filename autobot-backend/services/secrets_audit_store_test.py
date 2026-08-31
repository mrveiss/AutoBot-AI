# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Failed-credential-access auditing (#15023 AC3, failure limb).

Before this, ``INSERT INTO secrets_audit`` had exactly one reachable call site
tree-wide and it required a secret that was *found*: ``secret_id`` was
``TEXT NOT NULL`` with a foreign key to ``secrets(id)``, so a lookup that
matched nothing had no id to record against and simply returned ``None``. A
failed credential access left no trace at all.

These tests drive the real ``SecretsService`` against a temporary database file
-- no mock stands in for the audit write -- and assert on the *row*: that it
exists, that it names the reason, that "no such entry" and "expired" are
distinguishable when both hand the caller the same ``None``, that the success
path still writes exactly what it wrote before, and that nothing derived from
the credential value reaches any column. That last one follows #15080's
telltale-marker pattern: plant a marker inside the value being looked up, then
assert it is absent from everything written.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet

from autobot_shared.time_utils import now_utc
from services import secrets_audit_store
from services.secrets_audit_store import (
    ACTION_ACCESS_FAILED,
    ACTION_ACCESSED,
    FAILURE_REASONS,
    REASON_EXPIRED,
    REASON_LOOKUP_ERROR,
    REASON_NOT_FOUND,
    REASON_TYPE_MISMATCH,
    AuditLookup,
    _secret_id_is_not_null,
    build_failure_details,
)
from services.secrets_service import SecretsService

_CALLER = "bedrock_provider"
_ENTRY_NAME = "bedrock_aws_credentials"
_SECRET_TYPE = "aws_bedrock_credentials"  # nosemgrep: autobot-hardcoded-secret-key

#: Planted inside the *value* of the secret under lookup. It must never reach an
#: audit row -- not whole, and not as a fragment (#15080's failure mode was an
#: error message echoing the first characters of a key).
_TELLTALE = "TELLTALE-MARKER-THAT-MUST-NEVER-BE-AUDITED"
_PARKED_TABLE = "secrets_audit_pre_nullable_secret_id"


@pytest.fixture()
def service(tmp_path) -> SecretsService:
    """A real service on a throwaway database, with an explicit key.

    Both constructor arguments are supplied so the fixture never resolves the
    canonical data directory or the deployment's encryption key -- this must not
    touch a live store.
    """
    return SecretsService(
        db_path=str(tmp_path / "secrets.db"),
        encryption_key=Fernet.generate_key().decode(),
    )


def _credential_value(marker: str = _TELLTALE) -> str:
    """A Bedrock-shaped credential payload carrying the telltale marker."""
    return json.dumps({"aws_access_key_id": "AKIA" + "T" * 16, "aws_secret_access_key": marker})


def _failed_rows(service: SecretsService) -> list[dict]:
    return [entry for entry in service.get_audit_log() if entry["action"] == ACTION_ACCESS_FAILED]


def _expired_yesterday() -> str:
    return (now_utc() - timedelta(days=1)).isoformat()


def _dump_every_audit_cell(db_path: str) -> list[str]:
    """Every column of every audit row, as text -- the whole written surface."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM secrets_audit")
        return [str(cell) for row in cursor.fetchall() for cell in row]
    finally:
        conn.close()


def _table_names(db_path: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


def test_lookup_that_finds_nothing_writes_a_failed_access_row(service):
    """The gap #15023 AC3 names: a miss used to return None and record nothing."""
    assert service.get_secret(name=_ENTRY_NAME, include_value=True, accessed_by=_CALLER) is None

    rows = _failed_rows(service)
    assert len(rows) == 1, "a failed credential lookup must write exactly one audit row"
    row = rows[0]
    assert row["secret_id"] is None, "a lookup that matched nothing has no secret to point at"
    assert row["performed_by"] == _CALLER
    assert row["details"]["reason"] == REASON_NOT_FOUND
    assert row["details"]["requested_name"] == _ENTRY_NAME
    assert row["details"]["scope"] == "general"


def test_expired_secret_writes_a_distinct_reason(service):
    """Expired and missing are the same None to the caller; they must not be the
    same row to an auditor."""
    created = service.create_secret(
        name=_ENTRY_NAME,
        secret_type=_SECRET_TYPE,
        value=_credential_value(),
        expires_at=_expired_yesterday(),
    )

    assert service.get_secret(name=_ENTRY_NAME, include_value=True, accessed_by=_CALLER) is None

    rows = _failed_rows(service)
    assert len(rows) == 1
    assert rows[0]["details"]["reason"] == REASON_EXPIRED
    assert rows[0]["details"]["reason"] != REASON_NOT_FOUND
    # The expired row *does* resolve to a secret, so it records which one -- that
    # is the whole reason the column stays a foreign key rather than being dropped.
    assert rows[0]["secret_id"] == created["id"]


def test_expired_and_missing_are_told_apart_from_the_same_none(service):
    """Non-vacuity for the pair: both calls return None, and the rows still differ."""
    service.create_secret(
        name="expired-entry",
        secret_type=_SECRET_TYPE,
        value=_credential_value(),
        expires_at=_expired_yesterday(),
    )

    assert service.get_secret(name="expired-entry", include_value=True, accessed_by=_CALLER) is None
    assert service.get_secret(name="absent-entry", include_value=True, accessed_by=_CALLER) is None

    by_name = {row["details"]["requested_name"]: row["details"]["reason"] for row in _failed_rows(service)}
    assert by_name == {"expired-entry": REASON_EXPIRED, "absent-entry": REASON_NOT_FOUND}


def test_unattributed_lookup_writes_no_row(service):
    """No ``accessed_by`` means no principal to record, and no row -- the mirror of
    the success limb, which only audits when a value is actually handed over."""
    assert service.get_secret(name=_ENTRY_NAME, include_value=True) is None
    assert _failed_rows(service) == []


def test_successful_access_writes_exactly_what_it_wrote_before(service):
    """Regression guard on the limb that already worked: one 'accessed' row beside
    the 'created' row, unchanged in shape, and no failure row alongside it."""
    created = service.create_secret(
        name=_ENTRY_NAME,
        secret_type=_SECRET_TYPE,
        value=_credential_value(),
        created_by="operator",
    )

    got = service.get_secret(name=_ENTRY_NAME, include_value=True, accessed_by=_CALLER)
    assert got["value"] == _credential_value()

    entries = service.get_audit_log()
    assert sorted(entry["action"] for entry in entries) == ["accessed", "created"]
    accessed = [entry for entry in entries if entry["action"] == ACTION_ACCESSED]
    assert len(accessed) == 1, "the success path must not double-audit"
    assert accessed[0]["secret_id"] == created["id"]
    assert accessed[0]["performed_by"] == _CALLER
    assert accessed[0]["details"] == {}, "the success row carried no details before and must not now"
    assert _failed_rows(service) == []


def test_failed_row_carries_no_part_of_the_credential_value(service):
    """#15080's pattern: plant a marker in the value, assert it is nowhere written."""
    service.create_secret(
        name=_ENTRY_NAME,
        secret_type=_SECRET_TYPE,
        value=_credential_value(),
        expires_at=_expired_yesterday(),
    )
    service.get_secret(name=_ENTRY_NAME, include_value=True, accessed_by=_CALLER)

    assert _failed_rows(service), "no failed row was written -- the assertions below would be vacuous"
    cells = _dump_every_audit_cell(service.db_path)
    assert cells, "no audit cells to inspect"
    written = " ".join(cells)
    assert _TELLTALE not in written
    for fragment in (_TELLTALE[:10], _TELLTALE[-10:]):
        assert fragment not in written, "a fragment of the credential value reached an audit row"
    assert str(len(_TELLTALE)) not in json.dumps(_failed_rows(service)[0]["details"])


@pytest.mark.parametrize("reason", FAILURE_REASONS)
def test_every_reason_round_trips_to_its_own_row(service, reason):
    """Enumeration guard: each declared reason is writable and reads back as itself."""
    service.record_access_failure(reason, name=_ENTRY_NAME, accessed_by=_CALLER)
    rows = _failed_rows(service)
    assert len(rows) == 1
    assert rows[0]["details"]["reason"] == reason


def test_the_reason_enumeration_is_not_empty():
    """Non-vacuity for the parametrisation above: an empty tuple would pass it silently."""
    assert len(FAILURE_REASONS) >= 5
    assert REASON_NOT_FOUND in FAILURE_REASONS
    assert REASON_EXPIRED in FAILURE_REASONS


def test_an_unknown_reason_is_refused(service):
    """A row whose reason no reader understands is worse than no row."""
    with pytest.raises(ValueError):
        build_failure_details(AuditLookup(performed_by=_CALLER), "reason_nobody_declared")


def test_caller_side_rejection_records_the_secret_it_rejected(service):
    """A found-but-unusable row -- wrong type, unparseable value -- is only visible to
    the caller, so ``record_access_failure`` carries the resolved id through."""
    created = service.create_secret(name=_ENTRY_NAME, secret_type="some_other_type", value=_credential_value())

    service.record_access_failure(
        REASON_TYPE_MISMATCH,
        name=_ENTRY_NAME,
        accessed_by=_CALLER,
        secret_id=created["id"],
    )

    rows = _failed_rows(service)
    assert len(rows) == 1
    assert rows[0]["secret_id"] == created["id"]
    assert rows[0]["details"]["reason"] == REASON_TYPE_MISMATCH


# --- the schema migration -----------------------------------------------------------


def _build_pre_15023_database(db_path) -> None:
    """A database with the old ``secret_id TEXT NOT NULL`` audit table and history in it."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE secrets (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, "
        "secret_type TEXT NOT NULL, encrypted_value TEXT NOT NULL, scope TEXT NOT NULL DEFAULT 'general', "
        "chat_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT, created_by TEXT, "
        "metadata TEXT, access_count INTEGER DEFAULT 0, last_accessed_at TEXT, is_active BOOLEAN DEFAULT 1, "
        "UNIQUE(name, scope, chat_id))"
    )
    cursor.execute(
        "CREATE TABLE secrets_audit (id TEXT PRIMARY KEY, secret_id TEXT NOT NULL, action TEXT NOT NULL, "
        "performed_by TEXT, performed_at TEXT NOT NULL, details TEXT, "
        "FOREIGN KEY (secret_id) REFERENCES secrets(id))"
    )
    stamp = now_utc().isoformat()
    cursor.executemany(
        "INSERT INTO secrets_audit (id, secret_id, action, performed_by, performed_at, details) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("audit-1", "secret-1", "created", "operator", stamp, None),
            ("audit-2", "secret-1", "accessed", _CALLER, stamp, None),
        ],
    )
    conn.commit()
    conn.close()


def test_migration_carries_every_existing_row_across(tmp_path):
    """The table holds audit history -- the rebuild must not lose a single row."""
    db_path = tmp_path / "legacy.db"
    _build_pre_15023_database(db_path)

    service = SecretsService(db_path=str(db_path), encryption_key=Fernet.generate_key().decode())

    entries = service.get_audit_log()
    assert {entry["id"] for entry in entries} == {"audit-1", "audit-2"}
    assert {entry["action"] for entry in entries} == {"created", "accessed"}
    assert _PARKED_TABLE not in _table_names(str(db_path)), "the rebuild left its scratch table behind"


def test_migration_relaxes_not_null_so_a_miss_can_be_recorded(tmp_path):
    """The point of the migration: after it, an unresolvable access is writable."""
    db_path = tmp_path / "legacy.db"
    _build_pre_15023_database(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        assert _secret_id_is_not_null(conn.cursor()), "fixture is not the pre-#15023 schema"
    finally:
        conn.close()

    service = SecretsService(db_path=str(db_path), encryption_key=Fernet.generate_key().decode())

    conn = sqlite3.connect(str(db_path))
    try:
        assert not _secret_id_is_not_null(conn.cursor())
    finally:
        conn.close()

    assert service.get_secret(name="absent-entry", include_value=True, accessed_by=_CALLER) is None
    rows = _failed_rows(service)
    assert len(rows) == 1
    assert rows[0]["secret_id"] is None
    assert rows[0]["details"]["reason"] == REASON_NOT_FOUND


def test_migration_is_idempotent(tmp_path):
    """Re-opening an already-migrated database must not rebuild it again."""
    db_path = tmp_path / "legacy.db"
    _build_pre_15023_database(db_path)

    SecretsService(db_path=str(db_path), encryption_key=Fernet.generate_key().decode())
    reopened = SecretsService(db_path=str(db_path), encryption_key=Fernet.generate_key().decode())

    assert {entry["id"] for entry in reopened.get_audit_log()} == {"audit-1", "audit-2"}
    assert _PARKED_TABLE not in _table_names(str(db_path))
    reopened.record_access_failure(REASON_LOOKUP_ERROR, name=_ENTRY_NAME, accessed_by=_CALLER)
    assert len(_failed_rows(reopened)) == 1


def test_a_lossy_rebuild_aborts_and_leaves_the_history_intact(tmp_path, monkeypatch):
    """The transaction and the row-count compare exist so an interrupted or
    incomplete rebuild cannot cost audit history -- it must abort and roll back,
    not complete with fewer rows than it started with."""
    db_path = tmp_path / "legacy.db"
    _build_pre_15023_database(db_path)
    # A copy step that carries nothing: the shape of any rebuild that silently
    # loses rows, without needing to interrupt one mid-flight.
    monkeypatch.setattr(secrets_audit_store, "_MIGRATION_COPY_ROWS_SQL", "SELECT 1")

    with pytest.raises(sqlite3.IntegrityError):
        SecretsService(db_path=str(db_path), encryption_key=Fernet.generate_key().decode())

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM secrets_audit")
        assert {row[0] for row in cursor.fetchall()} == {"audit-1", "audit-2"}
        assert _secret_id_is_not_null(conn.cursor()), "the aborted rebuild must leave the old schema in place"
    finally:
        conn.close()
    assert _PARKED_TABLE not in _table_names(str(db_path)), "the rollback left the parked table behind"
