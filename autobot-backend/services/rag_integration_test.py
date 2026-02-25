#!/usr/bin/env python3
"""
Comprehensive tests for Advanced RAG Integration.

Tests cover:
- KnowledgeBaseAdapter
- RAGConfig
- RAGService
- Cross-encoder reranking
- API endpoints
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from advanced_rag_optimizer import RAGMetrics, SearchResult
from services.knowledge_base_adapter import KnowledgeBaseAdapter
from services.rag_config import RAGConfig, get_rag_config, update_rag_config
from services.rag_service import RAGService


class TestKnowledgeBaseAdapter:
    """Tests for KnowledgeBaseAdapter unified interface."""

    def test_adapter_initialization(self):
        """Test adapter initializes with both KB implementations."""
        # Mock knowledge base
        mock_kb = Mock()
        mock_kb.__class__.__name__ = "KnowledgeBase"

        adapter = KnowledgeBaseAdapter(mock_kb)

        assert adapter.kb == mock_kb
        assert adapter.kb_type == "KnowledgeBase"
        assert adapter.implementation_type == "KnowledgeBase"

    @pytest.mark.asyncio
    async def test_search_kb_v1(self):
        """Test search with KnowledgeBase V1 implementation."""
        # Mock KnowledgeBase V1
        mock_kb = AsyncMock()
        mock_kb.__class__.__name__ = "KnowledgeBase"
        mock_kb.search.return_value = [
            {"content": "test content", "metadata": {}, "score": 0.9}
        ]

        adapter = KnowledgeBaseAdapter(mock_kb)
        results = await adapter.search(query="test", top_k=5)

        # Verify correct V1 parameters used
        mock_kb.search.assert_called_once()
        call_kwargs = mock_kb.search.call_args[1]
        assert "similarity_top_k" in call_kwargs
        assert call_kwargs["similarity_top_k"] == 5

        assert len(results) == 1
        assert results[0]["content"] == "test content"

    @pytest.mark.asyncio
    async def test_search_kb_v2(self):
        """Test search with KnowledgeBase V2 implementation."""
        # Mock KnowledgeBase V2
        mock_kb = AsyncMock()
        mock_kb.__class__.__name__ = "KnowledgeBaseV2"
        mock_kb.search.return_value = [
            {"content": "test content", "metadata": {}, "score": 0.9}
        ]

        adapter = KnowledgeBaseAdapter(mock_kb)
        results = await adapter.search(query="test", top_k=5)

        # Verify correct V2 parameters used
        mock_kb.search.assert_called_once()
        call_kwargs = mock_kb.search.call_args[1]
        assert "top_k" in call_kwargs
        assert call_kwargs["top_k"] == 5

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_all_facts(self):
        """Test getting all facts through adapter."""
        mock_kb = AsyncMock()
        mock_kb.__class__.__name__ = "KnowledgeBase"
        mock_kb.get_all_facts.return_value = [
            {"content": "fact1"},
            {"content": "fact2"},
        ]

        adapter = KnowledgeBaseAdapter(mock_kb)
        facts = await adapter.get_all_facts()

        assert len(facts) == 2
        mock_kb.get_all_facts.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting stats through adapter."""
        mock_kb = AsyncMock()
        mock_kb.__class__.__name__ = "KnowledgeBase"
        mock_kb.get_stats.return_value = {"total_facts": 100}

        adapter = KnowledgeBaseAdapter(mock_kb)
        stats = await adapter.get_stats()

        assert stats["total_facts"] == 100
        assert stats["kb_implementation"] == "KnowledgeBase"


