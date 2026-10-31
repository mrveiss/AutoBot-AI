# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The conversation-file routes against the REAL ConversationFileManager (#20225).

The route module called ``upload_file``, ``get_file_info``, ``delete_file`` and ``transfer_files``,
which the manager did not define, and every test mocked the manager, so none saw it. Here the manager
is real (real SQLite, a temp storage dir); only identity, the owner store, the Redis cache (down) and
the two transfer destinations' external services are faked. Each route is exercised end to end.
"""

from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from api.conversation_files_owner_upload_20133_test import _ADMIN, _ALICE, world  # noqa: F401 -- fixture
from conversation_file_manager import ConversationFileManager

_BODY = b"hello from the real manager\n"
_SESSION = "s-real"


@pytest.fixture
def real(world, tmp_path, monkeypatch):  # noqa: F811
    """``world`` with the mock manager replaced by a real one on real SQLite."""
    manager = ConversationFileManager(storage_dir=tmp_path / "storage", db_path=tmp_path / "files.db")
    manager._initialize_schema()
    monkeypatch.setattr(manager, "_get_redis_sessions", AsyncMock(side_effect=RedisConnectionError("down")))
    world.app.state.conversation_file_manager = manager
    world.real = manager
    world.db = tmp_path / "files.db"
    world.tmp = tmp_path
    world.owner = "alice"
    return world


def _upload(w, name="notes.txt", body=_BODY):
    w.user = dict(_ALICE)
    return w.client.post(f"/api/conversation/{_SESSION}/upload", files={"file": (name, body, "text/plain")})


def _seed(w, name="notes.txt", body=_BODY) -> str:
    """Store a file through the manager itself, so a route is tested on its own (not behind the upload)."""
    stored = asyncio.run(w.real.add_file(_SESSION, body, name, mime_type="text/plain", uploaded_by="alice"))
    return stored["file_id"]


def _as_admin(w):
    w.user = dict(_ADMIN)
    return w


def _rows(w, sql, args=()):
    conn = sqlite3.connect(w.db)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def test_upload_stores_the_file_on_disk_and_in_the_db_with_a_valid_response(real):
    response = _upload(real)
    assert response.status_code == 200, response.text
    info = response.json()["file_info"]
    assert (info["filename"], info["original_filename"], info["size"], info["uploaded_by"]) == (
        "notes.txt",
        "notes.txt",
        len(_BODY),
        "alice",
    )
    assert info["session_id"] == _SESSION and "file_path" not in info
    on_disk = [p for p in (real.tmp / "storage").rglob("*") if p.is_file()]
    assert [p.read_bytes() for p in on_disk] == [_BODY]
    assert _rows(real, "SELECT file_id, uploaded_by, file_size FROM conversation_files") == [
        (info["file_id"], "alice", len(_BODY))
    ]


def test_a_duplicate_upload_in_the_same_session_dedups_and_its_access_log_is_written(real):
    first = _upload(real).json()["file_info"]
    second = _upload(real, "again.txt")
    assert second.status_code == 200, second.text
    assert second.json()["file_info"]["file_id"] == first["file_id"]
    assert _rows(real, "SELECT COUNT(*) FROM conversation_files") == [(1,)]
    logged = _rows(real, "SELECT access_metadata FROM file_access_log WHERE file_id = ?", (first["file_id"],))
    assert sum('"deduplication": true' in (row[0] or "") for row in logged) == 1, logged  # the dedup write landed


def test_list_returns_the_stored_file_as_valid_file_info(real):
    _seed(real)
    response = _as_admin(real).client.get(f"/api/conversation/{_SESSION}/list")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total_files"], body["total_size"]) == (1, len(_BODY))
    assert (body["files"][0]["filename"], body["files"][0]["uploaded_by"]) == ("notes.txt", "alice")
    assert "file_path" not in body["files"][0]


def test_download_returns_the_stored_bytes(real):
    file_id = _seed(real)
    response = _as_admin(real).client.get(f"/api/conversation/{_SESSION}/download/{file_id}")
    assert response.status_code == 200, response.text
    assert response.content == _BODY


def test_preview_returns_the_text_without_a_server_path(real):
    file_id = _seed(real)
    response = _as_admin(real).client.get(f"/api/conversation/{_SESSION}/preview/{file_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["preview_available"], body["preview_content"]) == (True, _BODY.decode())
    assert "file_path" not in body["file_info"]


def test_a_file_of_another_session_is_not_found(real):
    file_id = _seed(real)
    real.owner = "alice"
    response = _as_admin(real).client.get(f"/api/conversation/other-session/download/{file_id}")
    assert response.status_code == 404


def test_delete_removes_it_from_the_conversation(real):
    file_id = _seed(real)
    admin = _as_admin(real)
    response = admin.client.delete(f"/api/conversation/{_SESSION}/files/{file_id}")
    assert response.status_code == 200, response.text
    assert admin.client.get(f"/api/conversation/{_SESSION}/list").json()["total_files"] == 0
    assert admin.client.get(f"/api/conversation/{_SESSION}/download/{file_id}").status_code == 404
    assert admin.client.delete(f"/api/conversation/{_SESSION}/files/{file_id}").status_code == 404
    types = [r[0] for r in _rows(real, "SELECT access_type FROM file_access_log WHERE file_id = ?", (file_id,))]
    assert "delete" in types


@pytest.fixture
def destinations(real, monkeypatch):
    """The two transfer destinations: a temp shared root and a recording knowledge base."""
    kb = SimpleNamespace(add_document=AsyncMock(return_value={"status": "success"}))
    monkeypatch.setattr("conversation_file_transfer.SHARED_ROOT", real.tmp / "shared")
    monkeypatch.setattr("conversation_file_transfer.get_knowledge_base_async", AsyncMock(return_value=kb))
    (real.tmp / "shared").mkdir()
    real.kb = kb
    return real


def _transfer(w, file_id, destination, **extra):
    body = {"file_ids": [file_id], "destination": destination, **extra}
    return _as_admin(w).client.post(f"/api/conversation/{_SESSION}/transfer", json=body)


def test_transfer_copy_to_shared_leaves_the_conversation_file(destinations):
    file_id = _seed(destinations)
    response = _transfer(destinations, file_id, "shared", target_path="docs", copy=True)
    assert response.status_code == 200, response.text
    assert (response.json()["total_transferred"], response.json()["total_failed"]) == (1, 0)
    assert (destinations.tmp / "shared" / "docs" / "notes.txt").read_bytes() == _BODY
    assert destinations.client.get(f"/api/conversation/{_SESSION}/list").json()["total_files"] == 1


def test_transfer_move_to_shared_removes_it_from_the_conversation(destinations):
    file_id = _seed(destinations)
    assert _transfer(destinations, file_id, "shared").json()["total_transferred"] == 1
    assert (destinations.tmp / "shared" / "notes.txt").read_bytes() == _BODY
    assert destinations.client.get(f"/api/conversation/{_SESSION}/list").json()["total_files"] == 0


def test_transfer_to_shared_refuses_a_path_outside_the_shared_root(destinations):
    file_id = _seed(destinations)
    body = _transfer(destinations, file_id, "shared", target_path="../../escape", copy=True).json()
    assert (body["total_transferred"], body["total_failed"]) == (0, 1)
    assert not (destinations.tmp / "escape").exists()


def test_transfer_to_the_knowledge_base_ingests_the_text(destinations):
    file_id = _seed(destinations)
    response = _transfer(destinations, file_id, "kb", tags=["t1"], copy=True)
    assert response.status_code == 200, response.text
    assert response.json()["total_transferred"] == 1
    content, metadata = destinations.kb.add_document.await_args.args[:2]
    assert content == _BODY.decode() and metadata["tags"] == ["t1"] and metadata["source"] == "notes.txt"


def test_transfer_of_an_unknown_file_is_reported_failed_not_raised(destinations):
    body = _transfer(destinations, "no-such-file", "shared").json()
    assert (body["total_transferred"], body["total_failed"]) == (0, 1)
    assert body["failed_files"][0]["file_id"] == "no-such-file"
