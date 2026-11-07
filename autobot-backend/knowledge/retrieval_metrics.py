# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Pure retrieval-quality metrics for the retrieval benchmark gate.

Issue #20949. No I/O, no retriever dependency: every function takes ranked ids
and gold ids and returns a number, so the math is testable by hand.

Relevance is graded: ``gold`` maps doc id -> gain (a set means gain 1 each).
"""

from __future__ import annotations

import math
import os
import re
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Union

#: Fraction of a claim's content tokens that must appear in a chunk for the
#: default lexical support check to count the claim as grounded.
GROUNDING_OVERLAP_THRESHOLD = float(os.getenv("AUTOBOT_RETRIEVAL_GROUNDING_OVERLAP", "0.6"))

Gold = Union[Set[str], Mapping[str, float]]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN = re.compile(r"[a-z0-9_]+")
_STOPWORDS = frozenset(
    "a an the is are was were be been of to in on for and or with by at as it this that from".split()
)


def _gains(gold: Gold) -> Dict[str, float]:
    if isinstance(gold, Mapping):
        return {k: float(v) for k, v in gold.items() if v > 0}
    return {k: 1.0 for k in gold}


def recall_at_k(ranked: Sequence[str], gold: Gold, k: int) -> float:
    """Share of relevant docs found in the top *k*; 0.0 when nothing is relevant."""
    rel = _gains(gold)
    if not rel:
        return 0.0
    return len(set(ranked[:k]) & set(rel)) / len(rel)


def reciprocal_rank(ranked: Sequence[str], gold: Gold) -> float:
    """1/rank of the first relevant doc (1-based); 0.0 when none is retrieved."""
    rel = _gains(gold)
    for i, doc in enumerate(ranked, start=1):
        if doc in rel:
            return 1.0 / i
    return 0.0


def _dcg(gains: Iterable[float]) -> float:
    return sum(g / math.log2(i + 1) for i, g in enumerate(gains, start=1))


def ndcg_at_k(ranked: Sequence[str], gold: Gold, k: int) -> float:
    """nDCG@k with gain/log2(rank+1); 1.0 for the ideal ordering, 0.0 if no gold."""
    rel = _gains(gold)
    if not rel:
        return 0.0
    seen: Set[str] = set()
    got: List[float] = []
    for doc in ranked[:k]:
        got.append(rel.get(doc, 0.0) if doc not in seen else 0.0)
        seen.add(doc)
    ideal = sorted(rel.values(), reverse=True)[:k]
    return _dcg(got) / _dcg(ideal)


def split_claims(answer: str) -> List[str]:
    """Split an answer into sentence-level claims (empty fragments dropped)."""
    return [c.strip() for c in _SENTENCE_SPLIT.split(answer) if c.strip()]


def _content_tokens(text: str) -> Set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS}


def lexical_claim_supported(claim: str, chunk: str) -> bool:
    """Default support check: enough of the claim's content tokens occur in *chunk*."""
    tokens = _content_tokens(claim)
    if not tokens:
        return True
    return len(tokens & _content_tokens(chunk)) / len(tokens) >= GROUNDING_OVERLAP_THRESHOLD


def grounding_rate(
    answer: str,
    chunks: Sequence[str],
    supported: Callable[[str, str], bool] = lexical_claim_supported,
) -> Optional[float]:
    """Share of answer claims traced to at least one retrieved chunk.

    Returns None when the answer has no claims (nothing to ground).
    """
    claims = split_claims(answer)
    if not claims:
        return None
    hit = sum(1 for c in claims if any(supported(c, ch) for ch in chunks))
    return hit / len(claims)


def contradiction_rate(
    texts_per_query: Sequence[Sequence[str]],
    has_conflict: Callable[[Sequence[str]], bool],
) -> Optional[float]:
    """Share of queries whose answer/context texts contain conflicting facts.

    *has_conflict* is injected (production wires the contradiction detector).
    """
    if not texts_per_query:
        return None
    return sum(1 for t in texts_per_query if has_conflict(t)) / len(texts_per_query)


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    """Mean ignoring None; None when nothing was measured."""
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None
