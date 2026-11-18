# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A re-sync leaves exactly the new facts in the fact store and the vector store (#20026)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import knowledge_sync_incremental as sync_module
import knowledge_sync_replacement as replacement
from knowledge_sync_incremental import FileMetadata, IncrementalKnowledgeSync, SyncMetrics


class FakeKB:
    """In-memory stand-in: one dict for the fact rows, one for the vectors, as delete_fact removes both."""

    def __init__(self, facts):
        self.rows = {fid: {"ingest_route": replacement.SYNC_INGEST_ROUTE} for fid in facts}
        self.vectors = {fid: [0.0] for fid in facts}
        self.delete_calls = []
        self.redis_client = MagicMock()
        self.redis_client.hget = MagicMock(return_value=None)

    def get_fact(self, fact_id):
        row = self.rows.get(fact_id)
        return {"metadata": row} if row is not None else None

    async def delete_fact(self, fact_id):
        self.delete_calls.append(fact_id)
        self.rows.pop(fact_id, None)
        self.vectors.pop(fact_id, None)
        return {"status": "success"}

    def store(self, fact_id):
        self.rows[fact_id] = {"ingest_route": replacement.SYNC_INGEST_ROUTE}
        self.vectors[fact_id] = [0.0]


def _meta(path, fact_ids):
    return FileMetadata(
        path=str(path), relative_path=path.name, content_hash="h", size=1, modified_time=1.0, fact_ids=fact_ids
    )


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(replacement, "_audit_deletion", AsyncMock(return_value=True))
    monkeypatch.setattr(replacement, "_is_protected", lambda metadata: False)
    monkeypatch.setattr(replacement, "_provenance_defaults", lambda: {})
    monkeypatch.setattr(replacement, "is_replaceable", lambda metadata: True)
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    kb = FakeKB(["a1", "a2", "b1"])
    sync = IncrementalKnowledgeSync.__new__(IncrementalKnowledgeSync)
    sync.project_root = tmp_path
    sync.kb = kb
    sync.max_concurrent_files = 1
    sync.auto_invalidation_enabled = False
    sync.file_metadata = {str(a): _meta(a, ["a1", "a2"]), str(b): _meta(b, ["b1"])}
    sync._save_sync_state = AsyncMock()
    return sync, kb, a, b


def _store_new(sync, kb, outcome):
    async def process(path):
        if isinstance(outcome, Exception):
            raise outcome
        for fid in outcome:
            kb.store(fid)
        return _meta(path, outcome)

    sync._process_file_with_gpu_chunking = process


@pytest.mark.asyncio
async def test_a_changed_file_leaves_exactly_its_new_facts_in_both_stores(world):
    sync, kb, a, _ = world
    _store_new(sync, kb, ["a3", "a4"])
    await sync._process_sync_changes([a], [], SyncMetrics())
    assert {f for f in kb.rows if f.startswith("a")} == {"a3", "a4"}
    assert {f for f in kb.vectors if f.startswith("a")} == {"a3", "a4"}
    assert sync.file_metadata[str(a)].fact_ids == ["a3", "a4"]


@pytest.mark.asyncio
async def test_another_files_facts_survive_a_resync(world):
    sync, kb, a, _ = world
    _store_new(sync, kb, ["a3"])
    await sync._process_sync_changes([a], [], SyncMetrics())
    assert "b1" in kb.rows and "b1" in kb.vectors
    assert "b1" not in kb.delete_calls


@pytest.mark.asyncio
async def test_a_failed_store_loses_nothing(world):
    sync, kb, a, _ = world
    _store_new(sync, kb, RuntimeError("store failed"))
    await sync._process_sync_changes([a], [], SyncMetrics())
    assert kb.delete_calls == []
    assert {"a1", "a2"} <= set(kb.rows) and {"a1", "a2"} <= set(kb.vectors)
    assert sync.file_metadata[str(a)].fact_ids == ["a1", "a2"]


@pytest.mark.asyncio
async def test_an_unchanged_file_is_a_no_op(world):
    sync, kb, _, _ = world
    await sync._process_sync_changes([], [], SyncMetrics())
    assert kb.delete_calls == [] and sorted(kb.rows) == ["a1", "a2", "b1"]


def test_the_module_still_exposes_the_delete_the_sync_calls():
    assert sync_module.delete_replaced_facts is replacement.delete_replaced_facts
