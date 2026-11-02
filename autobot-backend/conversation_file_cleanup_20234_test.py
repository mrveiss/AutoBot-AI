# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Deleted conversation files: queue -> proposal -> human approval -> removal (#20234, #17038).

Real SQLite, real schema and a real directory; the real proposer, approval gate and dispatcher.
Only the approval DB session (a fake) and the audit sink are stubbed.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from conversation_file_manager import ConversationFileManager
from services import approval_execution, conversation_file_cleanup_action, conversation_file_cleanup_proposals
from services.approval_gate_service import ApprovalGateService
from testkit.fake_approval_session import ApprovalClaimSession

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def manager(tmp_path):
    mgr = ConversationFileManager(storage_dir=tmp_path / "storage", db_path=tmp_path / "files.db")
    mgr._initialize_schema()
    mgr._invalidate_session_cache = AsyncMock()
    return mgr


async def _sql(mgr, sql, args=()):
    conn = await mgr._get_async_db_connection()
    try:
        async with conn.execute(sql, args) as cur:
            rows = await cur.fetchall()
        await conn.commit()
        return rows
    finally:
        await conn.close()


async def _deleted_file(mgr, session="s1", name="a.txt", content=b"bytes"):
    stored = await mgr.add_file(session, content, name, uploaded_by="u")
    await mgr.delete_file(session, stored["file_id"])
    await _sql(mgr, "UPDATE file_cleanup_queue SET scheduled_deletion_time = datetime('now', '-1 day')")
    return stored


@pytest.fixture
def gate(monkeypatch, manager):
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())
    audited = []

    async def _audit(operation, **kwargs):
        audited.append({"operation": operation, **kwargs})
        return True

    monkeypatch.setattr(conversation_file_cleanup_action, "audit_log", _audit)
    monkeypatch.setattr(approval_execution, "audit_log", _audit)
    monkeypatch.setattr(conversation_file_cleanup_proposals, "_already_proposed", AsyncMock(return_value=set()))
    monkeypatch.setattr("conversation_file_manager.get_conversation_file_manager", AsyncMock(return_value=manager))
    conversation_file_cleanup_action.register_conversation_file_cleanup_action()
    return audited


async def _noop():
    return None


async def _propose(manager, session):
    from conversation_file_cleanup import list_cleanup_candidates

    candidates = await list_cleanup_candidates(manager)
    return await conversation_file_cleanup_proposals.propose_cleanups_for(session, candidates)


async def test_due_queue_entries_become_pending_proposals_and_remove_nothing(manager, gate):
    stored = await _deleted_file(manager)
    session = ApprovalClaimSession()

    ids = await _propose(manager, session)

    assert len(ids) == 1
    assert session.approval.status == "pending"
    assert session.approval.context["file_id"] == stored["file_id"]
    assert "file_path" not in session.approval.context
    assert (manager.storage_dir / "sessions" / "s1" / stored["stored_filename"]).exists(), "unapproved removes nothing"


async def test_a_live_file_is_never_a_candidate(manager, gate):
    await manager.add_file("s1", b"keep", "keep.txt", uploaded_by="u")
    await _sql(manager, "UPDATE file_cleanup_queue SET scheduled_deletion_time = datetime('now', '-1 day')")
    assert await _propose(manager, ApprovalClaimSession()) == []


async def test_approving_removes_the_bytes_and_records_it(manager, gate):
    stored = await _deleted_file(manager)
    path = manager.storage_dir / "sessions" / "s1" / stored["stored_filename"]
    session = ApprovalClaimSession()
    ids = await _propose(manager, session)

    await ApprovalGateService(session).approve(uuid.UUID(ids[0]), decided_by="alice", author_type="human", comment=None)

    assert not path.exists()
    assert [a["operation"] for a in gate] == ["conversation_file.cleanup"]
    assert gate[0]["result"] == "success"
    assert gate[0]["user_id"] == "alice"
    processed = await _sql(
        manager, "SELECT is_processed FROM file_cleanup_queue WHERE file_id = ?", (stored["file_id"],)
    )
    assert [r[0] for r in processed] == [1]
    assert await _sql(
        manager, "SELECT 1 FROM conversation_files WHERE file_id = ?", (stored["file_id"],)
    ), "record outlives bytes"
    stats = await manager.get_storage_stats()
    assert stats["pending_cleanup_files"] == 0


async def test_a_denied_entry_stays_on_disk_and_pending_in_the_stats(manager, gate):
    stored = await _deleted_file(manager)
    path = manager.storage_dir / "sessions" / "s1" / stored["stored_filename"]
    session = ApprovalClaimSession()
    ids = await _propose(manager, session)

    await ApprovalGateService(session).reject(uuid.UUID(ids[0]), decided_by="alice", author_type="human", comment=None)

    assert path.exists() and gate == []
    stats = await manager.get_storage_stats()
    assert stats["pending_cleanup_files"] == 1
    assert stats["pending_cleanup_bytes"] == len(b"bytes")


async def test_a_path_outside_the_store_is_refused(manager, gate, tmp_path):
    from conversation_file_cleanup import remove_approved_file

    stored = await _deleted_file(manager)
    outside = tmp_path / "outside.txt"
    await asyncio.to_thread(outside.write_bytes, b"not ours")
    await _sql(
        manager, "UPDATE conversation_files SET file_path = ? WHERE file_id = ?", (str(outside), stored["file_id"])
    )

    result = await remove_approved_file(manager, stored["file_id"])

    assert result["removed"] is False and "outside" in result["reason"]
    assert outside.exists()
    assert (await _sql(manager, "SELECT is_processed FROM file_cleanup_queue"))[0][0] == 0


async def test_a_restored_file_is_not_removed(manager, gate):
    from conversation_file_cleanup import remove_approved_file

    stored = await _deleted_file(manager)
    path = manager.storage_dir / "sessions" / "s1" / stored["stored_filename"]
    await _sql(manager, "UPDATE conversation_files SET is_deleted = 0 WHERE file_id = ?", (stored["file_id"],))

    result = await remove_approved_file(manager, stored["file_id"])

    assert result["removed"] is False and "live" in result["reason"]
    assert path.exists()


async def test_a_file_still_referenced_by_a_live_record_is_not_removed(manager, gate):
    from conversation_file_cleanup import remove_approved_file

    stored = await _deleted_file(manager)
    path = manager.storage_dir / "sessions" / "s1" / stored["stored_filename"]
    live = await manager.add_file("s2", b"other", "b.txt", uploaded_by="u")
    await _sql(manager, "UPDATE conversation_files SET file_path = ? WHERE file_id = ?", (str(path), live["file_id"]))

    result = await remove_approved_file(manager, stored["file_id"])

    assert result["removed"] is False and "referenced" in result["reason"]
    assert path.exists()
