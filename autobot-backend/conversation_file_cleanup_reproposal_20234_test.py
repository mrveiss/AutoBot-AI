# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Re-proposal of conversation file cleanups, and the hard-delete gate (#20234, #20488, #17038).

The real proposer, approval gate service and dispatcher run on a real SQLite ``approvals`` table
(JSONB rendered as JSON), so the lookup that decides "already proposed" executes as SQL rather
than being stubbed. A denial must stay denied; a failed or expired proposal must come back.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles

from conversation_file_manager import ConversationFileManager
from models.approval import Approval, ApprovalComment, TaskApprovalLink
from services import approval_execution, conversation_file_cleanup_action, conversation_file_cleanup_proposals
from services.approval_gate_service import ApprovalGateService

pytestmark = pytest.mark.asyncio

_URL = "sqlite+aiosqlite:///:memory:"


@compiles(JSONB, "sqlite")
def _jsonb_as_json(element, compiler, **kw):
    return "JSON"


@pytest.fixture
async def manager(tmp_path):
    mgr = ConversationFileManager(storage_dir=tmp_path / "storage", db_path=tmp_path / "files.db")
    mgr._initialize_schema()
    mgr._invalidate_session_cache = AsyncMock()
    return mgr


@pytest.fixture
async def db():
    engine = create_async_engine(_URL)  # canonical: ignore py-adhoc-db-engine (in-memory test store)
    async with engine.begin() as conn:
        for model in (Approval, ApprovalComment, TaskApprovalLink):
            await conn.run_sync(model.__table__.create)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
def gate(monkeypatch, manager):
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})
    monkeypatch.setattr(ApprovalGateService, "_notify", AsyncMock())
    monkeypatch.setattr(conversation_file_cleanup_action, "audit_log", AsyncMock(return_value=True))
    monkeypatch.setattr(approval_execution, "audit_log", AsyncMock(return_value=True))
    monkeypatch.setattr("conversation_file_manager.get_conversation_file_manager", AsyncMock(return_value=manager))
    conversation_file_cleanup_action.register_conversation_file_cleanup_action()


async def _sql(mgr, sql, args=()):
    conn = await mgr._get_async_db_connection()
    try:
        async with conn.execute(sql, args) as cur:
            rows = await cur.fetchall()
        await conn.commit()
        return rows
    finally:
        await conn.close()


async def _make_due(mgr):
    await _sql(mgr, "UPDATE file_cleanup_queue SET scheduled_deletion_time = datetime('now', '-1 day')")


async def _deleted_file(mgr, session="s1", name="a.txt"):
    stored = await mgr.add_file(session, b"bytes", name, uploaded_by="u")
    await mgr.delete_file(session, stored["file_id"])
    await _make_due(mgr)
    return stored


async def _sweep(manager, db):
    from conversation_file_cleanup import list_cleanup_candidates

    return await conversation_file_cleanup_proposals.propose_cleanups_for(db, await list_cleanup_candidates(manager))


async def test_a_pending_proposal_is_not_repeated(manager, db, gate):
    await _deleted_file(manager)
    assert len(await _sweep(manager, db)) == 1
    assert await _sweep(manager, db) == []


async def test_a_denied_proposal_stays_denied(manager, db, gate):
    await _deleted_file(manager)
    (approval_id,) = await _sweep(manager, db)
    await ApprovalGateService(db).reject(uuid.UUID(approval_id), decided_by="alice", author_type="human")

    assert await _sweep(manager, db) == []
    assert await _sweep(manager, db) == []


async def test_a_failed_execution_is_proposed_again(manager, db, gate):
    """Approved, but the removal was refused (the file is live): the bytes remain, so retry."""
    stored = await _deleted_file(manager)
    (first,) = await _sweep(manager, db)
    await _sql(manager, "UPDATE conversation_files SET is_deleted = 0 WHERE file_id = ?", (stored["file_id"],))
    await ApprovalGateService(db).approve(uuid.UUID(first), decided_by="alice", author_type="human")
    await _sql(manager, "UPDATE conversation_files SET is_deleted = 1 WHERE file_id = ?", (stored["file_id"],))
    assert (manager.storage_dir / "sessions" / "s1" / stored["stored_filename"]).exists()

    (second,) = await _sweep(manager, db)

    assert second != first


async def test_an_expired_proposal_is_proposed_again(manager, db, gate):
    await _deleted_file(manager)
    (first,) = await _sweep(manager, db)
    approval = await db.get(Approval, uuid.UUID(first))
    approval.status = "expired"
    await db.commit()

    (second,) = await _sweep(manager, db)

    assert second != first


async def test_a_removed_file_is_not_proposed_again(manager, db, gate):
    await _deleted_file(manager)
    (approval_id,) = await _sweep(manager, db)
    await ApprovalGateService(db).approve(uuid.UUID(approval_id), decided_by="alice", author_type="human")

    assert await _sweep(manager, db) == []


async def test_hard_delete_removes_no_bytes_and_leaves_them_to_the_gate(manager, db, gate):
    stored = await manager.add_file("s1", b"bytes", "a.txt", uploaded_by="u")
    path = manager.storage_dir / "sessions" / "s1" / stored["stored_filename"]

    assert await manager.delete_session_files("s1", hard_delete=True) == 1

    assert path.exists()
    assert (await _sql(manager, "SELECT is_deleted FROM conversation_files"))[0][0] == 1
    await _make_due(manager)
    assert len(await _sweep(manager, db)) == 1, "the bytes now wait on a proposal"


async def test_cleanup_session_defaults_to_the_gate_too(manager, gate):
    stored = await manager.add_file("s1", b"bytes", "a.txt", uploaded_by="u")
    path = manager.storage_dir / "sessions" / "s1" / stored["stored_filename"]

    result = await manager.cleanup_session("s1")

    assert result["files_deleted"] == 1 and path.exists()
