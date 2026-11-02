# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Two bounds on cleanup proposals (#20234): one pending per file under concurrency, and a cap on refusals.

Real SQLite for the file store and for ``approvals``; the real proposer, gate and dispatcher run.
The database-level uniqueness is exercised with an equivalent partial unique index created on SQLite
(the model's own index is PostgreSQL-only; its definition is pinned against the migration below).
"""

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import CreateIndex

from conversation_file_manager import ConversationFileManager
from models.approval import (
    PENDING_FILE_CLEANUP_INDEX,
    PENDING_FILE_CLEANUP_WHERE,
    Approval,
    ApprovalComment,
    TaskApprovalLink,
)
from services import approval_execution, conversation_file_cleanup_action, conversation_file_cleanup_proposals
from services.approval_gate_service import ApprovalGateService

pytestmark = pytest.mark.asyncio

_SQLITE_UNIQUE_PENDING = (
    "CREATE UNIQUE INDEX uq_pending ON approvals (json_extract(context, '$.file_id')) "
    "WHERE status = 'pending' AND requested_by_agent = 'conversation-file-cleanup'"
)


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
async def engine(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'approvals.db'}"
    eng = create_async_engine(url)  # canonical: ignore py-adhoc-db-engine
    async with eng.begin() as conn:
        for model in (Approval, ApprovalComment, TaskApprovalLink):
            await conn.run_sync(model.__table__.create)
    yield eng
    await eng.dispose()


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


async def _deleted_file(mgr):
    stored = await mgr.add_file("s1", b"bytes", "a.txt", uploaded_by="u")
    await mgr.delete_file("s1", stored["file_id"])
    await _sql(mgr, "UPDATE file_cleanup_queue SET scheduled_deletion_time = datetime('now', '-1 day')")
    return stored


async def _sweep(manager, db):
    from conversation_file_cleanup import list_cleanup_candidates

    return await conversation_file_cleanup_proposals.propose_cleanups_for(db, await list_cleanup_candidates(manager))


async def _refuse_once(manager, db):
    """Propose, point the file outside the store, approve: the removal is refused and counted."""
    (approval_id,) = await _sweep(manager, db)
    await ApprovalGateService(db).approve(uuid.UUID(approval_id), decided_by="alice", author_type="human")


async def test_two_concurrent_proposers_create_one_pending_proposal(manager, engine, gate, monkeypatch):
    stored = await _deleted_file(manager)
    async with engine.begin() as conn:
        await conn.execute(text(_SQLITE_UNIQUE_PENDING))
    # Both workers read "nothing proposed yet" before either inserts: only the database can stop the second.
    monkeypatch.setattr(conversation_file_cleanup_proposals, "_already_proposed", AsyncMock(return_value=set()))
    factory = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine

    async def worker():
        async with factory() as session:
            return await _sweep(manager, session)

    results = await asyncio.gather(worker(), worker())

    assert sorted(len(r) for r in results) == [0, 1]
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(Approval).where(Approval.status == "pending"))
    assert count == 1, stored["file_id"]


async def test_model_index_is_postgres_only_and_matches_the_migration():
    import importlib.util
    from pathlib import Path

    index = next(i for i in Approval.__table__.indexes if i.name == PENDING_FILE_CLEANUP_INDEX)
    ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "UNIQUE" in ddl and "(context ->> 'file_id')" in ddl and PENDING_FILE_CLEANUP_WHERE in ddl
    assert f"requested_by_agent = '{conversation_file_cleanup_proposals.REQUESTED_BY}'" in PENDING_FILE_CLEANUP_WHERE
    assert f"= '{conversation_file_cleanup_proposals.ACTION}'" in PENDING_FILE_CLEANUP_WHERE
    path = Path(__file__).parent / "migrations/versions/20261101_110_approvals_pending_file_cleanup_unique.py"
    spec = importlib.util.spec_from_file_location("mig109", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._WHERE == PENDING_FILE_CLEANUP_WHERE and mod._INDEX == PENDING_FILE_CLEANUP_INDEX


async def test_a_refused_removal_stops_being_proposed_after_the_cap(manager, engine, gate, tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOBOT_CONVERSATION_FILE_CLEANUP_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("AUTOBOT_CONVERSATION_FILE_CLEANUP_COOLDOWN_SECONDS", "0")
    stored = await _deleted_file(manager)
    outside = tmp_path / "outside.txt"
    await asyncio.to_thread(outside.write_bytes, b"not ours")
    await _sql(
        manager, "UPDATE conversation_files SET file_path = ? WHERE file_id = ?", (str(outside), stored["file_id"])
    )

    async with AsyncSession(engine, expire_on_commit=False) as db:
        await _refuse_once(manager, db)
        assert (await manager.get_storage_stats())["stuck_cleanup_files"] == 0
        await _refuse_once(manager, db)
        assert await _sweep(manager, db) == [], "capped: no third proposal"
        total = await db.scalar(select(func.count()).select_from(Approval))

    assert total == 2
    stats = await manager.get_storage_stats()
    assert stats["stuck_cleanup_files"] == 1 and stats["stuck_cleanup_bytes"] == len(b"bytes")
    assert stats["stuck_cleanup"][0]["file_id"] == stored["file_id"]
    assert stats["stuck_cleanup"][0]["failed_attempts"] == 2
    assert "outside" in stats["stuck_cleanup"][0]["last_reason"]
    assert stats["pending_cleanup_files"] == 1, "the bytes are still on disk and still counted as pending"
    assert outside.exists()


async def test_a_refusal_inside_the_cooldown_is_not_proposed_again(manager, engine, gate, tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOBOT_CONVERSATION_FILE_CLEANUP_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("AUTOBOT_CONVERSATION_FILE_CLEANUP_COOLDOWN_SECONDS", "3600")
    stored = await _deleted_file(manager)
    outside = tmp_path / "outside.txt"
    await asyncio.to_thread(outside.write_bytes, b"not ours")
    await _sql(
        manager, "UPDATE conversation_files SET file_path = ? WHERE file_id = ?", (str(outside), stored["file_id"])
    )

    async with AsyncSession(engine, expire_on_commit=False) as db:
        await _refuse_once(manager, db)
        assert await _sweep(manager, db) == [], "cooling down"
        await _sql(manager, "UPDATE file_cleanup_attempts SET last_failed_at = datetime('now', '-2 hours')")
        assert len(await _sweep(manager, db)) == 1, "cooldown over, under the cap: proposed again"
    assert (await manager.get_storage_stats())["stuck_cleanup_files"] == 0


async def test_a_successful_removal_is_never_counted(manager, engine, gate):
    await _deleted_file(manager)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        (approval_id,) = await _sweep(manager, db)
        await ApprovalGateService(db).approve(uuid.UUID(approval_id), decided_by="alice", author_type="human")
    assert await _sql(manager, "SELECT 1 FROM file_cleanup_attempts") == []
