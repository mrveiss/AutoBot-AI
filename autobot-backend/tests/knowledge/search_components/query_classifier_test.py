# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for QueryClassifier

Issue #1719: Dynamic per-query hybrid search weight selection.
Verifies that rule-based patterns and heuristic fallbacks correctly
classify queries into QueryComplexity tiers.
"""

import pytest

from knowledge.search_components.query_classifier import (
    QueryClassifier,
    QueryComplexity,
    get_query_classifier,
)


@pytest.fixture
def classifier() -> QueryClassifier:
    """Return a fresh QueryClassifier for each test."""
    return QueryClassifier()


# ---------------------------------------------------------------------------
# Parametrized classification correctness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected",
    [
        # SIMPLE — single-concept lookups
        ("What is Redis?", QueryComplexity.SIMPLE),
        ("List all tables", QueryComplexity.SIMPLE),
        ("GAN architecture", QueryComplexity.SIMPLE),
        ("error 0x80070005", QueryComplexity.SIMPLE),
        # MODERATE — relational / explanatory
        ("How does Redis relate to ChromaDB?", QueryComplexity.MODERATE),
        ("Explain how authentication works", QueryComplexity.MODERATE),
        ("Why does the service crash?", QueryComplexity.MODERATE),
        (
            "What is the connection between LangChain and LlamaIndex?",
            QueryComplexity.MODERATE,
        ),
        ("Why did the deployment fail?", QueryComplexity.MODERATE),
        # COMPLEX — comparative / analytical
        (
            "Compare Redis and Postgres and explain their trade-offs",
            QueryComplexity.COMPLEX,
        ),
        ("Pros and cons of using Docker Swarm", QueryComplexity.COMPLEX),
        (
            "Analyze performance differences across all worker nodes",
            QueryComplexity.COMPLEX,
        ),
        ("Similarities between BERT and GPT architectures", QueryComplexity.COMPLEX),
        # MULTI_HOP — causal chains
        (
            "What caused the memory leak that led to the service outage?",
            QueryComplexity.MULTI_HOP,
        ),
        (
            "Trace the request from the frontend to the database",
            QueryComplexity.MULTI_HOP,
        ),
        (
            "Describe the chain of events that caused the data loss",
            QueryComplexity.MULTI_HOP,
        ),
    ],
)
def test_classify_parametrized(classifier: QueryClassifier, query: str, expected: QueryComplexity) -> None:
    """Each query maps to the expected complexity tier."""
    result = classifier.classify(query)
    assert result == expected, f"Query {query!r}: expected {expected}, got {result}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_query_defaults_simple(classifier: QueryClassifier) -> None:
    """Empty string should default to SIMPLE without raising."""
    assert classifier.classify("") == QueryComplexity.SIMPLE


def test_whitespace_only_query_defaults_simple(classifier: QueryClassifier) -> None:
    """Whitespace-only string should default to SIMPLE without raising."""
    assert classifier.classify("   ") == QueryComplexity.SIMPLE


def test_returns_enum_type(classifier: QueryClassifier) -> None:
    """classify() must always return a QueryComplexity instance."""
    result = classifier.classify("What is a vector database?")
    assert isinstance(result, QueryComplexity)


# ---------------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------------


def test_long_query_heuristic_complex(classifier: QueryClassifier) -> None:
    """A long multi-clause query with no matching patterns classifies COMPLEX."""
    # 21 words, 3 clause boundaries (commas) — no pattern match
    long_query = (
        "first item, second item, third item, fourth item fifth sixth seventh "
        "eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth"
    )
    result = classifier.classify(long_query)
    assert result == QueryComplexity.COMPLEX


def test_medium_query_heuristic_moderate(classifier: QueryClassifier) -> None:
    """A medium-length query with one clause boundary classifies MODERATE."""
    # 13 words, 1 clause boundary — no pattern match
    medium_query = "the quick brown fox jumps over, the lazy dog in the field"
    result = classifier.classify(medium_query)
    assert result == QueryComplexity.MODERATE


def test_short_query_heuristic_simple(classifier: QueryClassifier) -> None:
    """A short single-clause query with no patterns classifies SIMPLE."""
    result = classifier.classify("quick brown fox")
    assert result == QueryComplexity.SIMPLE


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_get_query_classifier_singleton() -> None:
    """get_query_classifier() returns the same instance on repeated calls."""
    a = get_query_classifier()
    b = get_query_classifier()
    assert a is b


def test_get_query_classifier_returns_correct_type() -> None:
    """get_query_classifier() returns a QueryClassifier."""
    assert isinstance(get_query_classifier(), QueryClassifier)
