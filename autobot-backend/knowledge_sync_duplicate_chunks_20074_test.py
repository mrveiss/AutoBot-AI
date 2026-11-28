# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chunk the KB already holds is present, and is not deleted while a file relies on it (#20074)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge_sync_incremental import FileMetadata, IncrementalKnowledgeSync, SyncMetrics


def _sync(tmp_path, store_results=()):
    sync = IncrementalKnowledgeSync.__new__(IncrementalKnowledgeSync)
    sync.project_root = tmp_path
    sync.file_metadata = {}
    sync.kb = MagicMock()
    sync.kb.store_fact = AsyncMock(side_effect=list(store_results))
    sync.kb.delete_fact = AsyncMock(return_value={"status": "success"})
    return sync


def _metadata(path, fact_ids=(), shared=()):
    return FileMetadata(
        path=str(path),
        relative_path=path.name,
        content_hash="h",
        size=1,
        modified_time=1.0,
        fact_ids=list(fact_ids),
        shared_fact_ids=list(shared),
    )


def _chunks(count):
    return [SimpleNamespace(content=f"c{i}", semantic_score=1.0, sentences=["s"]) for i in range(count)]


@pytest.mark.asyncio
async def test_a_file_with_a_chunk_the_kb_holds_counts_as_stored():
    sync = _sync(
        Path("/x"),
        [{"status": "success", "fact_id": "new"}, {"status": "duplicate", "fact_id": "held"}],
    )
    chunks = _chunks(2)
    _, fact_ids, shared = await sync._store_chunks_in_knowledge_base(chunks, Path("a.md"), {})
    assert (fact_ids, shared) == (["new"], ["held"])
    assert sync._is_durably_stored(chunks, fact_ids + shared, Path("a.md")) is True


@pytest.mark.parametrize(
    "result",
    [
        {"status": "error", "message": "boom"},
        {"status": "duplicate"},
        {"status": "duplicate", "fact_id": "?"},  # the semantic check's placeholder when metadata has no id
    ],
)
@pytest.mark.asyncio
async def test_a_chunk_without_a_usable_id_still_counts_as_rejected(result):
    sync = _sync(Path("/x"), [result])
    chunks = _chunks(1)
    _, fact_ids, shared = await sync._store_chunks_in_knowledge_base(chunks, Path("a.md"), {})
    assert sync._is_durably_stored(chunks, fact_ids + shared, Path("a.md")) is False


@pytest.fixture
def proposed(monkeypatch):
    seen = AsyncMock(return_value=True)
    monkeypatch.setattr("knowledge_sync_removal_proposals.propose_removal", seen)
    return seen


@pytest.mark.asyncio
async def test_removing_a_file_proposes_not_a_fact_another_file_relies_on(tmp_path, proposed):
    sync = _sync(tmp_path)
    sync.kb.get_fact = MagicMock(return_value={"content": "x"})
    gone, other = tmp_path / "gone.md", tmp_path / "other.md"
    sync.file_metadata[str(gone)] = _metadata(gone, ["own", "both"])
    sync.file_metadata[str(other)] = _metadata(other, shared=["both"])
    await sync._remove_obsolete_knowledge([str(gone)])
    sync.kb.delete_fact.assert_not_awaited()
    assert proposed.await_args.args[2] == {"gone.md": ["own"]}


@pytest.mark.asyncio
async def test_a_removed_file_with_no_stored_fact_left_only_drops_the_sync_record(tmp_path, proposed):
    sync = _sync(tmp_path)
    sync.kb.get_fact = MagicMock(return_value=None)
    gone = tmp_path / "gone.md"
    sync.file_metadata[str(gone)] = _metadata(gone, ["own"])
    await sync._remove_obsolete_knowledge([str(gone)])
    proposed.assert_not_awaited()
    assert str(gone) not in sync.file_metadata


def test_a_new_version_keeps_what_it_still_relies_on_or_another_file_does(tmp_path):
    sync = _sync(tmp_path)
    doc, other = tmp_path / "doc.md", tmp_path / "other.md"
    sync.file_metadata[str(doc)] = _metadata(doc, ["old", "kept", "theirs"], ["was-shared"])
    sync.file_metadata[str(other)] = _metadata(other, shared=["theirs"])
    replaced = sync._update_metadata_from_results([doc], [_metadata(doc, ["new"], ["kept"])], SyncMetrics())
    assert replaced == ["old", "was-shared"]


def test_a_state_file_from_before_the_field_loads_with_nothing_shared(tmp_path):
    saved = {
        "path": "p",
        "relative_path": "p",
        "content_hash": "h",
        "size": 1,
        "modified_time": 1.0,
        "fact_ids": ["a"],
    }
    assert FileMetadata(**saved).shared_fact_ids == []
