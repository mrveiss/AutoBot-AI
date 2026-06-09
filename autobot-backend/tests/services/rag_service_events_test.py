# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for RAGService retrieval feedback event emission (#1516)."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from tests.fixtures import make_async_redis

# =============================================================================
# _emit_retrieval_feedback Tests
# =============================================================================


class TestEmitRetrievalFeedback:
    """Tests for RAGService._emit_retrieval_feedback()."""

    def _make_service(self):
        """Create a minimally-initialised RAGService without touching Redis or ChromaDB."""
        from services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        svc._initialized = True
        return svc

    @pytest.mark.asyncio
    async def test_calls_publish_live_event(self):
        """_emit_retrieval_feedback calls publish_live_event exactly once."""
        with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
            svc = self._make_service()
            await svc._emit_retrieval_feedback(
                query="test query",
                retrieved_ids=["c1", "c2"],
                ranked_ids=["c1", "c2"],
            )
        mock_pub.assert_called_once()

    @pytest.mark.asyncio
    async def test_channel_is_global(self):
        """Event is published to the 'global' channel."""
        with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
            svc = self._make_service()
            await svc._emit_retrieval_feedback(
                query="q",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )
        channel = mock_pub.call_args[0][0]
        assert channel == "global"

    @pytest.mark.asyncio
    async def test_event_type_is_rag_retrieval(self):
        """Event type is 'rag_retrieval'."""
        with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
            svc = self._make_service()
            await svc._emit_retrieval_feedback(
                query="q",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )
        event_type = mock_pub.call_args[0][1]
        assert event_type == "rag_retrieval"

    @pytest.mark.asyncio
    async def test_payload_contains_query_text(self):
        """Payload includes query_text field."""
        with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
            svc = self._make_service()
            await svc._emit_retrieval_feedback(
                query="what is redis",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )
        payload = mock_pub.call_args[0][2]
        assert payload["query_text"] == "what is redis"

    @pytest.mark.asyncio
    async def test_payload_contains_retrieved_chunk_ids(self):
        """Payload includes retrieved_chunk_ids field."""
        with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
            svc = self._make_service()
            await svc._emit_retrieval_feedback(
                query="q",
                retrieved_ids=["a", "b", "c"],
                ranked_ids=["a"],
            )
        payload = mock_pub.call_args[0][2]
        assert payload["retrieved_chunk_ids"] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_payload_contains_final_ranked_ids(self):
        """Payload includes final_ranked_ids field."""
        with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
            svc = self._make_service()
            await svc._emit_retrieval_feedback(
                query="q",
                retrieved_ids=["a", "b"],
                ranked_ids=["b", "a"],
            )
        payload = mock_pub.call_args[0][2]
        assert payload["final_ranked_ids"] == ["b", "a"]

    @pytest.mark.asyncio
    async def test_payload_contains_timestamp(self):
        """Payload includes a numeric timestamp."""
        with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
            svc = self._make_service()
            await svc._emit_retrieval_feedback(
                query="q",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )
        payload = mock_pub.call_args[0][2]
        assert "timestamp" in payload
        assert isinstance(payload["timestamp"], float)

    @pytest.mark.asyncio
    async def test_publish_error_does_not_propagate(self):
        """If publish_live_event raises, _emit_retrieval_feedback does not re-raise."""
        with patch(
            "services.rag_service.publish_live_event",
            new_callable=AsyncMock,
            side_effect=RuntimeError("ws down"),
        ):
            svc = self._make_service()
            # Should complete without raising
            await svc._emit_retrieval_feedback(
                query="q",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )


# =============================================================================
# _store_feedback_in_stream Tests
# =============================================================================


