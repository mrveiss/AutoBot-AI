# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for semantic duplicate guard on individual fact writes — Issue #3788.

Verifies that store_fact() skips near-duplicate content above the configured
threshold, allows content below threshold, and handles edge cases correctly.

Heavy dependencies (llama_index, chromadb, aioredis, redis) are stubbed via
sys.modules patching so the test suite can run without the full backend stack.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.facts import FactsMixin
from tests.helpers.fake_kb import FactsFakeKB

# ---------------------------------------------------------------------------
# Stub out heavy dependencies before importing knowledge.facts
# ---------------------------------------------------------------------------

_llama_core = types.ModuleType("llama_index.core")
_llama_core.Document = MagicMock
_llama_core.Settings = MagicMock()
_llama_index = types.ModuleType("llama_index")

sys.modules.setdefault("llama_index", _llama_index)
sys.modules.setdefault("llama_index.core", _llama_core)
sys.modules.setdefault("llama_index.vector_stores", types.ModuleType("llama_index.vector_stores"))
sys.modules.setdefault("llama_index.vector_stores.chroma", types.ModuleType("llama_index.vector_stores.chroma"))
sys.modules.setdefault("chromadb", types.ModuleType("chromadb"))
sys.modules.setdefault("redis", types.ModuleType("redis"))
sys.modules.setdefault("aioredis", types.ModuleType("aioredis"))

# knowledge.utils is imported lazily inside _vectorize_fact_in_chromadb
_knowledge_utils = types.ModuleType("knowledge.utils")
_knowledge_utils.sanitize_metadata_for_chromadb = lambda m: m
sys.modules.setdefault("knowledge.utils", _knowledge_utils)

# services.content_fingerprint is imported lazily inside _prepare_fact_metadata
_svc_fp = types.ModuleType("services.content_fingerprint")
_svc_fp.compute_fingerprint = lambda c: "fp-test"
sys.modules.setdefault("services.content_fingerprint", _svc_fp)

# services.npu_client is imported lazily inside _get_npu_client_cached
_svc_npu = types.ModuleType("services.npu_client")
_svc_npu.get_npu_client = MagicMock()
sys.modules.setdefault("services.npu_client", _svc_npu)

import knowledge.facts as facts_module  # noqa: E402 — must follow sys.modules patches

_THRESHOLD = 0.92


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chroma_result(distance: float, fact_id: str = "existing-001") -> dict:
    """Build a minimal ChromaDB query result dict with one hit."""
    return {
        "ids": [[fact_id]],
        "distances": [[distance]],
        "metadatas": [[{"fact_id": fact_id}]],
    }


def _empty_chroma_result() -> dict:
    return {"ids": [[]], "distances": [[]], "metadatas": [[]]}


# ---------------------------------------------------------------------------
# Tests: _find_duplicate()
# ---------------------------------------------------------------------------


