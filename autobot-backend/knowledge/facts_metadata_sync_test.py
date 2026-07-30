# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for Issue #12623 — ``update_fact`` metadata-only updates must
sync ChromaDB, not just Redis.

Before this fix, ``update_fact(fact_id, metadata=...)`` (no ``content``
argument) only re-synced the vector store when *content* also changed
(``_revectorize_fact``). A pure metadata change — e.g. the #12623 promotion
gate flipping ``collection`` from ``research`` to the general value — was
written to Redis but silently never reached ChromaDB, so any
ChromaDB-filtered search (like the #12622 chat-RAG quarantine filter) would
still see the stale metadata and the fact would remain invisible even after
"promotion".
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.facts import FactsMixin


class _KB(FactsMixin):
    """Minimal FactsMixin host with the collaborators update_fact touches."""

    def __init__(self, existing_metadata: dict):
        self.ensure_initialized = MagicMock()
        self.redis_client = MagicMock()
        self.redis_client.exists.return_value = True
        self.redis_client.hgetall.return_value = {
            b"content": b"unchanged content",
            b"metadata": json.dumps(existing_metadata).encode("utf-8"),
            b"timestamp": b"2026-01-01T00:00:00+00:00",
        }
        self.vector_store = MagicMock()
        self.vector_store._collection = MagicMock()


@pytest.mark.asyncio
async def test_metadata_only_update_syncs_chromadb():
    """A metadata-only update() call must push the change to ChromaDB too."""
    kb = _KB({"collection": "research", "fact_id": "fact-1"})

    result = await kb.update_fact("fact-1", metadata={"collection": "general"})

    assert result["status"] == "success"
    kb.vector_store._collection.update.assert_called_once()
    call_kwargs = kb.vector_store._collection.update.call_args.kwargs
    assert call_kwargs["ids"] == ["fact-1"]
    assert call_kwargs["metadatas"][0]["collection"] == "general"


@pytest.mark.asyncio
async def test_content_update_still_uses_revectorize_not_metadata_sync():
    """A content change re-embeds via _revectorize_fact — the metadata-only
    path must NOT also fire (would be a redundant/duplicate vector-store write)."""
    kb = _KB({"collection": "research", "fact_id": "fact-1"})
    kb._revectorize_fact = AsyncMock()
    kb._sync_fact_metadata_in_chromadb = AsyncMock()

    await kb.update_fact("fact-1", content="new content", metadata={"collection": "general"})

    kb._revectorize_fact.assert_awaited_once()
    kb._sync_fact_metadata_in_chromadb.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_vector_store_skips_sync_without_error():
    """A KB with no vector store configured must not raise on metadata update."""
    kb = _KB({"collection": "research"})
    kb.vector_store = None

    result = await kb.update_fact("fact-1", metadata={"collection": "general"})

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_chromadb_sync_failure_does_not_fail_the_update():
    """A ChromaDB error during the metadata sync must not surface as an update failure."""
    kb = _KB({"collection": "research"})
    kb.vector_store._collection.update.side_effect = RuntimeError("chroma unreachable")

    result = await kb.update_fact("fact-1", metadata={"collection": "general"})

    assert result["status"] == "success"
