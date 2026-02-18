#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Advanced RAG Optimizer.

Issue #429: Tests for semantic and keyword search fixes.
"""

from unittest.mock import AsyncMock

import pytest
from advanced_rag_optimizer import AdvancedRAGOptimizer, SearchResult


class TestSemanticSearch:
    """Tests for semantic search functionality (Issue #429 fix 1)."""

    @pytest.mark.asyncio
    async def test_semantic_search_uses_kb_search_method(self):
        """
        Issue #429: Verify semantic search uses kb.search() not kb.get_fact(query=...).

        The original bug was calling get_fact(query=query) which doesn't exist.
        The fix uses kb.search(query, top_k=limit) instead.
        """
        optimizer = AdvancedRAGOptimizer()

        # Mock knowledge base with search method
        mock_kb = AsyncMock()
        mock_kb.search.return_value = [
            {"content": "test content", "metadata": {"relative_path": "test.md"}},
            {"content": "more content", "metadata": {"relative_path": "test2.md"}},
        ]
        optimizer.kb = mock_kb

        # Perform semantic search
        results = await optimizer._perform_semantic_search("test query", limit=10)

        # Verify kb.search was called (not get_fact)
        mock_kb.search.assert_called_once_with("test query", top_k=10)

        # Verify results are properly formatted
        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        assert results[0].content == "test content"
        assert results[0].source_path == "test.md"

    @pytest.mark.asyncio
    async def test_semantic_search_handles_metadata_as_dict(self):
        """
        Issue #429: Verify metadata is treated as dict, not JSON string.

        The original bug called json.loads() on metadata that was already a dict.
        """
        optimizer = AdvancedRAGOptimizer()

        # Mock KB returning metadata as dict (not string)
        mock_kb = AsyncMock()
        mock_kb.search.return_value = [
            {
                "content": "test",
                "metadata": {
                    "relative_path": "docs/test.md",
                    "chunk_index": 3,
                    "category": "documentation",
                },
            }
        ]
        optimizer.kb = mock_kb

        results = await optimizer._perform_semantic_search("query")

        # Should not raise json.JSONDecodeError
        assert len(results) == 1
        assert results[0].source_path == "docs/test.md"
        assert results[0].chunk_index == 3
        assert results[0].metadata["category"] == "documentation"

    @pytest.mark.asyncio
    async def test_semantic_search_handles_empty_results(self):
        """Test semantic search handles empty results gracefully."""
        optimizer = AdvancedRAGOptimizer()

        mock_kb = AsyncMock()
        mock_kb.search.return_value = []
        optimizer.kb = mock_kb

        results = await optimizer._perform_semantic_search("nonexistent query")

        assert results == []


class TestKeywordSearch:
    """Tests for keyword search functionality (Issue #429 fix 2)."""

    def test_keyword_search_handles_metadata_as_dict(self):
        """
        Issue #429: Verify metadata is treated as dict, not JSON string.

        The original bug called json.loads() on metadata from get_all_facts()
        which already returns parsed dicts.
        """
        optimizer = AdvancedRAGOptimizer()

        # Mock facts with metadata as dict (as returned by get_all_facts)
        all_facts = [
            {
                "content": "Python is a programming language",
                "metadata": {
                    "relative_path": "docs/python.md",
                    "chunk_index": 1,
                },
            },
            {
                "content": "JavaScript runs in browsers",
                "metadata": {
                    "relative_path": "docs/javascript.md",
                    "chunk_index": 0,
                },
            },
        ]

        # Should not raise TypeError about json.loads receiving dict
        results = optimizer._perform_keyword_search("Python programming", all_facts)

        # Verify results
        assert len(results) >= 1
        # Python fact should match
        python_result = next((r for r in results if "Python" in r.content), None)
        assert python_result is not None
        assert python_result.source_path == "docs/python.md"

    def test_keyword_search_with_empty_metadata(self):
        """Test keyword search handles facts with empty or missing metadata."""
        optimizer = AdvancedRAGOptimizer()

        all_facts = [
            {"content": "test content"},  # No metadata
            {"content": "more test content", "metadata": {}},  # Empty metadata
            {
                "content": "full test content",
                "metadata": {"relative_path": "test.md"},
            },
        ]

        # Should not raise any errors
        results = optimizer._perform_keyword_search("test content", all_facts)

        assert len(results) == 3


class TestQueryContextAnalysis:
    """Tests for query context analysis."""

    def test_technical_query_classification(self):
        """Test technical queries are classified correctly."""
        optimizer = AdvancedRAGOptimizer()

        context = optimizer._analyze_query_context("how to install docker")

        assert context.query_type == "technical"
        assert context.complexity_score == 0.8

    def test_troubleshooting_query_classification(self):
        """Test troubleshooting queries are classified correctly."""
        optimizer = AdvancedRAGOptimizer()

        # Use "problem" which is in TROUBLESHOOTING_KEYWORDS but not technical_keywords
        context = optimizer._analyze_query_context(
            "I have a problem with my connection"
        )

        assert context.query_type == "troubleshooting"
        assert context.complexity_score == 0.9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