class TestFindDuplicate:
    """Unit tests for FactsMixin._find_duplicate (#3788)."""

    @pytest.mark.asyncio
    async def test_above_threshold_returns_metadata(self):
        """Distance giving similarity >= threshold returns existing metadata."""
        # similarity = 1 - 0.10/2 = 0.95 >= 0.92
        chroma_collection = MagicMock()
        chroma_collection.query = MagicMock(return_value=_chroma_result(distance=0.10, fact_id="dup-42"))
        vector_store = MagicMock()
        vector_store._collection = chroma_collection
        kb = FactsFakeKB(vector_store=vector_store)

        with (
            patch.object(
                facts_module,
                "_generate_embedding_with_npu_fallback",
                new=AsyncMock(return_value=[0.1] * 768),
            ),
            patch("knowledge.facts.asyncio.to_thread", side_effect=lambda f, *a, **k: f(*a, **k)),
        ):
            result = await kb._find_duplicate("duplicate content", threshold=_THRESHOLD)

        assert result is not None
        assert result.get("fact_id") == "dup-42"

    @pytest.mark.asyncio
    async def test_below_threshold_returns_none(self):
        """Distance giving similarity < threshold returns None."""
        # similarity = 1 - 0.30/2 = 0.85 < 0.92
        chroma_collection = MagicMock()
        chroma_collection.query = MagicMock(return_value=_chroma_result(distance=0.30, fact_id="not-dup"))
        vector_store = MagicMock()
        vector_store._collection = chroma_collection
        kb = FactsFakeKB(vector_store=vector_store)

        with (
            patch.object(
                facts_module,
                "_generate_embedding_with_npu_fallback",
                new=AsyncMock(return_value=[0.1] * 768),
            ),
            patch("knowledge.facts.asyncio.to_thread", side_effect=lambda f, *a, **k: f(*a, **k)),
        ):
            result = await kb._find_duplicate("distinct content", threshold=_THRESHOLD)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_vector_store_returns_none(self):
        """If vector_store is None the guard is skipped and returns None."""
        kb = FactsFakeKB(vector_store=None)
        result = await kb._find_duplicate("some content", threshold=_THRESHOLD)
        assert result is None

    @pytest.mark.asyncio
    async def test_chroma_error_returns_none(self):
        """ChromaDB query failure is swallowed and returns None (graceful degradation)."""
        chroma_collection = MagicMock()
        chroma_collection.query = MagicMock(side_effect=RuntimeError("chroma down"))
        vector_store = MagicMock()
        vector_store._collection = chroma_collection
        kb = FactsFakeKB(vector_store=vector_store)

        with (
            patch.object(
                facts_module,
                "_generate_embedding_with_npu_fallback",
                new=AsyncMock(return_value=[0.1] * 768),
            ),
            patch("knowledge.facts.asyncio.to_thread", side_effect=lambda f, *a, **k: f(*a, **k)),
        ):
            result = await kb._find_duplicate("any content", threshold=_THRESHOLD)

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_results_returns_none(self):
        """Empty ChromaDB result set produces no false positive."""
        chroma_collection = MagicMock()
        chroma_collection.query = MagicMock(return_value=_empty_chroma_result())
        vector_store = MagicMock()
        vector_store._collection = chroma_collection
        kb = FactsFakeKB(vector_store=vector_store)

        with (
            patch.object(
                facts_module,
                "_generate_embedding_with_npu_fallback",
                new=AsyncMock(return_value=[0.1] * 768),
            ),
            patch("knowledge.facts.asyncio.to_thread", side_effect=lambda f, *a, **k: f(*a, **k)),
        ):
            result = await kb._find_duplicate("brand new content", threshold=_THRESHOLD)

        assert result is None


# ---------------------------------------------------------------------------
# Tests: store_fact() integration
# ---------------------------------------------------------------------------


