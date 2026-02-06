#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for ChatKnowledgeService.

Tests knowledge retrieval, filtering, formatting, graceful degradation,
query intent detection (Issue #249 Phase 2), and conversation-aware
query enhancement (Issue #249 Phase 3).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.advanced_rag_optimizer import RAGMetrics, SearchResult
from src.services.chat_knowledge_service import (
    ChatKnowledgeService,
    ConversationContextEnhancer,
    QueryKnowledgeIntent,
    QueryKnowledgeIntentDetector,
    get_context_enhancer,
    get_query_intent_detector,
)


@pytest.fixture
def mock_rag_service():
    """Create mock RAGService for testing."""
    mock = MagicMock()
    mock.advanced_search = AsyncMock()
    mock.get_stats = MagicMock(
        return_value={
            "initialized": True,
            "cache_entries": 5,
            "kb_implementation": "KnowledgeBaseV2",
        }
    )
    return mock


@pytest.fixture
def sample_search_results():
    """Create sample search results for testing."""
    return [
        SearchResult(
            content="Redis is configured in config/redis.yaml",
            metadata={"id": "fact1", "source": "docs/redis.md"},
            semantic_score=0.95,
            keyword_score=0.8,
            hybrid_score=0.9,
            relevance_rank=1,
            source_path="docs/redis.md",
            chunk_index=0,
            rerank_score=0.92,
        ),
        SearchResult(
            content="Use redis-cli to connect to Redis",
            metadata={"id": "fact2", "source": "docs/redis.md"},
            semantic_score=0.85,
            keyword_score=0.7,
            hybrid_score=0.8,
            relevance_rank=2,
            source_path="docs/redis.md",
            chunk_index=1,
            rerank_score=0.82,
        ),
        SearchResult(
            content="Redis default port is 6379",
            metadata={"id": "fact3", "source": "docs/network.md"},
            semantic_score=0.65,
            keyword_score=0.5,
            hybrid_score=0.6,
            relevance_rank=3,
            source_path="docs/network.md",
            chunk_index=0,
            rerank_score=0.58,  # Below default threshold
        ),
    ]


@pytest.mark.asyncio
async def test_retrieve_relevant_knowledge_success(
    mock_rag_service, sample_search_results
):
    """Test successful knowledge retrieval with filtering."""
    # Setup
    mock_rag_service.advanced_search.return_value = (
        sample_search_results,
        RAGMetrics(),
    )
    service = ChatKnowledgeService(mock_rag_service)

    # Execute
    context, citations = await service.retrieve_relevant_knowledge(
        query="How to configure Redis?",
        top_k=5,
        score_threshold=0.7,  # Should filter out fact3
    )

    # Verify
    assert "KNOWLEDGE CONTEXT:" in context
    assert "Redis is configured" in context
    assert "redis-cli" in context
    assert "Redis default port" not in context  # Filtered out (score 0.58 < 0.7)

    assert len(citations) == 2  # Only 2 facts above threshold
    assert citations[0]["id"] == "fact1"
    assert citations[0]["score"] == 0.92
    assert citations[1]["id"] == "fact2"


@pytest.mark.asyncio
async def test_retrieve_relevant_knowledge_empty_results(mock_rag_service):
    """Test handling of empty search results."""
    # Setup
    mock_rag_service.advanced_search.return_value = ([], RAGMetrics())
    service = ChatKnowledgeService(mock_rag_service)

    # Execute
    context, citations = await service.retrieve_relevant_knowledge(
        query="Nonexistent topic"
    )

    # Verify
    assert context == ""
    assert citations == []


@pytest.mark.asyncio
async def test_retrieve_relevant_knowledge_graceful_degradation(mock_rag_service):
    """Test graceful degradation on error."""
    # Setup - simulate error
    mock_rag_service.advanced_search.side_effect = Exception("RAG service failed")
    service = ChatKnowledgeService(mock_rag_service)

    # Execute - should not raise exception
    context, citations = await service.retrieve_relevant_knowledge(query="Test query")

    # Verify - returns empty results instead of failing
    assert context == ""
    assert citations == []


def test_filter_by_score(mock_rag_service, sample_search_results):
    """Test score-based filtering."""
    service = ChatKnowledgeService(mock_rag_service)

    # Test with threshold 0.7
    filtered = service._filter_by_score(sample_search_results, 0.7)
    assert len(filtered) == 2  # fact1 and fact2 only

    # Test with threshold 0.9
    filtered = service._filter_by_score(sample_search_results, 0.9)
    assert len(filtered) == 1  # fact1 only

    # Test with threshold 0.5
    filtered = service._filter_by_score(sample_search_results, 0.5)
    assert len(filtered) == 3  # All facts


def test_format_knowledge_context(mock_rag_service, sample_search_results):
    """Test context string formatting."""
    service = ChatKnowledgeService(mock_rag_service)

    # Format first 2 results
    context = service.format_knowledge_context(sample_search_results[:2])

    # Verify structure
    assert "KNOWLEDGE CONTEXT:" in context
    assert "1. [score: 0.92]" in context
    assert "2. [score: 0.82]" in context
    assert "Redis is configured" in context
    assert "redis-cli" in context


def test_format_knowledge_context_empty(mock_rag_service):
    """Test empty context formatting."""
    service = ChatKnowledgeService(mock_rag_service)
    context = service.format_knowledge_context([])
    assert context == ""


def test_format_citations(mock_rag_service, sample_search_results):
    """Test citation formatting."""
    service = ChatKnowledgeService(mock_rag_service)

    citations = service.format_citations(sample_search_results[:2])

    # Verify structure
    assert len(citations) == 2

    # Check first citation
    assert citations[0]["id"] == "fact1"
    assert citations[0]["content"] == "Redis is configured in config/redis.yaml"
    assert citations[0]["score"] == 0.92
    assert citations[0]["source"] == "docs/redis.md"
    assert citations[0]["rank"] == 1
    assert "metadata" in citations[0]
    assert citations[0]["metadata"]["rerank_score"] == 0.92

    # Check second citation
    assert citations[1]["id"] == "fact2"
    assert citations[1]["rank"] == 2


@pytest.mark.asyncio
async def test_get_knowledge_stats(mock_rag_service):
    """Test statistics retrieval."""
    service = ChatKnowledgeService(mock_rag_service)

    stats = await service.get_knowledge_stats()

    assert stats["service"] == "ChatKnowledgeService"
    assert stats["rag_service_initialized"] is True
    assert stats["rag_cache_entries"] == 5
    assert stats["kb_implementation"] == "KnowledgeBaseV2"


def test_filter_uses_rerank_score_when_available(mock_rag_service):
    """Test that filtering prefers rerank_score over hybrid_score."""
    service = ChatKnowledgeService(mock_rag_service)

    # Create result with rerank_score that differs from hybrid_score
    result = SearchResult(
        content="Test content",
        metadata={},
        semantic_score=0.5,
        keyword_score=0.5,
        hybrid_score=0.9,  # High hybrid score
        relevance_rank=1,
        source_path="test.md",
        rerank_score=0.6,  # Lower rerank score
    )

    # Filter with threshold 0.7
    # Should filter out because rerank_score (0.6) < threshold (0.7)
    # Even though hybrid_score (0.9) > threshold
    filtered = service._filter_by_score([result], 0.7)
    assert len(filtered) == 0


def test_filter_falls_back_to_hybrid_score(mock_rag_service):
    """Test that filtering uses hybrid_score when rerank_score unavailable."""
    service = ChatKnowledgeService(mock_rag_service)

    # Create result without rerank_score
    result = SearchResult(
        content="Test content",
        metadata={},
        semantic_score=0.8,
        keyword_score=0.7,
        hybrid_score=0.75,
        relevance_rank=1,
        source_path="test.md",
        rerank_score=None,  # No rerank score
    )

    # Filter with threshold 0.7
    # Should pass because hybrid_score (0.75) > threshold (0.7)
    filtered = service._filter_by_score([result], 0.7)
    assert len(filtered) == 1


# ============================================================================
# Issue #249 Phase 2: Query Intent Detection Tests
# ============================================================================


@pytest.fixture
def intent_detector():
    """Create QueryKnowledgeIntentDetector for testing."""
    return QueryKnowledgeIntentDetector()


class TestQueryIntentDetector:
    """Tests for QueryKnowledgeIntentDetector (Issue #249 Phase 2)."""

    def test_detect_knowledge_query_with_question(self, intent_detector):
        """Test detection of knowledge queries with question words."""
        queries = [
            "What is Redis?",
            "How do I configure the database?",
            "Why does the service fail?",
            "When should I restart?",
        ]
        for query in queries:
            result = intent_detector.detect_intent(query)
            assert result.intent == QueryKnowledgeIntent.KNOWLEDGE_QUERY
            assert result.should_use_knowledge is True
            assert result.confidence >= 0.7

    def test_detect_knowledge_query_with_keywords(self, intent_detector):
        """Test detection of knowledge queries with knowledge keywords."""
        queries = [
            "Explain the architecture",
            "Describe the deployment process",
            "Tell me about the configuration",
            "What's the difference between Redis and Memcached?",
        ]
        for query in queries:
            result = intent_detector.detect_intent(query)
            assert result.intent == QueryKnowledgeIntent.KNOWLEDGE_QUERY
            assert result.should_use_knowledge is True

    def test_detect_command_request(self, intent_detector):
        """Test detection of command requests - should skip RAG."""
        queries = [
            "run ls -la",
            "git status",
            "docker ps",
            "npm install express",
            "execute the backup script",
        ]
        for query in queries:
            result = intent_detector.detect_intent(query)
            assert result.intent == QueryKnowledgeIntent.COMMAND_REQUEST
            assert result.should_use_knowledge is False

    def test_detect_conversational(self, intent_detector):
        """Test detection of conversational messages - should skip RAG."""
        queries = [
            "Hello",
            "Hi there",
            "Thanks!",
            "Thank you very much",
            "Bye",
            "Goodbye",
            "Ok",
            "Got it",
            "Great!",
        ]
        for query in queries:
            result = intent_detector.detect_intent(query)
            assert result.intent == QueryKnowledgeIntent.CONVERSATIONAL
            assert result.should_use_knowledge is False
            assert result.confidence >= 0.9

    def test_detect_code_generation(self, intent_detector):
        """Test detection of code generation requests."""
        queries = [
            "Write a function to parse JSON",
            "Create a class for user authentication",
            "Generate a script to process logs",
            "Implement the data validation code",
        ]
        for query in queries:
            result = intent_detector.detect_intent(query)
            assert result.intent == QueryKnowledgeIntent.CODE_GENERATION
            assert result.should_use_knowledge is True  # Use RAG for context

    def test_detect_short_clarification(self, intent_detector):
        """Test detection of short clarification queries."""
        # "yes" and "no" match conversational patterns, so use other short queries
        queries = [
            "and?",
            "really?",
            "hm",
        ]
        for query in queries:
            result = intent_detector.detect_intent(query)
            # Short queries without clear patterns default to clarification
            assert result.should_use_knowledge is False
            assert result.intent == QueryKnowledgeIntent.CLARIFICATION
            assert result.confidence <= 0.6

    def test_yes_no_detected_as_conversational(self, intent_detector):
        """Test that yes/no are detected as conversational."""
        queries = ["yes", "no", "ok"]
        for query in queries:
            result = intent_detector.detect_intent(query)
            assert result.intent == QueryKnowledgeIntent.CONVERSATIONAL
            assert result.should_use_knowledge is False

    def test_detect_longer_ambiguous_query(self, intent_detector):
        """Test that longer queries default to using knowledge."""
        query = "I need some help understanding the system setup process"
        result = intent_detector.detect_intent(query)
        assert result.should_use_knowledge is True
        assert result.confidence >= 0.6

    def test_global_detector_singleton(self):
        """Test that get_query_intent_detector returns singleton."""
        detector1 = get_query_intent_detector()
        detector2 = get_query_intent_detector()
        assert detector1 is detector2


@pytest.mark.asyncio
async def test_smart_retrieve_knowledge_skips_for_commands(
    mock_rag_service, sample_search_results
):
    """Test that smart retrieval skips RAG for command requests."""
    mock_rag_service.advanced_search.return_value = (
        sample_search_results,
        RAGMetrics(),
    )
    service = ChatKnowledgeService(mock_rag_service)

    # Command request should skip retrieval
    context, citations, intent = await service.smart_retrieve_knowledge(
        query="git status",
        force_retrieval=False,
    )

    assert context == ""
    assert citations == []
    assert intent.intent == QueryKnowledgeIntent.COMMAND_REQUEST
    assert intent.should_use_knowledge is False

    # Verify RAG service was NOT called
    mock_rag_service.advanced_search.assert_not_called()


@pytest.mark.asyncio
async def test_smart_retrieve_knowledge_retrieves_for_questions(
    mock_rag_service, sample_search_results
):
    """Test that smart retrieval performs RAG for knowledge queries."""
    mock_rag_service.advanced_search.return_value = (
        sample_search_results,
        RAGMetrics(),
    )
    service = ChatKnowledgeService(mock_rag_service)

    # Knowledge query should trigger retrieval
    context, citations, intent = await service.smart_retrieve_knowledge(
        query="How do I configure Redis?",
        force_retrieval=False,
    )

    assert "KNOWLEDGE CONTEXT:" in context
    assert len(citations) == 2  # Only 2 above default threshold
    assert intent.intent == QueryKnowledgeIntent.KNOWLEDGE_QUERY
    assert intent.should_use_knowledge is True

    # Verify RAG service WAS called
    mock_rag_service.advanced_search.assert_called_once()


@pytest.mark.asyncio
async def test_smart_retrieve_knowledge_force_retrieval(
    mock_rag_service, sample_search_results
):
    """Test that force_retrieval bypasses intent detection."""
    mock_rag_service.advanced_search.return_value = (
        sample_search_results,
        RAGMetrics(),
    )
    service = ChatKnowledgeService(mock_rag_service)

    # Even for command, force_retrieval should trigger RAG
    context, citations, intent = await service.smart_retrieve_knowledge(
        query="git status",
        force_retrieval=True,  # Force retrieval
    )

    assert "KNOWLEDGE CONTEXT:" in context
    assert len(citations) >= 1
    assert intent.intent == QueryKnowledgeIntent.COMMAND_REQUEST

    # Verify RAG service WAS called despite command intent
    mock_rag_service.advanced_search.assert_called_once()


@pytest.mark.asyncio
async def test_smart_retrieve_knowledge_skips_for_greetings(
    mock_rag_service, sample_search_results
):
    """Test that smart retrieval skips RAG for conversational messages."""
    service = ChatKnowledgeService(mock_rag_service)

    # Greeting should skip retrieval
    context, citations, intent = await service.smart_retrieve_knowledge(
        query="Hello!",
        force_retrieval=False,
    )

    assert context == ""
    assert citations == []
    assert intent.intent == QueryKnowledgeIntent.CONVERSATIONAL

    # Verify RAG service was NOT called
    mock_rag_service.advanced_search.assert_not_called()


# ============================================================================
# Issue #249 Phase 3: Conversation Context Enhancement Tests
# ============================================================================


@pytest.fixture
def context_enhancer():
    """Create ConversationContextEnhancer for testing."""
    return ConversationContextEnhancer()


@pytest.fixture
def sample_conversation_history():
    """Create sample conversation history for testing."""
    return [
        {
            "user": "How do I configure Redis?",
            "assistant": "Redis is configured in config/redis.yaml. You can set the host, port, and database settings there.",
        },
        {
            "user": "What port does it use?",
            "assistant": "Redis uses port 6379 by default.",
        },
    ]


class TestConversationContextEnhancer:
    """Tests for ConversationContextEnhancer (Issue #249 Phase 3)."""

    def test_enhance_query_with_pronoun(
        self, context_enhancer, sample_conversation_history
    ):
        """Test that queries with pronouns get enhanced with context."""
        result = context_enhancer.enhance_query(
            query="How do I restart it?",
            conversation_history=sample_conversation_history,
        )

        assert result.enhancement_applied is True
        assert "Redis" in result.enhanced_query or "context" in result.enhanced_query
        assert result.original_query == "How do I restart it?"
        assert (
            "pronoun" in result.reasoning.lower()
            or "reference" in result.reasoning.lower()
            or "context" in result.reasoning.lower()
        )

    def test_enhance_query_without_pronoun(self, context_enhancer):
        """Test that queries without pronouns don't get enhanced."""
        result = context_enhancer.enhance_query(
            query="What is the best database for web applications?",
            conversation_history=[],
        )

        assert result.enhancement_applied is False
        assert result.enhanced_query == result.original_query

    def test_enhance_query_empty_history(self, context_enhancer):
        """Test handling of empty conversation history."""
        result = context_enhancer.enhance_query(
            query="Tell me more about it",
            conversation_history=[],
        )

        # Even with pronouns, no enhancement without history
        assert result.enhancement_applied is False
        assert result.enhanced_query == "Tell me more about it"

    def test_extract_entities_from_history(
        self, context_enhancer, sample_conversation_history
    ):
        """Test entity extraction from conversation history."""
        entities = context_enhancer._extract_entities(sample_conversation_history)

        assert "Redis" in entities
        # Should find technical entities

    def test_short_query_enhancement(
        self, context_enhancer, sample_conversation_history
    ):
        """Test that very short queries get context added."""
        result = context_enhancer.enhance_query(
            query="and?",
            conversation_history=sample_conversation_history,
        )

        # Short queries should be enhanced with context
        assert result.enhancement_applied is True
        assert len(result.enhanced_query) > len(result.original_query)

    def test_elaborate_query_enhancement(
        self, context_enhancer, sample_conversation_history
    ):
        """Test that 'tell me more' queries include prior context."""
        result = context_enhancer.enhance_query(
            query="Tell me more about that",
            conversation_history=sample_conversation_history,
        )

        assert result.enhancement_applied is True
        # Should include some reference to prior conversation

    def test_needs_context_enhancement_detection(self, context_enhancer):
        """Test the internal detection of context-needing queries."""
        # Should need enhancement
        assert context_enhancer._needs_context_enhancement("What about it?") is True
        assert context_enhancer._needs_context_enhancement("this") is True
        assert context_enhancer._needs_context_enhancement("and?") is True

        # Should not need enhancement (explicit, no pronouns)
        assert (
            context_enhancer._needs_context_enhancement(
                "What is the best way to configure Redis connection pooling?"
            )
            is False
        )

    def test_global_enhancer_singleton(self):
        """Test that get_context_enhancer returns singleton."""
        enhancer1 = get_context_enhancer()
        enhancer2 = get_context_enhancer()
        assert enhancer1 is enhancer2


@pytest.mark.asyncio
async def test_conversation_aware_retrieve_with_context(
    mock_rag_service, sample_search_results
):
    """Test conversation-aware retrieval with context enhancement."""
    mock_rag_service.advanced_search.return_value = (
        sample_search_results,
        RAGMetrics(),
    )
    service = ChatKnowledgeService(mock_rag_service)

    conversation_history = [
        {
            "user": "How do I configure Redis?",
            "assistant": "Redis is configured in config/redis.yaml.",
        },
    ]

    # Query with pronoun should use enhanced query for search
    context, citations, intent, enhanced = await service.conversation_aware_retrieve(
        query="How do I restart it?",
        conversation_history=conversation_history,
        force_retrieval=False,
    )

    assert intent.intent == QueryKnowledgeIntent.KNOWLEDGE_QUERY
    assert enhanced is not None
    assert enhanced.enhancement_applied is True
    # RAG service should have been called
    mock_rag_service.advanced_search.assert_called_once()


@pytest.mark.asyncio
async def test_conversation_aware_retrieve_skips_commands(
    mock_rag_service, sample_search_results
):
    """Test that conversation-aware retrieval still skips commands."""
    service = ChatKnowledgeService(mock_rag_service)

    conversation_history = [
        {
            "user": "How do I check Redis status?",
            "assistant": "You can use redis-cli ping.",
        },
    ]

    # Command should skip retrieval even with conversation history
    context, citations, intent, enhanced = await service.conversation_aware_retrieve(
        query="git status",
        conversation_history=conversation_history,
        force_retrieval=False,
    )

    assert context == ""
    assert citations == []
    assert intent.intent == QueryKnowledgeIntent.COMMAND_REQUEST
    assert enhanced is None  # No enhancement for skipped queries

    # Verify RAG service was NOT called
    mock_rag_service.advanced_search.assert_not_called()


@pytest.mark.asyncio
async def test_conversation_aware_retrieve_force_retrieval(
    mock_rag_service, sample_search_results
):
    """Test that force_retrieval bypasses intent detection."""
    mock_rag_service.advanced_search.return_value = (
        sample_search_results,
        RAGMetrics(),
    )
    service = ChatKnowledgeService(mock_rag_service)

    # Even for command, force_retrieval should trigger RAG
    context, citations, intent, enhanced = await service.conversation_aware_retrieve(
        query="git status",
        conversation_history=[],
        force_retrieval=True,
    )

    assert "KNOWLEDGE CONTEXT:" in context
    assert len(citations) >= 1
    assert intent.intent == QueryKnowledgeIntent.COMMAND_REQUEST

    # Verify RAG service WAS called despite command intent
    mock_rag_service.advanced_search.assert_called_once()


@pytest.mark.asyncio
async def test_conversation_aware_retrieve_without_enhancement(
    mock_rag_service, sample_search_results
):
    """Test retrieval when query doesn't need enhancement."""
    mock_rag_service.advanced_search.return_value = (
        sample_search_results,
        RAGMetrics(),
    )
    service = ChatKnowledgeService(mock_rag_service)

    # Explicit query without pronouns
    context, citations, intent, enhanced = await service.conversation_aware_retrieve(
        query="What is the default Redis port configuration?",
        conversation_history=[],
        force_retrieval=False,
    )

    assert "KNOWLEDGE CONTEXT:" in context
    assert enhanced is not None
    assert enhanced.enhancement_applied is False  # No enhancement needed
    assert enhanced.original_query == enhanced.enhanced_query
