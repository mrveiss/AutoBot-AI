# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Restoring a fact from backup redacts credentials before the ChromaDB
embedding upsert, not just the durable/Redis writes store_fact already
covers (#13708 round 4).

_store_restored_fact calls store_fact (which redacts via sanitize_fact_content),
then separately calls _restore_fact_embedding with its OWN original content
copy for the vector_store.upsert -- a backup taken before this fix, or from
any path that never redacted, carried that raw copy straight into ChromaDB.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.bulk import BulkOperationsMixin
from knowledge.facts import FactsMixin

_SECRET = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"


class _RestoreFakeKB(FactsMixin, BulkOperationsMixin):
    # FactsMixin first: matches KnowledgeBase's real MRO (knowledge/_composed.py
    # lists FactsMixin before BulkOperationsMixin), so store_fact resolves to
    # FactsMixin's real implementation, not BulkOperationsMixin's
    # NotImplementedError stub (#13708 review round 4 caught this the same way
    # for KnowledgeBase itself -- DocumentsMixin's same-named stub/impl).
    embedding_model_name = "test-embed"

    def __init__(self):
        self.redis_client = MagicMock()
        self.vector_store = MagicMock()
        self._aioredis_client = AsyncMock()

    def ensure_initialized(self):
        pass

    async def _increment_stat(self, *_):
        pass

    def _schedule_bm25_refresh(self):
        pass

    async def _check_for_duplicates(self, content, metadata, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_restore_redacts_the_embedding_upsert():
    kb = _RestoreFakeKB()
    captured = {}

    def _upsert(*, ids, embeddings, metadatas, documents):
        captured["documents"] = documents
        captured["metadatas"] = metadatas

    kb.vector_store.upsert = MagicMock(side_effect=_upsert)  # sync: real chromadb client, dispatched via to_thread

    fact_data = {"embedding": [0.1, 0.2, 0.3]}
    content = f"your API key is {_SECRET}"

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        patch("knowledge.bulk.asyncio.to_thread", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))),
    ):
        result = await kb._store_restored_fact(fact_data, content, {}, "fact-1", restore_embeddings=True)

    assert result["action"] == "restored"
    assert result["embedding"] is True
    assert _SECRET not in captured["documents"][0]
    assert _SECRET not in captured["metadatas"][0]["content"]
    assert "your API key is" in captured["documents"][0]


@pytest.mark.asyncio
async def test_restore_a_safe_body_is_unchanged():
    """Negative control: the redaction pass must not mangle ordinary content."""
    kb = _RestoreFakeKB()
    captured = {}

    def _upsert(*, ids, embeddings, metadatas, documents):
        captured["documents"] = documents

    kb.vector_store.upsert = MagicMock(side_effect=_upsert)

    fact_data = {"embedding": [0.1, 0.2, 0.3]}
    content = "Redis listens on port 6379."

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        patch("knowledge.bulk.asyncio.to_thread", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))),
    ):
        await kb._store_restored_fact(fact_data, content, {}, "fact-2", restore_embeddings=True)

    assert captured["documents"][0] == "Redis listens on port 6379."