class TestStoreFact:
    """Integration tests for store_fact() duplicate guard (#3788)."""

    def _make_config_mock(self):
        cfg = MagicMock()
        cfg.cache.l2.kb_dedup_threshold = _THRESHOLD
        return cfg

    def _make_kb(self, chroma_distance: float, fact_id: str = "existing-001"):
        chroma_collection = MagicMock()
        chroma_collection.query = MagicMock(return_value=_chroma_result(distance=chroma_distance, fact_id=fact_id))
        vector_store = MagicMock()
        vector_store._collection = chroma_collection
        kb = FactsFakeKB(vector_store=vector_store)
        kb.redis_client.get = MagicMock(return_value=None)
        kb.redis_client.exists = MagicMock(return_value=False)
        kb.redis_client.hset = MagicMock()
        kb.redis_client.set = MagicMock()
        kb.redis_client.sadd = MagicMock()
        kb._aioredis_client.get = AsyncMock(return_value=None)
        return kb

    @pytest.mark.asyncio
    async def test_near_duplicate_above_threshold_is_skipped(self):
        """store_fact with near-duplicate content returns existing ID without writing."""
        kb = self._make_kb(chroma_distance=0.10)  # sim=0.95 > 0.92

        with (
            patch.object(
                facts_module,
                "_generate_embedding_with_npu_fallback",
                new=AsyncMock(return_value=[0.1] * 768),
            ),
            patch(
                "knowledge.facts.asyncio.to_thread",
                side_effect=lambda f, *a, **k: f(*a, **k),
            ),
            patch("autobot_shared.ssot_config.config", self._make_config_mock()),
        ):
            result = await kb.store_fact("This is a near-duplicate fact", metadata={"category": "test"})

        assert result["status"] == "duplicate"
        assert result["fact_id"] == "existing-001"

    @pytest.mark.asyncio
    async def test_distinct_content_below_threshold_writes_normally(self):
        """store_fact with distinct content (similarity < threshold) proceeds to write."""
        kb = self._make_kb(chroma_distance=0.30)  # sim=0.85 < 0.92

        with (
            patch.object(
                facts_module,
                "_generate_embedding_with_npu_fallback",
                new=AsyncMock(return_value=[0.1] * 768),
            ),
            patch(
                "knowledge.facts.asyncio.to_thread",
                side_effect=lambda f, *a, **k: f(*a, **k),
            ),
            patch("autobot_shared.ssot_config.config", self._make_config_mock()),
            patch.object(FactsMixin, "_vectorize_fact_in_chromadb", new=AsyncMock()),
            patch.object(FactsMixin, "_store_fact_in_redis", new=AsyncMock()),
        ):
            result = await kb.store_fact("Completely different content", metadata={"category": "test"})

        assert result["status"] == "success"
        assert "fact_id" in result

    @pytest.mark.asyncio
    async def test_exact_duplicate_hash_blocked_before_semantic(self):
        """Exact hash duplicate is caught before the semantic check fires."""
        # Semantic check would NOT trigger (high distance)
        kb = self._make_kb(chroma_distance=1.0)

        exact_content = "Exact same content"

        def fake_redis_get(key):
            if b"content_hash:" in key if isinstance(key, bytes) else "content_hash:" in key:
                return b"hash-matched-id"
            return None

        kb.redis_client.get = MagicMock(side_effect=fake_redis_get)

        with (
            patch.object(
                facts_module,
                "_generate_embedding_with_npu_fallback",
                new=AsyncMock(return_value=[0.1] * 768),
            ),
            patch(
                "knowledge.facts.asyncio.to_thread",
                side_effect=lambda f, *a, **k: f(*a, **k),
            ),
            patch("autobot_shared.ssot_config.config", self._make_config_mock()),
        ):
            result = await kb.store_fact(exact_content, metadata={})

        assert result["status"] == "duplicate"
        assert result["fact_id"] == "hash-matched-id"

    @pytest.mark.asyncio
    async def test_empty_kb_no_false_positive(self):
        """Empty ChromaDB (no prior facts) does not produce a false duplicate."""
        chroma_collection = MagicMock()
        chroma_collection.query = MagicMock(return_value=_empty_chroma_result())
        vector_store = MagicMock()
        vector_store._collection = chroma_collection
        kb = FactsFakeKB(vector_store=vector_store)
        kb.redis_client.get = MagicMock(return_value=None)
        kb.redis_client.hset = MagicMock()
        kb.redis_client.set = MagicMock()
        kb.redis_client.sadd = MagicMock()
        kb._aioredis_client.get = AsyncMock(return_value=None)

        with (
            patch.object(
                facts_module,
                "_generate_embedding_with_npu_fallback",
                new=AsyncMock(return_value=[0.1] * 768),
            ),
            patch(
                "knowledge.facts.asyncio.to_thread",
                side_effect=lambda f, *a, **k: f(*a, **k),
            ),
            patch("autobot_shared.ssot_config.config", self._make_config_mock()),
            patch.object(FactsMixin, "_vectorize_fact_in_chromadb", new=AsyncMock()),
            patch.object(FactsMixin, "_store_fact_in_redis", new=AsyncMock()),
        ):
            result = await kb.store_fact("Brand new fact", metadata={})

        assert result["status"] == "success"
