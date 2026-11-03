# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The quota is enforced where bytes are recorded, so every way into the store is covered (#20217).

Real ``ConversationFileManager`` on real SQLite. Covers: each entry path (upload, create, agent-create,
copy, content update, the manager itself), the live / pending-removal split in the refusal, a removal that
frees space only once its queue row is processed, a conditional insert under concurrent writers, the
NULL-owner bucket, and the ``uploaded_by`` index.
"""

from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

import conversation_file_quota as quota
from api.conversation_files_owner_upload_20133_test import world  # noqa: F401 -- fixture
from api.conversation_files_real_manager_20225_test import (  # noqa: F401
    _SESSION,
    _as_admin,
    _rows,
    _seed,
    _upload,
    real,
)
from conversation_file_manager import ConversationFileManager

_API = "/api/conversation/" + _SESSION


@pytest.fixture
def small(real, monkeypatch):  # noqa: F811
    """A 20-byte quota; ``root`` (the admin the routes run as) and ``alice`` each start empty."""
    monkeypatch.setattr(quota, "USER_QUOTA_BYTES", 20)
    return real


def _code(response) -> str:
    assert response.status_code == 413, response.text
    return response.json()["detail"]["code"]


def test_create_is_refused_past_the_quota_and_stores_nothing(small):
    admin = _as_admin(small)
    body = {"filename": "a.txt", "content": "x" * 21}
    assert _code(admin.client.post(f"{_API}/files/create", json=body)) == quota.QUOTA_EXCEEDED
    assert _rows(small, "SELECT COUNT(*) FROM conversation_files") == [(0,)]
    assert [p for p in (small.tmp / "storage").rglob("*") if p.is_file()] == []
    assert admin.client.post(f"{_API}/files/create", json={"filename": "a.txt", "content": "x" * 20}).status_code == 200


def test_agent_create_is_refused_past_the_quota_for_the_agent_that_owns_it(small):
    admin = _as_admin(small)
    body = {"filename": "g.txt", "content": "y" * 15, "agent_name": "scribe"}
    assert admin.client.post(f"{_API}/generate", json=body).status_code == 200
    body["filename"] = "g2.txt"
    body["content"] = "z" * 6
    assert _code(admin.client.post(f"{_API}/generate", json=body)) == quota.QUOTA_EXCEEDED
    assert _rows(small, "SELECT uploaded_by, SUM(file_size) FROM conversation_files") == [("scribe", 15)]


def test_a_copy_is_a_reference_that_stores_no_bytes_so_it_cannot_pass_the_quota(small):
    file_id = _seed(small, body=b"c" * 20)  # alice is exactly at the quota
    copied = _as_admin(small).client.post(f"{_API}/files/{file_id}/copy", json={"new_filename": "c2.txt"})
    assert copied.status_code == 200, copied.text
    assert _rows(small, "SELECT COUNT(*), SUM(file_size) FROM conversation_files") == [(1, 20)]


def test_a_content_update_cannot_grow_a_file_past_the_quota(small):
    file_id = _seed(small, body=b"u" * 10)
    admin = _as_admin(small)
    assert (
        _code(admin.client.put(f"{_API}/files/{file_id}/content", json={"content": "v" * 21})) == quota.QUOTA_EXCEEDED
    )
    assert _rows(small, "SELECT file_size FROM conversation_files") == [(10,)]
    assert [p.read_bytes() for p in (small.tmp / "storage").rglob("*") if p.is_file()] == [b"u" * 10]
    assert admin.client.put(f"{_API}/files/{file_id}/content", json={"content": "v" * 20}).status_code == 200
    assert _rows(small, "SELECT file_size FROM conversation_files") == [(20,)]


def test_the_manager_itself_refuses_so_no_caller_can_skip_the_quota(small):
    asyncio.run(small.real.add_file(_SESSION, b"m" * 20, "m.txt", uploaded_by="dora"))
    with pytest.raises(quota.UploadRefused) as caught:
        asyncio.run(small.real.add_file(_SESSION, b"n" * 1, "n.txt", uploaded_by="dora"))
    assert caught.value.detail["code"] == quota.QUOTA_EXCEEDED and caught.value.detail["live_bytes"] == 20


def test_a_deduplicated_reference_stores_no_bytes_and_needs_no_room(small):
    asyncio.run(small.real.add_file(_SESSION, b"d" * 20, "d.txt", uploaded_by="dora"))
    again = asyncio.run(small.real.add_file(_SESSION, b"d" * 20, "d-again.txt", uploaded_by="dora"))
    assert again["deduplicated"] is True


def test_the_refusal_says_how_much_is_live_and_how_much_awaits_human_review(small):
    assert _upload(small, body=b"l" * 8).status_code == 200
    gone = _upload(small, name="p.txt", body=b"p" * 12).json()["file_info"]
    asyncio.run(small.real.delete_file(_SESSION, gone["file_id"]))
    response = _upload(small, name="q.txt", body=b"q" * 5)
    assert _code(response) == quota.QUOTA_EXCEEDED
    detail = response.json()["detail"]
    assert (detail["live_bytes"], detail["pending_removal_bytes"], detail["remaining_bytes"]) == (8, 12, 0)
    assert "awaiting human review" in detail["message"]


def test_space_returns_only_once_a_removal_marks_the_queue_row_processed(small):
    info = _upload(small, body=b"x" * 20).json()["file_info"]
    asyncio.run(small.real.delete_file(_SESSION, info["file_id"]))
    assert _code(_upload(small, name="two.txt", body=b"y" * 5)) == quota.QUOTA_EXCEEDED
    assert asyncio.run(small.real.remaining_upload_quota("alice")) == 0  # nothing freed by the delete alone
    conn = sqlite3.connect(small.db)
    conn.execute("UPDATE file_cleanup_queue SET is_processed = 1 WHERE file_id = ?", (info["file_id"],))
    conn.commit()
    conn.close()  # what an approved removal does (#20234); the test purges nothing itself
    assert asyncio.run(small.real.remaining_upload_quota("alice")) == 20
    assert _upload(small, name="two.txt", body=b"y" * 5).status_code == 200


def test_the_ownerless_bucket_is_one_shared_owner_held_to_the_same_quota(small):
    asyncio.run(small.real.add_file(_SESSION, b"a" * 15, "a.txt", uploaded_by=None))
    with pytest.raises(quota.UploadRefused):
        asyncio.run(small.real.add_file(_SESSION, b"b" * 6, "b.txt", uploaded_by=None))
    assert asyncio.run(small.real.remaining_upload_quota(None)) == 5
    assert asyncio.run(small.real.remaining_upload_quota("alice")) == 20  # a named owner is unaffected


def test_concurrent_writers_cannot_overshoot_the_quota(real, monkeypatch, tmp_path):  # noqa: F811
    """Eight independent managers (their own locks) race on one database file: only two 10-byte files fit in 25."""
    monkeypatch.setattr(quota, "USER_QUOTA_BYTES", 25)
    managers = [
        ConversationFileManager(storage_dir=tmp_path / "storage", db_path=tmp_path / "files.db") for _ in range(8)
    ]
    for manager in managers:
        monkeypatch.setattr(manager, "_get_redis_sessions", AsyncMock(side_effect=RedisConnectionError("down")))

    async def race():
        jobs = [
            m.add_file(_SESSION, bytes([65 + i]) * 10, f"f{i}.txt", uploaded_by="erin") for i, m in enumerate(managers)
        ]
        return await asyncio.gather(*jobs, return_exceptions=True)

    results = asyncio.run(race())
    assert sum(isinstance(r, dict) for r in results) == 2, results
    assert all(isinstance(r, quota.UploadRefused) for r in results if not isinstance(r, dict)), results
    assert _rows(real, "SELECT COUNT(*), SUM(file_size) FROM conversation_files") == [(2, 20)]
    assert len([p for p in (tmp_path / "storage").rglob("*") if p.is_file()]) == 2  # refused bytes are not left behind


def test_uploaded_by_is_indexed(real):  # noqa: F811
    names = {r[0] for r in _rows(real, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "idx_conversation_files_uploaded_by" in names
    plan = _rows(real, "EXPLAIN QUERY PLAN SELECT SUM(file_size) FROM conversation_files WHERE uploaded_by IS 'x'")
    assert any("idx_conversation_files_uploaded_by" in str(row) for row in plan), plan
