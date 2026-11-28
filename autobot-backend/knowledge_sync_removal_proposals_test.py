# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sync removals beyond a changed file's own chunks are proposed and applied only on approval (#20028)."""

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import knowledge_base
import knowledge_sync_incremental as sync_module
import knowledge_sync_removal_proposals as removals
from knowledge_sync_incremental import FileMetadata, IncrementalKnowledgeSync, SyncMetrics
from models.approval import Approval
from services import approval_execution
from services.approval_gate_service import ApprovalGateService
from testkit.fake_approval_session import ApprovalClaimSession


def _meta(path, fact_ids, sync_time=None):
    return FileMetadata(
        path=str(path),
        relative_path=path.name,
        content_hash="h",
        size=1,
        modified_time=1.0,
        sync_time=sync_time,
        fact_ids=list(fact_ids),
        shared_fact_ids=[],
    )


@pytest.fixture
def world(monkeypatch):
    """One approval session, one fake KB, an audit log, and the real registered executor."""
    session = ApprovalClaimSession()
    kb = MagicMock()
    kb.get_fact = MagicMock(return_value={"content": "x", "metadata": {}})
    kb.delete_fact = AsyncMock(return_value={"status": "success"})
    audited = []

    async def _audit(operation, **kwargs):
        audited.append((operation, kwargs))
        return True

    @asynccontextmanager
    async def _factory_session():
        yield session

    async def _get_kb():
        return kb

    async def _pending(service, action, key, value):
        return next((o for o in session.added if isinstance(o, Approval) and o.context.get(key) == value), None)

    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})
    monkeypatch.setattr(ApprovalGateService, "_notify", AsyncMock())
    for target in (approval_execution, removals):
        monkeypatch.setattr(target, "audit_log", _audit)
    monkeypatch.setattr("services.kb_cleanup_proposals.audit_log", _audit)
    monkeypatch.setattr("services.kb_cleanup_proposals.find_pending_proposal", _pending)
    monkeypatch.setattr("user_management.database.get_async_session_factory", lambda: _factory_session)
    monkeypatch.setattr(knowledge_base, "get_knowledge_base", _get_kb)
    removals.register_sync_removal()
    return MagicMock(session=session, kb=kb, audited=audited)


def _approvals(world):
    return [o for o in world.session.added if isinstance(o, Approval)]


def _sync(tmp_path, kb):
    sync = IncrementalKnowledgeSync.__new__(IncrementalKnowledgeSync)
    sync.project_root = tmp_path
    sync.file_metadata = {}
    sync.kb = kb
    sync.auto_invalidation_enabled = True
    sync.knowledge_ttl_hours = 1
    sync.max_concurrent_files = 2
    sync._scanned_paths = set()
    sync._vanished_paths = []
    sync._save_sync_state = AsyncMock()
    return sync


@pytest.mark.asyncio
async def test_a_partial_tree_removal_creates_a_proposal_and_deletes_nothing(tmp_path, world):
    sync = _sync(tmp_path, world.kb)
    gone = tmp_path / "gone.md"
    sync.file_metadata[str(gone)] = _meta(gone, ["f1", "f2"])
    await sync._remove_obsolete_knowledge([str(gone)])
    (approval,) = _approvals(world)
    assert approval.status == "pending" and approval.context["action"] == "kb_sync_removal"
    assert approval.context["kind"] == "partial_tree"
    assert approval.context["sources"] == {"gone.md": ["f1", "f2"]}
    assert approval.requested_by_agent == "system:kb-sync"
    world.kb.delete_fact.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_facts_of_a_deleted_directory_are_proposed(tmp_path, world):
    sync = _sync(tmp_path, world.kb)
    gone = tmp_path / "docs" / "doc.md"
    sync.file_metadata[str(gone)] = _meta(gone, ["d1"])
    await sync._remove_obsolete_knowledge([str(gone)], removals.DIRECTORY_MISSING)
    (approval,) = _approvals(world)
    assert approval.context["kind"] == "directory_missing" and approval.context["fact_ids"] == ["d1"]
    world.kb.delete_fact.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_rerun_does_not_stack_a_second_proposal(tmp_path, world):
    sync = _sync(tmp_path, world.kb)
    gone = tmp_path / "gone.md"
    sync.file_metadata[str(gone)] = _meta(gone, ["f1"])
    await sync._remove_obsolete_knowledge([str(gone)])
    await sync._remove_obsolete_knowledge([str(gone)])
    assert len(_approvals(world)) == 1


