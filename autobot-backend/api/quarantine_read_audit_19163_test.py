# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two owner-approved opt-out readers, and the summaries that must not launder (#19163).

The admin ChromaDB explorer and the knowledge lint may read quarantined facts, audited and marked.
Summaries derived from a quarantined fact carry its collection marker and summary search withholds
them. Everything audits through ``services.audit_logger.audit_log``, the one audit path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import knowledge_chroma, knowledge_maintenance
from api.quarantine_read_audit import INTERNAL_SERVICE_ACTOR, request_actor
from autobot_shared.ssot_config import config
from knowledge.pipeline.loaders.chromadb_loader import ChromaDBLoader
from knowledge.quarantine import audit_quarantine_read
from knowledge.summary_search import SummarySearchService
from services.audit.taxonomy import AuditAction
from services.knowledge.contradiction_detector import ConflictPair, _mark_quarantined

_RESEARCH = config.research_quarantine_collection
_HELPER_AUDIT = "api.quarantine_read_audit.audit_quarantine_read"
_REQUEST = MagicMock()


@pytest.mark.asyncio
async def test_audit_helper_writes_through_the_canonical_audit_log():
    with patch("services.audit_logger.audit_log", AsyncMock(return_value=True)) as audit_log:
        await audit_quarantine_read("admin", "kb.search", ["a", "b"])

    audit_log.assert_awaited_once()
    assert audit_log.await_args.args == (AuditAction.KNOWLEDGE_QUARANTINE_READ.value,)
    kwargs = audit_log.await_args.kwargs
    assert kwargs["user_id"] == "admin"
    assert kwargs["details"] == {"surface": "kb.search", "count": 2, "ids": ["a", "b"]}


@pytest.mark.asyncio
async def test_request_actor_is_the_human_else_the_internal_service():
    with patch("api.quarantine_read_audit.resolve_human_user", AsyncMock(return_value={"username": "root"})):
        assert await request_actor(_REQUEST) == "root"
    with patch("api.quarantine_read_audit.resolve_human_user", AsyncMock(return_value=None)):
        assert await request_actor(_REQUEST) == INTERNAL_SERVICE_ACTOR


def _collection(ids, metadatas):
    collection = AsyncMock()
    collection.get = AsyncMock(return_value={"ids": ids, "documents": ["d"] * len(ids), "metadatas": metadatas})
    collection.count = AsyncMock(return_value=len(ids))
    return collection


@pytest.mark.asyncio
async def test_explorer_marks_and_audits_quarantined_rows():
    collection = _collection(["a", "q"], [{}, {"collection": _RESEARCH}])
    client = AsyncMock()
    client.get_collection = AsyncMock(return_value=collection)
    with (
        patch.object(knowledge_chroma, "get_async_chromadb_client", AsyncMock(return_value=client)),
        patch("api.quarantine_read_audit.resolve_human_user", AsyncMock(return_value={"username": "root"})),
        patch(_HELPER_AUDIT, AsyncMock(return_value=True)) as audit,
    ):
        response = await knowledge_chroma.list_documents("kb", limit=10, offset=0, _=True, request=_REQUEST)

    assert response.data["quarantined_ids"] == ["q"]
    audit.assert_awaited_once_with("root", "chroma.list_documents:kb", ["q"])


@pytest.mark.asyncio
async def test_explorer_writes_no_audit_entry_when_no_row_is_quarantined():
    client = AsyncMock()
    client.get_collection = AsyncMock(return_value=_collection(["a"], [{}]))
    with (
        patch.object(knowledge_chroma, "get_async_chromadb_client", AsyncMock(return_value=client)),
        patch(_HELPER_AUDIT, AsyncMock(return_value=True)) as audit,
    ):
        response = await knowledge_chroma.list_documents("kb", limit=10, offset=0, _=True, request=_REQUEST)

    assert response.data["quarantined_ids"] == []
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_lint_marks_quarantined_chunks_and_audits_once_per_run():
    store = MagicMock()
    store._collection.get.return_value = {
        "ids": ["a", "q"],
        "documents": ["plain", "held"],
        "metadatas": [{}, {"collection": _RESEARCH}],
    }
    kb = SimpleNamespace(vector_store=store)
    chunks = await knowledge_maintenance._fetch_all_chunks(kb)

    assert chunks[0] == {"text": "plain", "metadata": {}}
    assert chunks[1]["quarantined"] is True and chunks[1]["id"] == "q"

    with (
        patch.object(knowledge_maintenance, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch.object(knowledge_maintenance, "audit_admin_quarantine_read", AsyncMock()) as audit,
    ):
        await knowledge_maintenance.start_lint(MagicMock(), admin_check=True, req=_REQUEST)

    audit.assert_awaited_once_with(_REQUEST, "knowledge.lint", ["q"])


def test_a_conflict_citing_a_quarantined_chunk_is_marked():
    pair = ConflictPair(chunk_a="held", chunk_b="plain", explanation="e", confidence=0.9)
    other = ConflictPair(chunk_a="x", chunk_b="y", explanation="e", confidence=0.9)
    _mark_quarantined([pair, other], [{"text": "held", "quarantined": True}, {"text": "plain"}])
    assert (pair.quarantined, other.quarantined) == (True, False)


@pytest.mark.asyncio
async def test_summary_search_filters_quarantine_in_every_reader():
    collection = AsyncMock()
    collection.query = AsyncMock(return_value={"ids": [[]], "documents": [[]], "metadatas": [[]]})
    collection.get = AsyncMock(return_value={"ids": [], "documents": [], "metadatas": []})
    client = AsyncMock()
    client.get_collection = AsyncMock(return_value=collection)
    service = SummarySearchService(client)
    clause = {"collection": {"$ne": _RESEARCH}}

    await service.search_summaries("q", level="document")
    assert clause in collection.query.await_args.kwargs["where"]["$and"]
    await service.get_document_overview("00000000-0000-0000-0000-000000000001")
    assert all(clause in c.kwargs["where"]["$and"] for c in collection.get.await_args_list)


@pytest.mark.asyncio
async def test_drill_down_refuses_a_quarantined_summary_and_filters_children():
    collection = AsyncMock()
    collection.get = AsyncMock(
        return_value={"ids": ["s"], "documents": ["held"], "metadatas": [{"collection": _RESEARCH}]}
    )
    client = AsyncMock()
    client.get_collection = AsyncMock(return_value=collection)

    result = await SummarySearchService(client).drill_down("00000000-0000-0000-0000-000000000001")

    assert result == {"summary": None, "children": []}


@pytest.mark.asyncio
async def test_loader_stamps_the_source_collection_onto_every_summary():
    collection = AsyncMock()
    summaries = [
        SimpleNamespace(
            id=i,
            content="c",
            level="chunk",
            source_document_id=i,
            parent_summary_id=None,
            key_topics=["t"],
            word_count=1,
        )
        for i in (1, 2)
    ]
    await ChromaDBLoader()._upsert_summary_batch(collection, summaries, _RESEARCH)
    await ChromaDBLoader()._upsert_summary_batch(collection, summaries, None)

    marked, unmarked = (c.kwargs["metadatas"] for c in collection.upsert.await_args_list)
    assert all(m["collection"] == _RESEARCH for m in marked)
    assert all("collection" not in m for m in unmarked)
