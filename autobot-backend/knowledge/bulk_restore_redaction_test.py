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

    def ensure_initialized(self):
        pass

    async def _increment_stat(self, *_):
        pass

    def _schedule_bm25_refresh(self):
        pass

    async def _check_for_duplicates(self, content, metadata, **_kwargs):
        return None


async def _restore(content: str, fact_id: str) -> tuple[dict, dict]:
    """Run the restore, the persisted fact being what store_fact handed to the vectorizer."""
    kb = _RestoreFakeKB()
    captured: dict = {}

    async def _vectorize(_fid, stored, metadata, **_kw):
        captured["persisted"] = {"content": stored, "metadata": metadata}

    async def _write(_space, _fid, _vec, stored, metadata, _ctx):
        captured.update(document=stored, metadata=metadata)
        return True

    kb._get_fact_for_vectorization = AsyncMock(side_effect=lambda _fid: captured["persisted"])
    kb._write_vector = AsyncMock(side_effect=_write)
    kb._mark_vectorization_succeeded = AsyncMock()
    space = MagicMock(model="test-embed", write_buffer=None)
    space.vector_store._collection.get.return_value = {"ids": []}
    fact_data = {"embedding": [0.1, 0.2, 0.3], "embedding_model": "test-embed"}
    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock(side_effect=_vectorize)),
        patch("knowledge.backup_embeddings.current_space", new=AsyncMock(return_value=space)),
    ):
        result = await kb._store_restored_fact(fact_data, content, {}, fact_id, restore_embeddings=True)
    return result, captured


@pytest.mark.asyncio
async def test_restore_redacts_what_reaches_the_vector_store():
    result, captured = await _restore(f"your API key is {_SECRET}", "fact-1")
    assert result["action"] == "restored"
    assert result["embedding"] is True
    assert _SECRET not in captured["document"]
    assert _SECRET not in str(captured["metadata"])
    assert "your API key is" in captured["document"]


@pytest.mark.asyncio
async def test_restore_a_safe_body_is_unchanged():
    """Negative control: the redaction pass must not mangle ordinary content."""
    _, captured = await _restore("Redis listens on port 6379.", "fact-2")
    assert captured["document"] == "Redis listens on port 6379."