class TestRAGConfig:
    """Tests for RAG configuration management."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RAGConfig()

        assert config.hybrid_weight_semantic == 0.7
        assert config.hybrid_weight_keyword == 0.3
        assert config.enable_reranking is True
        assert config.max_results_per_stage == 20

    def test_weight_validation(self, caplog):
        """Test weight normalization."""
        import logging

        # Suppress expected warning during intentional validation test
        with caplog.at_level(logging.ERROR, logger="rag_config"):
            config = RAGConfig(
                hybrid_weight_semantic=0.8,
                hybrid_weight_keyword=0.3,  # Sum > 1.0 - intentionally tests normalization
            )

        # Weights should be normalized
        assert (
            abs(config.hybrid_weight_semantic + config.hybrid_weight_keyword - 1.0)
            < 0.01
        )

    def test_invalid_weights(self):
        """Test invalid weight values raise errors or get normalized."""
        # Positive out-of-range values get normalized (#788)
        config = RAGConfig(hybrid_weight_semantic=1.5)
        assert (
            abs(config.hybrid_weight_semantic + config.hybrid_weight_keyword - 1.0)
            < 0.01
        )

        # Negative values cause ValueError after normalization pushes
        # the other weight out of range
        with pytest.raises(ValueError, match="must be 0-1"):
            RAGConfig(hybrid_weight_keyword=-0.1)

    def test_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            "hybrid_weight_semantic": 0.6,
            "hybrid_weight_keyword": 0.4,
            "enable_reranking": False,
        }

        config = RAGConfig.from_dict(config_dict)

        assert config.hybrid_weight_semantic == 0.6
        assert config.hybrid_weight_keyword == 0.4
        assert config.enable_reranking is False

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = RAGConfig()
        config_dict = config.to_dict()

        assert "hybrid_weight_semantic" in config_dict
        assert "enable_reranking" in config_dict
        assert config_dict["hybrid_weight_semantic"] == 0.7

    def test_update_config(self):
        """Test runtime configuration updates."""
        # Reset singleton
        import services.rag_config as rag_config_module

        rag_config_module._rag_config_instance = None

        # Create initial config
        config = get_rag_config()
        assert config.enable_reranking is True

        # Update config
        updated = update_rag_config({"enable_reranking": False})

        assert updated.enable_reranking is False

        # Verify singleton updated
        current = get_rag_config()
        assert current.enable_reranking is False


class TestRAGService:
    """Tests for RAGService functionality."""

    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """Test RAG service initializes correctly."""
        mock_kb = Mock()
        mock_kb.__class__.__name__ = "KnowledgeBase"

        service = RAGService(mock_kb)

        assert service.kb_adapter is not None
        assert service.config is not None
        assert service._initialized is False

    @pytest.mark.asyncio
    async def test_fallback_when_rag_disabled(self):
        """Test fallback to basic search when RAG disabled."""
        mock_kb = AsyncMock()
        mock_kb.__class__.__name__ = "KnowledgeBase"
        mock_kb.search.return_value = [
            {"content": "fallback result", "metadata": {}, "score": 0.8}
        ]

        config = RAGConfig(enable_advanced_rag=False)
        service = RAGService(mock_kb, config=config)

        results, metrics = await service.advanced_search("test query")

        # Should use fallback
        assert len(results) == 1
        assert results[0].content == "fallback result"

    @pytest.mark.asyncio
    async def test_rerank_results(self):
        """Test reranking functionality."""
        mock_kb = Mock()
        mock_kb.__class__.__name__ = "KnowledgeBase"

        service = RAGService(mock_kb)

        # Mock the optimizer
        service._initialized = True
        service.optimizer = Mock()
        service.optimizer._rerank_with_cross_encoder = AsyncMock()

        # Create test results
        test_results = [
            {"content": "result 1", "metadata": {}, "score": 0.5},
            {"content": "result 2", "metadata": {}, "score": 0.8},
        ]

        # Mock reranking to return in different order
        reranked_search_results = [
            SearchResult(
                content="result 2",
                metadata={},
                semantic_score=0.8,
                keyword_score=0.0,
                hybrid_score=0.8,
                relevance_rank=1,
                source_path="test",
                rerank_score=0.95,
            ),
            SearchResult(
                content="result 1",
                metadata={},
                semantic_score=0.5,
                keyword_score=0.0,
                hybrid_score=0.5,
                relevance_rank=2,
                source_path="test",
                rerank_score=0.6,
            ),
        ]

        service.optimizer._rerank_with_cross_encoder.return_value = (
            reranked_search_results
        )

        reranked = await service.rerank_results("test query", test_results)

        # Should have rerank scores added
        assert len(reranked) == 2
        assert reranked[0]["rerank_score"] == 0.95
        assert reranked[1]["rerank_score"] == 0.6

    def test_cache_management(self):
        """Test result caching functionality."""
        mock_kb = Mock()
        mock_kb.__class__.__name__ = "KnowledgeBase"

        service = RAGService(mock_kb)

        # Add to cache
        test_results = ([Mock()], RAGMetrics())
        service._add_to_cache("test_key", test_results)

        # Retrieve from cache
        cached = service._get_from_cache("test_key")
        assert cached is not None

        # Clear cache
        service.clear_cache()
        cached_after_clear = service._get_from_cache("test_key")
        assert cached_after_clear is None


class TestCrossEncoderReranking:
    """Tests for cross-encoder reranking upgrade."""

    @pytest.mark.asyncio
    async def test_cross_encoder_fallback(self):
        """Test fallback when cross-encoder unavailable."""
        from advanced_rag_optimizer import AdvancedRAGOptimizer

        optimizer = AdvancedRAGOptimizer()

        # Create test results
        results = [
            SearchResult(
                content="test content with query terms",
                metadata={},
                semantic_score=0.5,
                keyword_score=0.3,
                hybrid_score=0.4,
                relevance_rank=1,
                source_path="test",
            )
        ]

        # Mock missing cross-encoder
        optimizer._cross_encoder = None

        reranked = await optimizer._rerank_with_cross_encoder("query terms", results)

        # Should still return results with fallback scoring
        assert len(reranked) == 1
        assert reranked[0].rerank_score is not None

    @pytest.mark.asyncio
    @patch("src.advanced_rag_optimizer.CrossEncoder")
    async def test_cross_encoder_integration(self, mock_cross_encoder_class):
        """Test cross-encoder model integration."""
        from advanced_rag_optimizer import AdvancedRAGOptimizer

        # Mock cross-encoder predict
        mock_ce = Mock()
        mock_ce.predict.return_value = [0.9, 0.6]  # Relevance scores
        mock_cross_encoder_class.return_value = mock_ce

        optimizer = AdvancedRAGOptimizer()

        # Create test results
        results = [
            SearchResult(
                content="result 1",
                metadata={},
                semantic_score=0.5,
                keyword_score=0.2,
                hybrid_score=0.4,
                relevance_rank=1,
                source_path="test",
            ),
            SearchResult(
                content="result 2",
                metadata={},
                semantic_score=0.7,
                keyword_score=0.3,
                hybrid_score=0.6,
                relevance_rank=2,
                source_path="test",
            ),
        ]

        reranked = await optimizer._rerank_with_cross_encoder("test query", results)

        # Verify cross-encoder was loaded
        assert hasattr(optimizer, "_cross_encoder")

        # Verify results reranked
        assert len(reranked) == 2
        # First result should have higher score (0.9)
        assert reranked[0].rerank_score > reranked[1].rerank_score


class TestAPIEndpoints:
    """Tests for advanced RAG API endpoints."""

    @pytest.mark.asyncio
    async def test_search_with_reranking_parameter(self):
        """Test /search endpoint accepts enable_reranking parameter."""
        # This would require FastAPI TestClient integration
        # Placeholder for integration test

    @pytest.mark.asyncio
    async def test_advanced_search_endpoint(self):
        """Test /knowledge_base/rag/advanced_search endpoint."""
        # This would require FastAPI TestClient integration
        # Placeholder for integration test

    @pytest.mark.asyncio
    async def test_rerank_results_endpoint(self):
        """Test /knowledge_base/rag/rerank_results endpoint."""
        # This would require FastAPI TestClient integration
        # Placeholder for integration test

    @pytest.mark.asyncio
    async def test_config_get_endpoint(self):
        """Test /knowledge_base/rag/config endpoint GET."""
        # This would require FastAPI TestClient integration
        # Placeholder for integration test

    @pytest.mark.asyncio
    async def test_config_update_endpoint(self):
        """Test /knowledge_base/rag/config endpoint PUT."""
        # This would require FastAPI TestClient integration
        # Placeholder for integration test


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