class TestStoreFeedbackInStream:
    """Tests for RAGService._store_feedback_in_stream()."""

    _THIRTY_DAYS_SECONDS = 30 * 24 * 3600

    def _make_service(self):
        from services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        svc._initialized = True
        return svc

    def _make_redis_mock(self, xadd_side_effect=None):
        # Migrated to canonical ``make_async_redis()`` (#7280 round 8).
        # ``side_effect`` requires a post-set since canonical's ``**extra_methods``
        # only configures ``return_value``.
        mock_redis = make_async_redis(xadd=b"1234-0")
        if xadd_side_effect is not None:
            mock_redis.xadd = AsyncMock(return_value=b"1234-0", side_effect=xadd_side_effect)
        return mock_redis

    @pytest.mark.asyncio
    async def test_xadd_called_with_feedback_stream_key(self):
        """Redis xadd is called with a key matching rag:feedback:{date}."""
        mock_redis = self._make_redis_mock()

        with patch(
            "services.rag_service.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            svc = self._make_service()
            await svc._store_feedback_in_stream(
                query="test",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )

        assert mock_redis.xadd.called
        key_used = mock_redis.xadd.call_args[0][0]
        assert key_used.startswith("rag:feedback:")

    @pytest.mark.asyncio
    async def test_stream_entry_contains_query(self):
        """Stream entry fields include query_text."""
        mock_redis = self._make_redis_mock()

        with patch(
            "services.rag_service.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            svc = self._make_service()
            await svc._store_feedback_in_stream(
                query="what is redis",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )

        entry = mock_redis.xadd.call_args[0][1]
        assert "query_text" in entry
        assert entry["query_text"] == "what is redis"

    @pytest.mark.asyncio
    async def test_stream_entry_contains_ids_as_json(self):
        """Stream entry includes retrieved and ranked IDs serialised as JSON."""
        mock_redis = self._make_redis_mock()

        with patch(
            "services.rag_service.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            svc = self._make_service()
            await svc._store_feedback_in_stream(
                query="q",
                retrieved_ids=["a", "b"],
                ranked_ids=["b"],
            )

        entry = mock_redis.xadd.call_args[0][1]
        assert json.loads(entry["retrieved_chunk_ids"]) == ["a", "b"]
        assert json.loads(entry["final_ranked_ids"]) == ["b"]

    @pytest.mark.asyncio
    async def test_expire_set_to_thirty_days(self):
        """Stream key TTL is set to 30 days (2592000 seconds). Fix: #2102."""
        mock_redis = self._make_redis_mock()

        with patch(
            "services.rag_service.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            svc = self._make_service()
            await svc._store_feedback_in_stream(
                query="q",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )

        assert mock_redis.expire.called
        ttl_arg = mock_redis.expire.call_args[0][1]
        assert ttl_arg == self._THIRTY_DAYS_SECONDS

    @pytest.mark.asyncio
    async def test_redis_unavailable_does_not_raise(self):
        """When Redis client is None, method completes without raising."""
        with patch(
            "services.rag_service.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=None,
        ):
            svc = self._make_service()
            await svc._store_feedback_in_stream(
                query="q",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )

    @pytest.mark.asyncio
    async def test_redis_error_does_not_propagate(self):
        """Redis exceptions are swallowed; method does not re-raise."""
        mock_redis = self._make_redis_mock(xadd_side_effect=ConnectionError("redis gone"))

        with patch(
            "services.rag_service.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            svc = self._make_service()
            await svc._store_feedback_in_stream(
                query="q",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )


# =============================================================================
# Complexity field integration tests (Issue #2024)
# =============================================================================


class TestComplexityInEmitRetrievalFeedback:
    """Tests that _emit_retrieval_feedback passes complexity in the payload. Issue #2024."""

    def _make_service(self):
        from services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        svc._initialized = True
        return svc

    @pytest.mark.asyncio
    async def test_payload_contains_complexity_field(self):
        """Payload includes a complexity field when explicitly provided."""
        with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
            svc = self._make_service()
            await svc._emit_retrieval_feedback(
                query="what is redis",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
                complexity="simple",
            )
        payload = mock_pub.call_args[0][2]
        assert "complexity" in payload

    @pytest.mark.asyncio
    async def test_payload_complexity_matches_classifier_output(self):
        """Payload complexity value matches what QueryClassifier returns for the query."""
        from knowledge.search_components.query_classifier import (
            QueryClassifier,
            QueryComplexity,
        )

        classifier = QueryClassifier()
        query = "compare redis and memcached advantages and disadvantages"
        expected_complexity = classifier.classify(query).value

        with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
            svc = self._make_service()
            await svc._emit_retrieval_feedback(
                query=query,
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
                complexity=expected_complexity,
            )
        payload = mock_pub.call_args[0][2]
        assert payload["complexity"] == expected_complexity
        assert payload["complexity"] in {c.value for c in QueryComplexity}

    @pytest.mark.asyncio
    async def test_default_complexity_is_simple(self):
        """When no complexity is passed, the default is 'simple'."""
        with patch("services.rag_service.publish_live_event", new_callable=AsyncMock) as mock_pub:
            svc = self._make_service()
            await svc._emit_retrieval_feedback(
                query="q",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )
        payload = mock_pub.call_args[0][2]
        assert payload["complexity"] == "simple"


class TestComplexityInStoreFeedbackInStream:
    """Tests that _store_feedback_in_stream persists complexity in the stream. Issue #2024."""

    def _make_service(self):
        from services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        svc._initialized = True
        return svc

    def _make_redis_mock(self):
        # Migrated to canonical ``make_async_redis()`` (#7280 round 8).
        return make_async_redis(xadd=b"1234-0")

    @pytest.mark.asyncio
    async def test_stream_entry_contains_complexity_field(self):
        """Redis stream entry includes a complexity field."""
        mock_redis = self._make_redis_mock()

        with patch(
            "services.rag_service.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            svc = self._make_service()
            await svc._store_feedback_in_stream(
                query="q",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
                complexity="moderate",
            )

        entry = mock_redis.xadd.call_args[0][1]
        assert "complexity" in entry

    @pytest.mark.asyncio
    async def test_stream_entry_complexity_matches_passed_value(self):
        """Stream entry complexity equals the value forwarded from the classifier."""
        mock_redis = self._make_redis_mock()

        with patch(
            "services.rag_service.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            svc = self._make_service()
            await svc._store_feedback_in_stream(
                query="trace the chain of events that caused the outage",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
                complexity="multi_hop",
            )

        entry = mock_redis.xadd.call_args[0][1]
        assert entry["complexity"] == "multi_hop"

    @pytest.mark.asyncio
    async def test_default_complexity_persisted_as_simple(self):
        """When no complexity kwarg is provided, stream entry defaults to 'simple'."""
        mock_redis = self._make_redis_mock()

        with patch(
            "services.rag_service.get_async_redis_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            svc = self._make_service()
            await svc._store_feedback_in_stream(
                query="q",
                retrieved_ids=["c1"],
                ranked_ids=["c1"],
            )

        entry = mock_redis.xadd.call_args[0][1]
        assert entry["complexity"] == "simple"


# =============================================================================
# retrieved_ids vs ranked_ids separation tests (Issue #2035)
# =============================================================================


class TestRetrievedVsRankedIdsSeparation:
    """Verify that advanced_search emits distinct retrieved_ids and ranked_ids.

    Issue #2035: feedback events were passing ranked_ids=retrieved_ids (same list).
    After reranking, retrieved_ids must reflect hybrid_score order (pre-rerank)
    and ranked_ids must reflect rerank_score order (post-rerank).
    """

    def _make_service(self):
        """Build a RAGService instance with a stub config and bypassed init."""
        from services.rag_config import RAGConfig
        from services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        svc._initialized = True
        cfg = RAGConfig()
        cfg.enable_advanced_rag = True
        svc.config = cfg
        return svc

    def _make_result(self, chunk_id: str, hybrid_score: float, rerank_score: float):
        """Construct a SearchResult with controlled scores."""
        from advanced_rag_optimizer import SearchResult

        return SearchResult(
            content="content",
            metadata={"chunk_id": chunk_id},
            semantic_score=hybrid_score,
            keyword_score=0.0,
            hybrid_score=hybrid_score,
            relevance_rank=1,
            source_path=chunk_id,
            rerank_score=rerank_score,
        )

    @pytest.mark.asyncio
    async def test_ranked_ids_follow_rerank_score_order(self):
        """ranked_ids are in rerank_score descending order (post-rerank)."""
        from advanced_rag_optimizer import RAGMetrics

        # Results arrive from the optimizer already sorted by rerank_score desc:
        # chunk_b rerank=0.9, chunk_a rerank=0.6, chunk_c rerank=0.3
        results = [
            self._make_result("chunk_b", hybrid_score=0.5, rerank_score=0.9),
            self._make_result("chunk_a", hybrid_score=0.8, rerank_score=0.6),
            self._make_result("chunk_c", hybrid_score=0.3, rerank_score=0.3),
        ]
        svc = self._make_service()

        with (
            patch(
                "services.rag_service.RAGService._check_cache_tiers",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "services.rag_service.RAGService.initialize",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "services.rag_service.RAGService._execute_and_cache_search",
                new_callable=AsyncMock,
                return_value=(results, RAGMetrics()),
            ),
            patch(
                "services.rag_service.RAGService._store_in_semantic_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._store_in_topic_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._emit_retrieval_feedback",
                new_callable=AsyncMock,
            ) as mock_emit,
            patch(
                "services.rag_service.RAGService._store_feedback_in_stream",
                new_callable=AsyncMock,
            ),
        ):
            await svc.advanced_search(query="test")

        _, kwargs = mock_emit.call_args
        assert kwargs["ranked_ids"] == ["chunk_b", "chunk_a", "chunk_c"]

    @pytest.mark.asyncio
    async def test_retrieved_ids_follow_hybrid_score_order(self):
        """retrieved_ids are in hybrid_score descending order (pre-rerank)."""
        from advanced_rag_optimizer import RAGMetrics

        # hybrid_score order: chunk_a=0.8, chunk_b=0.5, chunk_c=0.3
        # rerank_score order: chunk_b=0.9, chunk_a=0.6, chunk_c=0.3
        results = [
            self._make_result("chunk_b", hybrid_score=0.5, rerank_score=0.9),
            self._make_result("chunk_a", hybrid_score=0.8, rerank_score=0.6),
            self._make_result("chunk_c", hybrid_score=0.3, rerank_score=0.3),
        ]
        svc = self._make_service()

        with (
            patch(
                "services.rag_service.RAGService._check_cache_tiers",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "services.rag_service.RAGService.initialize",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "services.rag_service.RAGService._execute_and_cache_search",
                new_callable=AsyncMock,
                return_value=(results, RAGMetrics()),
            ),
            patch(
                "services.rag_service.RAGService._store_in_semantic_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._store_in_topic_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._emit_retrieval_feedback",
                new_callable=AsyncMock,
            ) as mock_emit,
            patch(
                "services.rag_service.RAGService._store_feedback_in_stream",
                new_callable=AsyncMock,
            ),
        ):
            await svc.advanced_search(query="test")

        _, kwargs = mock_emit.call_args
        assert kwargs["retrieved_ids"] == ["chunk_a", "chunk_b", "chunk_c"]

    @pytest.mark.asyncio
    async def test_retrieved_ids_differ_from_ranked_ids_when_reranking_changes_order(
        self,
    ):
        """When reranking reorders results, retrieved_ids != ranked_ids."""
        from advanced_rag_optimizer import RAGMetrics

        # Reranking promotes chunk_b above chunk_a despite lower hybrid_score
        results = [
            self._make_result("chunk_b", hybrid_score=0.5, rerank_score=0.9),
            self._make_result("chunk_a", hybrid_score=0.8, rerank_score=0.6),
        ]
        svc = self._make_service()

        with (
            patch(
                "services.rag_service.RAGService._check_cache_tiers",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "services.rag_service.RAGService.initialize",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "services.rag_service.RAGService._execute_and_cache_search",
                new_callable=AsyncMock,
                return_value=(results, RAGMetrics()),
            ),
            patch(
                "services.rag_service.RAGService._store_in_semantic_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._store_in_topic_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._emit_retrieval_feedback",
                new_callable=AsyncMock,
            ) as mock_emit,
            patch(
                "services.rag_service.RAGService._store_feedback_in_stream",
                new_callable=AsyncMock,
            ),
        ):
            await svc.advanced_search(query="test")

        _, kwargs = mock_emit.call_args
        assert kwargs["retrieved_ids"] != kwargs["ranked_ids"]
        assert kwargs["retrieved_ids"] == ["chunk_a", "chunk_b"]
        assert kwargs["ranked_ids"] == ["chunk_b", "chunk_a"]

    @pytest.mark.asyncio
    async def test_retrieved_and_ranked_ids_identical_when_order_unchanged(self):
        """When hybrid_score and rerank_score yield the same order, lists are equal."""
        from advanced_rag_optimizer import RAGMetrics

        # Both scores rank chunk_a first
        results = [
            self._make_result("chunk_a", hybrid_score=0.9, rerank_score=0.95),
            self._make_result("chunk_b", hybrid_score=0.5, rerank_score=0.4),
        ]
        svc = self._make_service()

        with (
            patch(
                "services.rag_service.RAGService._check_cache_tiers",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "services.rag_service.RAGService.initialize",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "services.rag_service.RAGService._execute_and_cache_search",
                new_callable=AsyncMock,
                return_value=(results, RAGMetrics()),
            ),
            patch(
                "services.rag_service.RAGService._store_in_semantic_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._store_in_topic_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._emit_retrieval_feedback",
                new_callable=AsyncMock,
            ) as mock_emit,
            patch(
                "services.rag_service.RAGService._store_feedback_in_stream",
                new_callable=AsyncMock,
            ),
        ):
            await svc.advanced_search(query="test")

        _, kwargs = mock_emit.call_args
        assert kwargs["retrieved_ids"] == kwargs["ranked_ids"] == ["chunk_a", "chunk_b"]

    @pytest.mark.asyncio
    async def test_stream_store_receives_same_separation(self):
        """_store_feedback_in_stream receives the same retrieved/ranked split."""
        from advanced_rag_optimizer import RAGMetrics

        results = [
            self._make_result("chunk_b", hybrid_score=0.5, rerank_score=0.9),
            self._make_result("chunk_a", hybrid_score=0.8, rerank_score=0.6),
        ]
        svc = self._make_service()

        with (
            patch(
                "services.rag_service.RAGService._check_cache_tiers",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "services.rag_service.RAGService.initialize",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "services.rag_service.RAGService._execute_and_cache_search",
                new_callable=AsyncMock,
                return_value=(results, RAGMetrics()),
            ),
            patch(
                "services.rag_service.RAGService._store_in_semantic_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._store_in_topic_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._emit_retrieval_feedback",
                new_callable=AsyncMock,
            ),
            patch(
                "services.rag_service.RAGService._store_feedback_in_stream",
                new_callable=AsyncMock,
            ) as mock_store,
        ):
            await svc.advanced_search(query="test")

        _, kwargs = mock_store.call_args
        assert kwargs["retrieved_ids"] == ["chunk_a", "chunk_b"]
        assert kwargs["ranked_ids"] == ["chunk_b", "chunk_a"]


# =============================================================================
# _filter_stale_chunks Tests (#4689)
# =============================================================================


class TestFilterStaleChunks:
    """Tests for RAGService._filter_stale_chunks() — provenance validation."""

    @pytest.fixture(autouse=True)
    def reset_hash_cache_memo(self):
        """Reset module-level TTL cache before each test to ensure isolation."""
        import services.rag_service as rag_mod

        rag_mod._hash_cache_memo = {}
        rag_mod._hash_cache_loaded_at = 0.0
        yield
        rag_mod._hash_cache_memo = {}
        rag_mod._hash_cache_loaded_at = 0.0

    def _make_service(self):
        from services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        svc._initialized = True
        return svc

    def _make_chunk(self, source_path: str):
        from advanced_rag_optimizer import SearchResult

        return SearchResult(
            content="text",
            metadata={"relative_path": source_path},
            semantic_score=0.9,
            keyword_score=0.0,
            hybrid_score=0.9,
            relevance_rank=1,
            source_path=source_path,
            chunk_index=0,
        )

    @pytest.mark.asyncio
    async def test_valid_chunk_passes_through(self, tmp_path):
        """Chunk whose source_path IS in the hash cache is kept."""
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text('{"docs/guide.md": "abc123"}', encoding="utf-8")

        svc = self._make_service()
        chunk = self._make_chunk("docs/guide.md")

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            result = await svc._filter_stale_chunks([chunk])

        assert result == [chunk]

    @pytest.mark.asyncio
    async def test_stale_chunk_is_filtered(self, tmp_path):
        """Chunk whose source_path is ABSENT from the hash cache is dropped."""
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text('{"docs/present.md": "abc123"}', encoding="utf-8")

        svc = self._make_service()
        stale = self._make_chunk("docs/removed.md")
        valid = self._make_chunk("docs/present.md")

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            result = await svc._filter_stale_chunks([stale, valid])

        assert result == [valid]

    @pytest.mark.asyncio
    async def test_warning_logged_for_stale_chunks(self, tmp_path):
        """A warning is emitted when stale chunks are dropped."""
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text('{"docs/present.md": "abc123"}', encoding="utf-8")

        svc = self._make_service()
        stale = self._make_chunk("docs/gone.md")

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            with patch("services.rag_service.logger") as mock_logger:
                await svc._filter_stale_chunks([stale])

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0]
        assert "stale" in call_args[0]

    @pytest.mark.asyncio
    async def test_cache_unavailable_returns_all_chunks(self, tmp_path):
        """If the hash cache module cannot be imported, all chunks are returned unchanged."""
        svc = self._make_service()
        chunk = self._make_chunk("docs/anything.md")

        with patch.dict("sys.modules", {"services.knowledge.doc_indexer": None}):
            result = await svc._filter_stale_chunks([chunk])

        assert result == [chunk]

    @pytest.mark.asyncio
    async def test_empty_cache_skips_filter(self, tmp_path):
        """An empty hash cache (indexer hasn't run) passes all chunks through."""
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text("{}", encoding="utf-8")

        svc = self._make_service()
        chunk = self._make_chunk("docs/anything.md")

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            result = await svc._filter_stale_chunks([chunk])

        assert result == [chunk]

    @pytest.mark.asyncio
    async def test_missing_cache_file_skips_filter(self, tmp_path):
        """If hash cache file does not exist, all chunks pass through."""
        cache_file = tmp_path / "nonexistent_hashes.json"

        svc = self._make_service()
        chunk = self._make_chunk("docs/anything.md")

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            result = await svc._filter_stale_chunks([chunk])

        assert result == [chunk]

    # ------------------------------------------------------------------
    # TTL memo-cache tests (Issue #4723)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_first_call_loads_from_disk(self, tmp_path):
        """First call triggers a disk read via asyncio.to_thread."""
        import services.rag_service as rag_mod

        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text('{"docs/guide.md": "abc"}', encoding="utf-8")

        svc = self._make_service()
        chunk = self._make_chunk("docs/guide.md")

        # Reset module-level state so we always start cold.
        rag_mod._hash_cache_loaded_at = 0.0
        rag_mod._hash_cache_memo = {}

        load_call_count = 0
        original_to_thread = asyncio.to_thread

        async def counting_to_thread(fn, *args, **kwargs):
            nonlocal load_call_count
            load_call_count += 1
            return await original_to_thread(fn, *args, **kwargs)

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            with patch("services.rag_service.asyncio.to_thread", side_effect=counting_to_thread):
                await svc._filter_stale_chunks([chunk])

        assert load_call_count == 1

    @pytest.mark.asyncio
    async def test_second_call_within_ttl_skips_disk(self, tmp_path):
        """Second call within TTL window uses the in-process memo — no disk read."""
        import services.rag_service as rag_mod

        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text('{"docs/guide.md": "abc"}', encoding="utf-8")

        svc = self._make_service()
        chunk = self._make_chunk("docs/guide.md")

        # Seed memo as if we already loaded recently.
        rag_mod._hash_cache_memo = {"docs/guide.md": "abc"}
        rag_mod._hash_cache_loaded_at = time.monotonic()  # just now — within TTL

        load_call_count = 0
        original_to_thread = asyncio.to_thread

        async def counting_to_thread(fn, *args, **kwargs):
            nonlocal load_call_count
            load_call_count += 1
            return await original_to_thread(fn, *args, **kwargs)

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            with patch("services.rag_service.asyncio.to_thread", side_effect=counting_to_thread):
                result = await svc._filter_stale_chunks([chunk])

        assert load_call_count == 0, "Should not re-read disk within TTL"
        assert result == [chunk]

    @pytest.mark.asyncio
    async def test_call_after_ttl_expiry_reloads(self, tmp_path):
        """A call made after the TTL expires triggers a fresh disk read."""
        import services.rag_service as rag_mod

        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text('{"docs/guide.md": "abc"}', encoding="utf-8")

        svc = self._make_service()
        chunk = self._make_chunk("docs/guide.md")

        # Simulate an expired memo: loaded_at is older than TTL.
        rag_mod._hash_cache_memo = {"docs/guide.md": "abc"}
        rag_mod._hash_cache_loaded_at = time.monotonic() - rag_mod._HASH_CACHE_TTL - 1.0

        load_call_count = 0
        original_to_thread = asyncio.to_thread

        async def counting_to_thread(fn, *args, **kwargs):
            nonlocal load_call_count
            load_call_count += 1
            return await original_to_thread(fn, *args, **kwargs)

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            with patch("services.rag_service.asyncio.to_thread", side_effect=counting_to_thread):
                result = await svc._filter_stale_chunks([chunk])

        assert load_call_count == 1, "Should reload disk after TTL expiry"
        assert result == [chunk]


# =============================================================================
# _fallback_basic_search stale-chunk filtering tests (#4721)
# =============================================================================


class TestFallbackBasicSearchFiltersStaleChunks:
    """Verify that _fallback_basic_search() passes results through _filter_stale_chunks().

    Issue #4721: the fallback path previously returned results without calling
    _filter_stale_chunks(), silently returning stale/moved source paths.
    """

    @pytest.fixture(autouse=True)
    def reset_hash_cache_memo(self):
        """Reset module-level TTL cache before each test to ensure isolation."""
        import services.rag_service as rag_mod

        rag_mod._hash_cache_memo = {}
        rag_mod._hash_cache_loaded_at = 0.0
        yield
        rag_mod._hash_cache_memo = {}
        rag_mod._hash_cache_loaded_at = 0.0

    def _make_service(self):
        from services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        svc._initialized = True
        return svc

    def _make_kb_result(self, source: str, score: float = 0.8):
        return {"content": f"content from {source}", "metadata": {"source": source}, "score": score}

    @pytest.mark.asyncio
    async def test_filter_stale_chunks_is_called_on_fallback_path(self):
        """_filter_stale_chunks is awaited once during _fallback_basic_search."""
        svc = self._make_service()

        mock_kb_adapter = AsyncMock()
        mock_kb_adapter.search = AsyncMock(return_value=[self._make_kb_result("docs/a.md")])
        svc.kb_adapter = mock_kb_adapter

        with patch(
            "services.rag_service.RAGService._filter_stale_chunks",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_filter:
            await svc._fallback_basic_search(query="test query", max_results=5)

        mock_filter.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stale_chunks_removed_in_fallback_results(self, tmp_path):
        """Stale chunks are absent from the returned results on the fallback path."""
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text('{"docs/present.md": "abc"}', encoding="utf-8")

        svc = self._make_service()
        mock_kb_adapter = AsyncMock()
        mock_kb_adapter.search = AsyncMock(
            return_value=[
                self._make_kb_result("docs/present.md"),
                self._make_kb_result("docs/removed.md"),
            ]
        )
        svc.kb_adapter = mock_kb_adapter

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            results, metrics = await svc._fallback_basic_search(query="test", max_results=10)

        source_paths = [r.source_path for r in results]
        assert "docs/present.md" in source_paths
        assert "docs/removed.md" not in source_paths

    @pytest.mark.asyncio
    async def test_valid_chunks_preserved_in_fallback_results(self, tmp_path):
        """Non-stale chunks are kept in the returned results on the fallback path."""
        cache_file = tmp_path / ".doc_index_hashes.json"
        cache_file.write_text('{"docs/guide.md": "hash1", "docs/ref.md": "hash2"}', encoding="utf-8")

        svc = self._make_service()
        mock_kb_adapter = AsyncMock()
        mock_kb_adapter.search = AsyncMock(
            return_value=[
                self._make_kb_result("docs/guide.md"),
                self._make_kb_result("docs/ref.md"),
            ]
        )
        svc.kb_adapter = mock_kb_adapter

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            results, metrics = await svc._fallback_basic_search(query="test", max_results=10)

        assert len(results) == 2
        assert metrics.final_results_count == 2

    @pytest.mark.asyncio
    async def test_metrics_reflect_post_filter_count(self, tmp_path):
        """metrics.final_results_count matches the count after stale filtering."""
        cache_file = tmp_path / ".doc_index_hashes.json"
        # Only one of two source paths is present in the cache
        cache_file.write_text('{"docs/kept.md": "hash"}', encoding="utf-8")

        svc = self._make_service()
        mock_kb_adapter = AsyncMock()
        mock_kb_adapter.search = AsyncMock(
            return_value=[
                self._make_kb_result("docs/kept.md"),
                self._make_kb_result("docs/gone.md"),
            ]
        )
        svc.kb_adapter = mock_kb_adapter

        with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
            results, metrics = await svc._fallback_basic_search(query="test", max_results=10)

        assert len(results) == 1
        assert metrics.final_results_count == 1