@pytest.mark.asyncio
async def test_approving_deletes_exactly_those_facts_with_an_audit_row_each(tmp_path, world):
    sync = _sync(tmp_path, world.kb)
    gone = tmp_path / "gone.md"
    sync.file_metadata[str(gone)] = _meta(gone, ["f1", "f2"])
    await sync._remove_obsolete_knowledge([str(gone)])
    (approval,) = _approvals(world)
    await ApprovalGateService(world.session).approve(approval.id, decided_by="alice", author_type="human", comment=None)
    assert [c.args[0] for c in world.kb.delete_fact.await_args_list] == ["f1", "f2"]
    removed = [kw for op, kw in world.audited if op == "knowledge.remove"]
    assert [kw["resource"] for kw in removed] == ["fact:f1", "fact:f2"]
    assert all(kw["details"]["approval_id"] == str(approval.id) for kw in removed)


@pytest.mark.asyncio
async def test_rejecting_deletes_nothing(tmp_path, world):
    sync = _sync(tmp_path, world.kb)
    gone = tmp_path / "gone.md"
    sync.file_metadata[str(gone)] = _meta(gone, ["f1"])
    await sync._remove_obsolete_knowledge([str(gone)])
    (approval,) = _approvals(world)
    await ApprovalGateService(world.session).reject(approval.id, decided_by="alice", author_type="human", comment=None)
    world.kb.delete_fact.assert_not_awaited()


async def _run_sync_step(sync, tmp_path, monkeypatch, changed, new_ids):
    async def _process(_semaphore, _sync, file_path):
        return _meta(file_path, new_ids, sync_time=9e12)

    monkeypatch.setattr(sync_module, "_process_file_with_semaphore", _process)
    replaced_delete = AsyncMock(return_value=0)
    monkeypatch.setattr(sync_module, "delete_replaced_facts", replaced_delete)
    await sync._process_sync_changes(changed, [], SyncMetrics())
    return replaced_delete


@pytest.mark.asyncio
async def test_an_expired_fact_is_reindexed_and_its_old_copy_proposed_not_deleted(tmp_path, world, monkeypatch):
    sync = _sync(tmp_path, world.kb)
    doc = tmp_path / "doc.md"
    sync.file_metadata[str(doc)] = _meta(doc, ["old"], sync_time=1.0)
    sync._scanned_paths = {str(doc)}
    auto = await _run_sync_step(sync, tmp_path, monkeypatch, [], ["new"])
    assert sync.file_metadata[str(doc)].fact_ids == ["new"]  # refreshed by re-indexing
    (approval,) = _approvals(world)
    assert approval.context["kind"] == "expired" and approval.context["fact_ids"] == ["old"]
    auto.assert_awaited_once_with(world.kb, [])
    world.kb.delete_fact.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_changed_files_own_chunks_are_still_replaced_automatically(tmp_path, world, monkeypatch):
    sync = _sync(tmp_path, world.kb)
    doc = tmp_path / "doc.md"
    sync.file_metadata[str(doc)] = _meta(doc, ["old"])
    auto = await _run_sync_step(sync, tmp_path, monkeypatch, [Path(doc)], ["new"])
    auto.assert_awaited_once_with(world.kb, ["old"])
    assert _approvals(world) == []


@pytest.mark.asyncio
async def test_a_proposal_that_cannot_be_audit_logged_is_not_created_and_does_not_raise(tmp_path, world, monkeypatch):
    async def _refuse(operation, **kwargs):
        return False

    monkeypatch.setattr("services.kb_cleanup_proposals.audit_log", _refuse)
    sync = _sync(tmp_path, world.kb)
    gone = tmp_path / "gone.md"
    sync.file_metadata[str(gone)] = _meta(gone, ["f1"])
    await sync._remove_obsolete_knowledge([str(gone)])
    assert _approvals(world) == []
    world.kb.delete_fact.assert_not_awaited()


def test_the_executor_is_registered_with_this_module_as_its_proposer(world):
    assert approval_execution.registered_action_proposers()["kb_sync_removal"] == "knowledge_sync_removal_proposals"
