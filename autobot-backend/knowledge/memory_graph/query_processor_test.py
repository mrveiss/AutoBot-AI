# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""
Shim contract tests for `knowledge/memory_graph/` (#12650).

`hybrid_scorer.py` and `query_processor.py` in this package are compatibility
re-export shims onto `autobot_memory_graph.semantic_search` — the canonical
implementation, already covered by `autobot_memory_graph/semantic_search_test.py`.
These tests only assert the shim resolves to the exact canonical objects, so a
future accidental re-fork (a shim drifting back into its own implementation)
fails fast here instead of silently reintroducing the duplicate engine.
"""

from autobot_memory_graph.semantic_search import (
    HybridScorer as CanonicalHybridScorer,
)
from autobot_memory_graph.semantic_search import (
    MemoryGraphQueryProcessor as CanonicalMemoryGraphQueryProcessor,
)
from autobot_memory_graph.semantic_search import (
    QueryIntent as CanonicalQueryIntent,
)
from autobot_memory_graph.semantic_search import (
    SearchResult as CanonicalSearchResult,
)
from autobot_memory_graph.semantic_search import (
    ensure_indexes as canonical_ensure_indexes,
)
from knowledge.memory_graph.hybrid_scorer import HybridScorer, SearchResult
from knowledge.memory_graph.query_processor import (
    MemoryGraphQueryProcessor,
    QueryIntent,
    ensure_indexes,
)


def test_hybrid_scorer_is_canonical_object():
    assert HybridScorer is CanonicalHybridScorer


def test_search_result_is_canonical_object():
    assert SearchResult is CanonicalSearchResult


def test_query_processor_is_canonical_object():
    assert MemoryGraphQueryProcessor is CanonicalMemoryGraphQueryProcessor


def test_query_intent_is_canonical_object():
    assert QueryIntent is CanonicalQueryIntent


def test_ensure_indexes_is_canonical_object():
    assert ensure_indexes is canonical_ensure_indexes
