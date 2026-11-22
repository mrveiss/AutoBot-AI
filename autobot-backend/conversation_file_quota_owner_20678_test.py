# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Who pays the quota for a file an agent writes (#20678, option B).

Real ``ConversationFileManager`` on real SQLite, through the routes. An agent's file is charged to the
human who owns the conversation (``quota_owner``) while ``uploaded_by`` keeps naming the writer; a human
upload is charged to its uploader as before; the column is added to an older database without touching rows.
"""

from __future__ import annotations

import sqlite3

import pytest

import conversation_file_quota as quota
from api.conversation_files_owner_upload_20133_test import _BOB, world  # noqa: F401 -- fixture
from api.conversation_files_real_manager_20225_test import (  # noqa: F401
    _as_admin,
    _rows,
    _upload,
    real,
)
from conversation_file_quota_owner import OWNERLESS_AGENT_WRITE_RULE
from conversation_file_quota_owner_schema import ensure_quota_owner_schema

_COLUMNS = "SELECT session_id, uploaded_by, quota_owner, file_size FROM conversation_files ORDER BY session_id"


@pytest.fixture
def small(real, monkeypatch):  # noqa: F811
    """A 20-byte quota."""
    monkeypatch.setattr(quota, "USER_QUOTA_BYTES", 20)
    return real


def _generate(w, session: str, owner: str | None, content: str, agent: str | None = "scribe"):
    w.owner = owner
    body = {"filename": f"{session}.txt", "content": content, "agent_name": agent}
    return _as_admin(w).client.post(f"/api/conversation/{session}/generate", json=body)


def _mcp_write(w, session: str, owner: str | None, content: str):
    w.owner = owner
    body = {"tool_name": "session_write_file", "arguments": {"filename": f"{session}.txt", "content": content}}
    return _as_admin(w).client.post(f"/api/conversation/{session}/mcp/call", json=body)


def test_the_rule_is_named_and_it_is_the_conversation_owner():
    assert OWNERLESS_AGENT_WRITE_RULE == "conversation_owner"


def test_an_agent_write_is_charged_to_the_conversation_owner_and_uploaded_by_names_the_agent(small):
    assert _generate(small, "s-a", "alice", "x" * 15).status_code == 200
    assert _rows(small, _COLUMNS) == [("s-a", "scribe", "alice", 15)]


def test_one_users_agent_cannot_exhaust_another_users_quota(small):
    assert _generate(small, "s-a", "alice", "x" * 20).status_code == 200  # alice's agent fills alice's quota
    assert _generate(small, "s-a2", "alice", "y").status_code == 413  # alice's own next agent write is refused
    assert _generate(small, "s-b", "bob", "z" * 20).status_code == 200  # bob's agent, same name, is not
    owners = [(r[0], r[2]) for r in _rows(small, _COLUMNS)]
    assert owners == [("s-a", "alice"), ("s-b", "bob")]


def test_an_ownerless_mcp_write_is_charged_to_the_conversation_owner_not_to_agent(small):
    assert _mcp_write(small, "s-a", "alice", "x" * 20).status_code == 200  # the writer is the generic "agent"
    assert _mcp_write(small, "s-a2", "alice", "y").status_code == 413
    assert _mcp_write(small, "s-b", "bob", "z" * 20).status_code == 200
    assert _rows(small, _COLUMNS) == [("s-a", "agent", "alice", 20), ("s-b", "agent", "bob", 20)]


def test_an_agent_write_in_a_conversation_with_no_recorded_owner_is_charged_to_the_calling_user(small):
    assert _generate(small, "s-legacy", None, "x" * 5).status_code == 200
    assert _rows(small, _COLUMNS) == [("s-legacy", "scribe", "root", 5)]


def test_a_human_upload_is_charged_to_the_uploader_as_before(small):
    assert _upload(small, "a.txt", b"u" * 20).status_code == 200
    assert _rows(small, _COLUMNS) == [("s-real", "alice", "alice", 20)]
    assert _upload(small, "b.txt", b"v").status_code == 413  # alice is at her quota


def test_a_row_stored_before_the_column_is_still_charged_to_its_uploaded_by(small):
    _upload(small, "a.txt", b"u" * 20)
    conn = sqlite3.connect(small.db)
    conn.execute("UPDATE conversation_files SET quota_owner = NULL")  # what a pre-#20678 row looks like
    conn.commit()
    conn.close()
    assert _upload(small, "b.txt", b"v").status_code == 413


def test_a_non_owner_is_refused_before_any_charge_on_both_agent_write_routes(small):
    small.owner = "alice"
    small.user = dict(_BOB)
    body = {"filename": "x.txt", "content": "x" * 5, "agent_name": "scribe"}
    mcp = {"tool_name": "session_write_file", "arguments": {"filename": "x.txt", "content": "x" * 5}}
    assert small.client.post("/api/conversation/s-a/generate", json=body).status_code in (403, 404)
    assert small.client.post("/api/conversation/s-a/mcp/call", json=mcp).status_code in (403, 404)
    assert _rows(small, _COLUMNS) == []  # no row, so nothing was charged to anybody


def test_an_owner_lookup_that_raises_denies_the_write_and_charges_nobody(small):
    small.owner_error = RuntimeError("owner store down")
    assert _generate(small, "s-a", "alice", "x" * 5).status_code >= 400
    assert _mcp_write(small, "s-a2", "alice", "x" * 5).status_code >= 400
    assert _rows(small, _COLUMNS) == []  # it was not charged to the caller instead


def test_editing_an_agent_written_file_is_charged_to_the_quota_owner_not_the_agent(small):
    assert _upload(small, "a.txt", b"u" * 15).status_code == 200  # alice holds 15 of 20
    assert _generate(small, "s-a", "alice", "x" * 3).status_code == 200  # her agent's file: 3 more, charged to alice
    (file_id,) = _rows(small, "SELECT file_id FROM conversation_files WHERE uploaded_by = 'scribe'")[0]
    url = f"/api/conversation/s-a/files/{file_id}/content"
    assert _as_admin(small).client.put(url, json={"content": "y" * 8}).status_code == 413  # 15 + 8 > 20 for alice
    assert _as_admin(small).client.put(url, json={"content": "y" * 5}).status_code == 200  # 15 + 5 == 20
    assert _rows(small, "SELECT file_size FROM conversation_files WHERE uploaded_by = 'scribe'") == [(5,)]


def test_the_column_is_added_to_an_older_database_and_no_row_changes(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE conversation_files (file_id TEXT, uploaded_by TEXT, is_deleted INTEGER, file_size INTEGER)"
    )
    conn.execute("INSERT INTO conversation_files VALUES ('f1', 'scribe', 0, 7)")
    conn.commit()
    ensure_quota_owner_schema(conn)
    ensure_quota_owner_schema(conn)  # idempotent
    assert conn.execute("SELECT file_id, uploaded_by, quota_owner, file_size FROM conversation_files").fetchall() == [
        ("f1", "scribe", None, 7)
    ]
    indexes = [r[1] for r in conn.execute("PRAGMA index_list(conversation_files)")]
    assert "idx_conversation_files_quota_owner" in indexes
    conn.close()
