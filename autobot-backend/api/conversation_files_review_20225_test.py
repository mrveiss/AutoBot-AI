# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Review findings on the conversation-file routes (#20225): duplicates, shared links, batches, shared writes."""

# flake8: noqa: F811 -- fixtures imported from the sibling test module are redefined as test arguments

from __future__ import annotations

import os
import sqlite3
from unittest.mock import AsyncMock

import conversation_file_transfer as transfer
from api.conversation_files_owner_upload_20133_test import world  # noqa: F401 -- fixture
from api.conversation_files_real_manager_20225_test import (  # noqa: F401 -- fixtures
    _BODY,
    _SESSION,
    _as_admin,
    _rows,
    _seed,
    _transfer,
    _upload,
    destinations,
    real,
)


def _listed(w, session=_SESSION):
    return w.client.get(f"/api/conversation/{session}/list").json()


def test_a_reupload_of_identical_bytes_lists_once_and_counts_its_size_once(real):
    first = _upload(real).json()["file_info"]
    assert _upload(real, "again.txt").status_code == 200
    assert _rows(real, "SELECT COUNT(*) FROM session_file_associations WHERE file_id = ?", (first["file_id"],)) == [
        (1,)
    ]
    listed = _listed(_as_admin(real))
    assert listed["total_files"] == 1 and len(listed["files"]) == 1
    assert listed["total_size"] == len(_BODY)


def _share(w, file_id, session="s-other"):
    conn = sqlite3.connect(w.db)
    conn.execute(
        "INSERT INTO session_file_associations (session_id, file_id, association_type) VALUES (?, ?, 'reference')",
        (session, file_id),
    )
    conn.commit()
    conn.close()


def test_delete_in_one_session_keeps_a_file_another_session_still_links(real):
    file_id = _seed(real)
    _share(real, file_id)
    admin = _as_admin(real)
    assert admin.client.delete(f"/api/conversation/{_SESSION}/files/{file_id}").status_code == 200
    assert _listed(admin)["total_files"] == 0
    assert _rows(real, "SELECT is_deleted FROM conversation_files WHERE file_id = ?", (file_id,)) == [(0,)]
    assert admin.client.get("/api/conversation/s-other/list").json()["total_files"] == 1
    assert admin.client.delete(f"/api/conversation/s-other/files/{file_id}").status_code == 200
    assert _rows(real, "SELECT is_deleted FROM conversation_files WHERE file_id = ?", (file_id,)) == [(1,)]


def test_one_failing_lookup_in_a_batch_is_a_failed_entry_and_the_batch_continues(destinations, monkeypatch):
    good = _seed(destinations)
    real_lookup = destinations.real.get_file_info

    async def flaky(session_id, file_id):
        if file_id == "boom":
            raise RuntimeError("db down")
        return await real_lookup(session_id, file_id)

    monkeypatch.setattr(destinations.real, "get_file_info", flaky)
    body = _as_admin(destinations).client.post(
        f"/api/conversation/{_SESSION}/transfer",
        json={"file_ids": ["boom", good], "destination": "shared", "copy": True},
    )
    assert body.status_code == 200, body.text
    out = body.json()
    assert (out["total_transferred"], out["total_failed"]) == (1, 1)
    assert out["failed_files"][0] == {"file_id": "boom", "error": "db down"}


def test_a_move_whose_source_delete_fails_is_transferred_with_the_delete_failure_recorded(destinations, monkeypatch):
    file_id = _seed(destinations)
    monkeypatch.setattr(destinations.real, "delete_file", AsyncMock(side_effect=RuntimeError("locked")))
    out = _transfer(destinations, file_id, "shared").json()
    assert (out["total_transferred"], out["total_failed"]) == (1, 0)
    assert out["transferred_files"][0]["source_delete_error"] == "locked"
    assert (destinations.tmp / "shared" / "notes.txt").read_bytes() == _BODY  # the destination is kept, not rolled back


def test_a_collision_is_reported_and_the_original_is_intact(destinations):
    file_id = _seed(destinations)
    existing = destinations.tmp / "shared" / "notes.txt"
    existing.write_bytes(b"original")
    out = _transfer(destinations, file_id, "shared", copy=True).json()
    assert (out["total_transferred"], out["total_failed"]) == (0, 1)
    assert "already exists" in out["failed_files"][0]["error"]
    assert existing.read_bytes() == b"original"
    assert [p.name for p in existing.parent.iterdir()] == ["notes.txt"]  # no temp left behind


def test_the_final_write_never_overwrites_a_file_created_after_the_check(destinations, monkeypatch):
    file_id = _seed(destinations)
    target = destinations.tmp / "shared" / "notes.txt"
    real_copy = transfer.shutil.copyfileobj

    def racing_copy(src, dst):
        real_copy(src, dst)
        target.write_bytes(b"won the race")  # a concurrent transfer lands between check and publish

    monkeypatch.setattr(transfer.shutil, "copyfileobj", racing_copy)
    out = _transfer(destinations, file_id, "shared", copy=True).json()
    assert out["total_failed"] == 1
    assert target.read_bytes() == b"won the race"
    assert [p.name for p in target.parent.iterdir()] == ["notes.txt"]


def test_a_failed_copy_leaves_nothing_in_the_shared_root(destinations, monkeypatch):
    file_id = _seed(destinations)

    def dying_copy(src, dst):
        dst.write(b"par")
        raise OSError("disk full")

    monkeypatch.setattr(transfer.shutil, "copyfileobj", dying_copy)
    out = _transfer(destinations, file_id, "shared", target_path="docs", copy=True).json()
    assert out["failed_files"][0]["error"] == "disk full"
    assert [p for p in (destinations.tmp / "shared" / "docs").iterdir()] == []


def test_an_absolute_target_path_is_refused(destinations):
    file_id = _seed(destinations)
    out = _transfer(destinations, file_id, "shared", target_path="/docs", copy=True).json()
    assert (out["total_transferred"], out["total_failed"]) == (0, 1)
    assert not (destinations.tmp / "shared" / "docs").exists()


def test_a_symlink_at_the_target_is_never_written_through(destinations):
    file_id = _seed(destinations)
    outside = destinations.tmp / "outside.txt"
    outside.write_bytes(b"outside")
    os.symlink(outside, destinations.tmp / "shared" / "notes.txt")
    out = _transfer(destinations, file_id, "shared", copy=True).json()
    assert out["total_failed"] == 1
    assert outside.read_bytes() == b"outside"


def test_a_symlinked_directory_in_the_path_cannot_leave_the_root(destinations):
    file_id = _seed(destinations)
    outside = destinations.tmp / "outside_dir"
    outside.mkdir()
    os.symlink(outside, destinations.tmp / "shared" / "link")
    out = _transfer(destinations, file_id, "shared", target_path="link", copy=True).json()
    assert out["total_failed"] == 1
    assert list(outside.iterdir()) == []
