# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for RAGService retrieval feedback event emission (#1516)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

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
        with patch(
            "services.rag_service.publish_live_event", new_callable=AsyncMock
        ) as mock_pub:
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
        with patch(
            "services.rag_service.publish_live_event", new_callable=AsyncMock
        ) as mock_pub:
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
        with patch(
            "services.rag_service.publish_live_event", new_callable=AsyncMock
        ) as mock_pub:
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
        with patch(
            "services.rag_service.publish_live_event", new_callable=AsyncMock
        ) as mock_pub:
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
        with patch(
            "services.rag_service.publish_live_event", new_callable=AsyncMock
        ) as mock_pub:
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
        with patch(
            "services.rag_service.publish_live_event", new_callable=AsyncMock
        ) as mock_pub:
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
        with patch(
            "services.rag_service.publish_live_event", new_callable=AsyncMock
        ) as mock_pub:
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

    _SEVEN_DAYS_SECONDS = 7 * 24 * 3600

    def _make_service(self):
        from services.rag_service import RAGService

        svc = RAGService.__new__(RAGService)
        svc._initialized = True
        return svc

    def _make_redis_mock(self, xadd_side_effect=None):
        """Build an async Redis mock that get_redis_client will return when awaited."""
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(
            return_value=b"1234-0",
            side_effect=xadd_side_effect,
        )
        mock_redis.expire = AsyncMock(return_value=True)
        return mock_redis

    @pytest.mark.asyncio
    async def test_xadd_called_with_feedback_stream_key(self):
        """Redis xadd is called with a key matching rag:feedback:{date}."""
        mock_redis = self._make_redis_mock()

        with patch(
            "services.rag_service.get_redis_client",
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
            "services.rag_service.get_redis_client",
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
            "services.rag_service.get_redis_client",
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
    async def test_expire_set_to_seven_days(self):
        """Stream key TTL is set to 7 days (604800 seconds)."""
        mock_redis = self._make_redis_mock()

        with patch(
            "services.rag_service.get_redis_client",
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
        assert ttl_arg == self._SEVEN_DAYS_SECONDS

    @pytest.mark.asyncio
    async def test_redis_unavailable_does_not_raise(self):
        """When Redis client is None, method completes without raising."""
        with patch(
            "services.rag_service.get_redis_client",
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
        mock_redis = self._make_redis_mock(
            xadd_side_effect=ConnectionError("redis gone")
        )

        with patch(
            "services.rag_service.get_redis_client",
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
        with patch(
            "services.rag_service.publish_live_event", new_callable=AsyncMock
        ) as mock_pub:
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

        with patch(
            "services.rag_service.publish_live_event", new_callable=AsyncMock
        ) as mock_pub:
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
        with patch(
            "services.rag_service.publish_live_event", new_callable=AsyncMock
        ) as mock_pub:
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
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value=b"1234-0")
        mock_redis.expire = AsyncMock(return_value=True)
        return mock_redis

    @pytest.mark.asyncio
    async def test_stream_entry_contains_complexity_field(self):
        """Redis stream entry includes a complexity field."""
        mock_redis = self._make_redis_mock()

        with patch(
            "services.rag_service.get_redis_client",
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
            "services.rag_service.get_redis_client",
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
            "services.rag_service.get_redis_client",
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
