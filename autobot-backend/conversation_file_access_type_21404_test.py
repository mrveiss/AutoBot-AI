# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A deduplicated upload is logged as ``reference``, and an older log gains that type (#21404)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import conversation_file_access_type_schema as schema
from api.conversation_files_owner_upload_20133_test import world  # noqa: F401 -- fixture `real` builds on
from api.conversation_files_real_manager_20225_test import _rows, _upload, real  # noqa: F401 -- fixture
from conversation_file_access_type_schema import ensure_access_type_schema

_SCHEMA = Path(__file__).parent / "database/schemas/conversation_files_schema.sql"
_INSERT = "INSERT INTO file_access_log (file_id, access_type, accessed_by) VALUES (?, ?, ?)"


def test_a_duplicate_upload_is_logged_as_a_reference_not_an_upload(real):  # noqa: F811
    first = _upload(real).json()["file_info"]
    assert _upload(real, "again.txt").status_code == 200
    types = _rows(
        real, "SELECT access_type FROM file_access_log WHERE file_id = ? ORDER BY log_id", (first["file_id"],)
    )
    assert types == [("upload",), ("reference",)]


_ROWS = [
    ("f1", "download", "alice", "2026-01-01 10:00:00", '{"a": 1}'),
    ("f2", "view", "bob", "2026-01-02 11:00:00", None),
    ("f3", "restore", None, "2026-01-03 12:00:00", '{"b": [2]}'),
]
_ALL = "SELECT log_id, file_id, access_type, accessed_by, accessed_at, access_metadata FROM file_access_log ORDER BY log_id"
_FULL_INSERT = (
    "INSERT INTO file_access_log (file_id, access_type, accessed_by, accessed_at, access_metadata) VALUES (?,?,?,?,?)"
)


def _old_database(tmp_path, rows=_ROWS):
    """A log made before #21404: the schema with its CHECK lacking ``reference``, and *rows* in it (FKs off)."""
    old = _SCHEMA.read_text(encoding="utf-8").replace(", 'restore', 'reference'))", ", 'restore'))")
    assert "'reference'))" not in old
    connection = sqlite3.connect(tmp_path / "old.db")
    connection.executescript(old)
    connection.executemany(_FULL_INSERT, rows)
    connection.commit()
    return connection


def _refused_reference(connection) -> bool:
    try:
        connection.execute(_INSERT, ("f9", "reference", "alice"))
    except sqlite3.IntegrityError:
        connection.rollback()
        return True
    return False


def test_the_migration_keeps_every_row_and_column_and_is_idempotent(tmp_path):
    connection = _old_database(tmp_path)
    before = connection.execute(_ALL).fetchall()
    assert _refused_reference(connection)

    ensure_access_type_schema(connection)
    ensure_access_type_schema(connection)  # a second run changes nothing

    assert connection.execute(_ALL).fetchall() == before and len(before) == len(_ROWS)
    assert not _refused_reference(connection)
    index = connection.execute("SELECT name FROM sqlite_master WHERE name = 'idx_file_access_log_file'").fetchall()
    assert index == [("idx_file_access_log_file",)]
    connection.close()


def test_an_orphan_row_survives_and_the_foreign_key_setting_is_restored(tmp_path):
    connection = _old_database(tmp_path)  # no conversation_files row exists: every row is an orphan
    connection.execute("PRAGMA foreign_keys = ON")
    before = connection.execute(_ALL).fetchall()

    ensure_access_type_schema(connection)

    assert connection.execute(_ALL).fetchall() == before
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    connection.close()


def test_log_ids_of_deleted_rows_are_never_reused(tmp_path):
    connection = _old_database(tmp_path)
    connection.execute("DELETE FROM file_access_log WHERE log_id > 1")  # the counter stays at 3
    connection.commit()

    ensure_access_type_schema(connection)
    connection.execute(_INSERT, ("f4", "reference", "alice"))

    assert [row[0] for row in connection.execute(_ALL)] == [1, 4]
    connection.close()


def test_an_error_mid_migration_leaves_the_old_table_and_rows_intact(tmp_path, monkeypatch):
    connection = _old_database(tmp_path)
    before = connection.execute(_ALL).fetchall()
    monkeypatch.setattr(schema, "_RESTORE_SQL", "INSERT INTO no_such_table SELECT 1")

    with pytest.raises(sqlite3.Error):
        ensure_access_type_schema(connection)

    assert connection.execute(_ALL).fetchall() == before
    assert _refused_reference(connection)  # still the old CHECK
    assert connection.execute("SELECT name FROM sqlite_temp_master WHERE name LIKE 'file_access_log%'").fetchall() == []
    connection.close()
