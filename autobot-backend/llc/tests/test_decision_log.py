# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for DecisionLogWriter and DecisionLogReader — GH#8243.

Test coverage:
- DecisionLogWriter.write() indexes a resolved approval to the decisions KB
- DecisionLogWriter.write() raises ValueError for pending approvals
- DecisionLogWriter.write() is idempotent (already-indexed doc is skipped)
- DecisionLogWriter.write() propagates RuntimeError on KB failure
- DecisionLogReader.search() returns results from ChromaDB query
- DecisionLogReader.search() returns [] when collection does not exist
- DecisionLogReader.list_decisions() returns all items and filters by type/date
- DecisionLogReader.list_decisions() returns [] when collection does not exist
- ApprovalService.log_decision_to_kb() calls DecisionLogWriter.write()
- ApprovalService.log_decision_to_kb() swallows KB exceptions (best-effort)
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.kb.decision_log import (
    DecisionLogReader,
    DecisionLogWriter,
    _compose_document,
    _decisions_collection,
)
from llc.models.enums import ApprovalStatus, ApprovalType
from llc.services.approval import ApprovalService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_approval(
    *,
    status: ApprovalStatus = ApprovalStatus.APPROVED,
    approval_type: ApprovalType = ApprovalType.STRATEGY,
    decision_note: str = "",
) -> MagicMock:
    a = MagicMock()
    a.id = uuid.uuid4()
    a.company_id = uuid.uuid4()
    a.type = approval_type.value
    a.status = status.value
    a.requested_by_agent_id = uuid.uuid4()
    a.decided_by_agent_id = uuid.uuid4()
    a.decided_at = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {}
    if decision_note:
        payload["decision_note"] = decision_note
    a.payload = payload
    return a


def _make_chromadb_client(*, collection_exists: bool = True) -> MagicMock:
    """Build a mock ChromaDB async client with get/add/query stubs."""
    client = AsyncMock()
    collection = AsyncMock()

    # Default: no existing documents
    collection.get = AsyncMock(return_value={"ids": [], "documents": [], "metadatas": []})
    collection.add = AsyncMock()
    collection.query = AsyncMock(
        return_value={
            "ids": [["decision:abc"]],
            "documents": [["Type: strategy\nDecision: approved"]],
            "metadatas": [[{"approval_type": "strategy", "decision": "approved"}]],
            "distances": [[0.1]],
        }
    )

    client.get_or_create_collection = AsyncMock(return_value=collection)

    if collection_exists:
        client.get_collection = AsyncMock(return_value=collection)
    else:
        client.get_collection = AsyncMock(side_effect=Exception("Collection not found"))

    return client, collection


def _make_kb(client: MagicMock) -> MagicMock:
    kb = MagicMock()
    kb._async_chroma_client = client
    return kb


# ---------------------------------------------------------------------------
# _compose_document
# ---------------------------------------------------------------------------


def test_compose_document_includes_all_fields() -> None:
    approval = _make_approval(decision_note="Good strategic fit")
    doc = _compose_document(approval)
    assert approval.type in doc
    assert approval.status in doc
    assert str(approval.requested_by_agent_id) in doc
    assert "Good strategic fit" in doc


def test_compose_document_omits_rationale_when_absent() -> None:
    approval = _make_approval()
    doc = _compose_document(approval)
    assert "Rationale:" not in doc


def test_decisions_collection_name() -> None:
    company_id = "abc-123"
    name = _decisions_collection(company_id)
    assert "company" in name
    assert company_id in name
    assert "decisions" in name


# ---------------------------------------------------------------------------
# DecisionLogWriter.write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_indexes_resolved_approval() -> None:
    """write() should add a document to the decisions collection."""
    approval = _make_approval()
    client, collection = _make_chromadb_client()
    kb = _make_kb(client)

    with patch("knowledge.get_knowledge_base", new_callable=AsyncMock) as mock_kb:
        mock_kb.return_value = kb
        writer = DecisionLogWriter()
        await writer.write(approval)

    collection.add.assert_awaited_once()
    call_kwargs = collection.add.call_args[1]
    assert f"decision:{approval.id}" in call_kwargs["ids"]
    assert call_kwargs["metadatas"][0]["decision"] == approval.status
    assert call_kwargs["metadatas"][0]["approval_type"] == approval.type


@pytest.mark.asyncio
async def test_write_raises_for_pending_approval() -> None:
    """write() must raise ValueError when approval is still pending."""
    approval = _make_approval(status=ApprovalStatus.PENDING)
    writer = DecisionLogWriter()

    with pytest.raises(ValueError, match="pending"):
        await writer.write(approval)


