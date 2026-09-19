# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared pytest fixtures for services/*_test.py.

mock_rag_service and sample_search_results were defined in
chat_knowledge_service_test.py and used only there until
chat_knowledge_rag_firewall_test.py (#16930 review split) needed them too.
A conftest fixture is discovered by every test module in this directory
without an explicit import, which is what avoids each importing module's
parameter list shadowing the import and tripping pyflakes' F811
("redefinition of unused ...") -- the failure mode an explicit
`from chat_knowledge_service_test import mock_rag_service` hits the moment
a second file uses it as a fixture parameter.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from advanced_rag_optimizer import SearchResult


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
