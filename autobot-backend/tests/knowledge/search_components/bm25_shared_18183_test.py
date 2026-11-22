# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One BM25 formula for the knowledge base and the memory graph (#18183).

The memory-graph `HybridScorer.bm25_score` keeps its own corpus-free IDF
(`log(1 + 1/(tf + 0.5))`) and its own constants (k1=1.5, b=0.75); only the
tf-saturation and length-normalisation formula is shared. These tests pin the
memory-graph scores and order against the CURRENT `HybridScorer`, so the repoint
of `bm25_score` onto `bm25_score_terms` cannot move a ranking.
"""

import math

import pytest

from knowledge.search_components.bm25 import BM25Scorer, bm25_score_terms, bm25_tf_component

_CORPUS = [
    ["the", "cat", "sat", "on", "the", "mat"],
    ["dog", "barked", "at", "the", "cat", "cat", "cat"],
    ["memory", "graph", "entity", "redis", "search", "entity"],
    ["a"],
    [
        "cat",
        "dog",
        "mat",
        "graph",
        "search",
        "redis",
        "entity",
        "memory",
        "the",
        "on",
        "sat",
        "at",
        "barked",
        "a",
        "cat",
    ],
]
_QUERIES = [["cat"], ["cat", "dog"], ["entity", "graph", "missing"], ["the", "the", "mat"], ["zzz"], []]

#: Scores of `HybridScorer().bm25_score(query, doc, 50.0)` captured before the repoint.
_PINNED_AVG50 = [
    [0.8457377876920374, 0.5335762808511805, 0.0, 0.0, 0.6202253209607611],
    [0.8457377876920374, 1.366897037402552, 0.0, 0.0, 1.365956158575346],
    [0.0, 0.0, 1.5160012072562066, 0.0, 1.4914616752291696],
    [1.5160012072562066, 0.8333207565513714, 0.0, 0.0, 1.4914616752291696],
    [0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.0, 0.0],
]
_PINNED_AVG6 = [
    [0.5108256237659906, 0.4021030852494496, 0.0, 0.0, 0.32431058951442204],
    [0.5108256237659906, 0.8772897120085106, 0.0, 0.0, 0.6292811111657597],
    [0.0, 0.0, 0.9915002475105805, 0.0, 0.6099410433026753],
    [0.9915002475105805, 0.47518662675906104, 0.0, 0.0, 0.6099410433026753],
    [0.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.0, 0.0],
]


def _memory_graph_via_shared(query, doc, avg):
    """The exact call the memory graph makes after the repoint."""
    return bm25_score_terms(query, doc, avg, 1.5, 0.75, lambda _term, tf: math.log(1 + (1.0 / (tf + 0.5))))


def _table(fn, avg):
    return [[fn(q, d, avg) for d in _CORPUS] for q in _QUERIES]


@pytest.mark.parametrize(("avg", "pinned"), [(50.0, _PINNED_AVG50), (6.0, _PINNED_AVG6)])
def test_shared_formula_reproduces_the_pinned_memory_graph_scores(avg, pinned):
    assert _table(_memory_graph_via_shared, avg) == pinned


@pytest.mark.parametrize("avg", [50.0, 6.0, 0.0])
def test_shared_formula_matches_the_live_hybrid_scorer(avg):
    from autobot_memory_graph.semantic_search import HybridScorer

    live = HybridScorer().bm25_score
    assert _table(_memory_graph_via_shared, avg) == _table(live, avg)


def test_pinned_ranking_order_is_unchanged():
    for row in _PINNED_AVG50:
        shared = _table(_memory_graph_via_shared, 50.0)[_PINNED_AVG50.index(row)]
        assert sorted(range(5), key=lambda i: -shared[i]) == sorted(range(5), key=lambda i: -row[i])


def test_knowledge_scorer_uses_the_shared_tf_component():
    scorer = BM25Scorer(total_docs=10, avg_doc_length=7.0, doc_frequencies={"cat": 2}, k1=1.2, b=0.75)
    text = "cat cat dog"
    expected = scorer.idf("cat") * bm25_tf_component(2, 3, 7.0, 1.2, 0.75)
    assert scorer.score(["cat"], text, 3) == expected


def test_contrast_a_different_constant_changes_the_score():
    """The parameterisation is real: k1/b are not ignored by the shared function."""
    idf = lambda _t, tf: 1.0  # noqa: E731
    a = bm25_score_terms(["cat"], _CORPUS[1], 7.0, 1.5, 0.75, idf)
    b = bm25_score_terms(["cat"], _CORPUS[1], 7.0, 1.2, 0.5, idf)
    assert a != b