@pytest.mark.asyncio
async def test_write_is_idempotent() -> None:
    """write() should skip add() when the document is already in the collection."""
    approval = _make_approval()
    client, collection = _make_chromadb_client()
    # Simulate existing document
    collection.get = AsyncMock(
        return_value={"ids": [f"decision:{approval.id}"], "documents": ["..."], "metadatas": [{}]}
    )
    kb = _make_kb(client)

    with patch("knowledge.get_knowledge_base", new_callable=AsyncMock) as mock_kb:
        mock_kb.return_value = kb
        writer = DecisionLogWriter()
        await writer.write(approval)

    collection.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_propagates_kb_failure_as_runtime_error() -> None:
    """write() should raise RuntimeError when the KB operation fails."""
    approval = _make_approval()
    client = AsyncMock()
    client.get_or_create_collection = AsyncMock(side_effect=Exception("ChromaDB down"))
    kb = _make_kb(client)

    with patch("knowledge.get_knowledge_base", new_callable=AsyncMock) as mock_kb:
        mock_kb.return_value = kb
        writer = DecisionLogWriter()
        with pytest.raises(RuntimeError):
            await writer.write(approval)


# ---------------------------------------------------------------------------
# DecisionLogReader.search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_results() -> None:
    client, collection = _make_chromadb_client(collection_exists=True)
    kb = _make_kb(client)

    with patch("knowledge.get_knowledge_base", new_callable=AsyncMock) as mock_kb:
        mock_kb.return_value = kb
        reader = DecisionLogReader()
        results = await reader.search(company_id=uuid.uuid4(), query="hire engineer")

    assert len(results) == 1
    assert "text" in results[0]
    assert "distance" in results[0]
    collection.query.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_returns_empty_when_collection_missing() -> None:
    client, _ = _make_chromadb_client(collection_exists=False)
    kb = _make_kb(client)

    with patch("knowledge.get_knowledge_base", new_callable=AsyncMock) as mock_kb:
        mock_kb.return_value = kb
        reader = DecisionLogReader()
        results = await reader.search(company_id=uuid.uuid4(), query="anything")

    assert results == []


# ---------------------------------------------------------------------------
# DecisionLogReader.list_decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_decisions_returns_all() -> None:
    client, collection = _make_chromadb_client(collection_exists=True)
    collection.get = AsyncMock(
        return_value={
            "ids": ["decision:a", "decision:b"],
            "documents": ["Type: hire\nDecision: approved", "Type: strategy\nDecision: rejected"],
            "metadatas": [
                {"approval_type": "hire", "decision": "approved", "decided_at": "2026-05-01T00:00:00"},
                {"approval_type": "strategy", "decision": "rejected", "decided_at": "2026-05-02T00:00:00"},
            ],
        }
    )
    kb = _make_kb(client)

    with patch("knowledge.get_knowledge_base", new_callable=AsyncMock) as mock_kb:
        mock_kb.return_value = kb
        reader = DecisionLogReader()
        results = await reader.list_decisions(company_id=uuid.uuid4())

    assert len(results) == 2
    # Newest first — strategy (May 2) should come first
    assert results[0]["approval_type"] == "strategy"


@pytest.mark.asyncio
async def test_list_decisions_filters_by_type() -> None:
    client, collection = _make_chromadb_client(collection_exists=True)
    collection.get = AsyncMock(
        return_value={
            "ids": ["decision:a", "decision:b"],
            "documents": ["doc a", "doc b"],
            "metadatas": [
                {"approval_type": "hire", "decision": "approved", "decided_at": "2026-05-01T00:00:00"},
                {"approval_type": "strategy", "decision": "rejected", "decided_at": "2026-05-02T00:00:00"},
            ],
        }
    )
    kb = _make_kb(client)

    with patch("knowledge.get_knowledge_base", new_callable=AsyncMock) as mock_kb:
        mock_kb.return_value = kb
        reader = DecisionLogReader()
        results = await reader.list_decisions(company_id=uuid.uuid4(), approval_type="hire")

    assert len(results) == 1
    assert results[0]["approval_type"] == "hire"


@pytest.mark.asyncio
async def test_list_decisions_returns_empty_when_collection_missing() -> None:
    client, _ = _make_chromadb_client(collection_exists=False)
    kb = _make_kb(client)

    with patch("knowledge.get_knowledge_base", new_callable=AsyncMock) as mock_kb:
        mock_kb.return_value = kb
        reader = DecisionLogReader()
        results = await reader.list_decisions(company_id=uuid.uuid4())

    assert results == []


# ---------------------------------------------------------------------------
# ApprovalService.log_decision_to_kb
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_decision_to_kb_calls_writer() -> None:
    """log_decision_to_kb() should call DecisionLogWriter.write()."""
    approval = _make_approval()
    svc = ApprovalService()

    with patch("llc.services.approval.DecisionLogWriter") as MockWriter:
        instance = AsyncMock()
        MockWriter.return_value = instance
        await svc.log_decision_to_kb(approval)

    instance.write.assert_awaited_once_with(approval)


@pytest.mark.asyncio
async def test_log_decision_to_kb_swallows_exceptions() -> None:
    """log_decision_to_kb() should not raise even when KB write fails."""
    approval = _make_approval()
    svc = ApprovalService()

    with patch("llc.services.approval.DecisionLogWriter") as MockWriter:
        instance = AsyncMock()
        instance.write.side_effect = RuntimeError("KB down")
        MockWriter.return_value = instance
        # Must not raise
        await svc.log_decision_to_kb(approval)
