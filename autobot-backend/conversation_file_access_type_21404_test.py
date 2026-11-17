# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A deduplicated upload is logged as ``reference``, and an older log gains that type (#21404)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

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


def _old_database(tmp_path):
    """A log made before #21404: the schema with its CHECK lacking ``reference``, and one row in it."""
    old = _SCHEMA.read_text(encoding="utf-8").replace(", 'restore', 'reference'))", ", 'restore'))")
    assert "'reference'))" not in old
    connection = sqlite3.connect(tmp_path / "old.db")
    connection.executescript(old)
    connection.execute(_INSERT, ("f1", "download", "alice"))
    connection.commit()
    return connection


def test_the_migration_keeps_existing_rows_and_is_idempotent(tmp_path):
    connection = _old_database(tmp_path)
    try:
        connection.execute(_INSERT, ("f2", "reference", "alice"))
        raise AssertionError("the old CHECK should refuse 'reference'")
    except sqlite3.IntegrityError:
        connection.rollback()
    ensure_access_type_schema(connection)
    ensure_access_type_schema(connection)  # a second run changes nothing
    connection.execute(_INSERT, ("f2", "reference", "alice"))
    rows = connection.execute(
        "SELECT file_id, access_type, accessed_by FROM file_access_log ORDER BY log_id"
    ).fetchall()
    assert rows == [("f1", "download", "alice"), ("f2", "reference", "alice")]
    index = connection.execute("SELECT name FROM sqlite_master WHERE name = 'idx_file_access_log_file'").fetchall()
    assert index == [("idx_file_access_log_file",)]
    connection.close()
