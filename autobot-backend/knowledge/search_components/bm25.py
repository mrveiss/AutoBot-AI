# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
BM25 Scorer Module

Issue #1720: Upgrade keyword search from TF-only to BM25 Okapi scoring.
Provides IDF with Laplace smoothing and document length normalization.
"""

import math
from typing import Callable, Dict, List, Sequence

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def bm25_tf_component(tf: int, doc_length: int, avg_doc_length: float, k1: float, b: float) -> float:
    """
    The one BM25 term-frequency saturation + length-normalisation formula (#18183).

    tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl)). Every BM25 scorer in
    the codebase multiplies an IDF by this; the IDF is what differs per corpus.
    """
    denom = tf + k1 * (1.0 - b + b * doc_length / avg_doc_length)
    return (tf * (k1 + 1.0)) / denom


def bm25_score_terms(
    query_terms: Sequence[str],
    document_terms: Sequence[str],
    avg_doc_len: float,
    k1: float,
    b: float,
    idf: Callable[[str, int], float],
) -> float:
    """
    Score a tokenised document against query terms with a caller-supplied IDF.

    ``idf(term, tf)`` receives the term and its in-document frequency, so a
    corpus with no document-frequency table (the memory graph) and one with
    (the knowledge base) share this loop and the shared tf component.
    Distinct query terms are scored once; absent terms contribute nothing.
    """
    if not query_terms or not document_terms:
        return 0.0
    term_freqs: Dict[str, int] = {}
    for term in document_terms:
        term_freqs[term] = term_freqs.get(term, 0) + 1
    avg = max(avg_doc_len, 1)
    score = 0.0
    for term in set(query_terms):
        tf = term_freqs.get(term, 0)
        if tf:
            score += idf(term, tf) * bm25_tf_component(tf, len(document_terms), avg, k1, b)
    return score


class BM25Scorer:
    """
    BM25 Okapi scorer with IDF smoothing and length normalization.

    Replaces the TF-only `score_fact_by_terms()` helper with proper
    BM25 scoring:
    - IDF: log((N - df + 0.5) / (df + 0.5) + 1.0)  — Laplace-smoothed
    - TF saturation: tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))

    Args:
        total_docs:      Total number of documents in the corpus (N).
        avg_doc_length:  Average document length in tokens (avgdl).
        doc_frequencies: Mapping of term → number of docs containing it (df).
        k1:              Term frequency saturation parameter (default 1.2).
        b:               Length normalization parameter (default 0.75).
    """

    def __init__(
        self,
        total_docs: int,
        avg_doc_length: float,
        doc_frequencies: Dict[str, int],
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        """Initialize BM25Scorer with corpus statistics and tuning parameters."""
        self.total_docs = max(total_docs, 1)
        self.avg_doc_length = max(avg_doc_length, 1.0)
        self.doc_frequencies = doc_frequencies
        self.k1 = k1
        self.b = b

    def idf(self, term: str) -> float:
        """
        Compute IDF for a term using Laplace smoothing (#1720).

        Returns log((N - df + 0.5) / (df + 0.5) + 1.0) so unknown terms
        still receive a positive score rather than zero or negative IDF.
        """
        df = self.doc_frequencies.get(term, 0)
        n = self.total_docs
        return math.log((n - df + 0.5) / (df + 0.5) + 1.0)

    def _tf_normalized(self, term: str, doc_text: str, doc_length: int) -> float:
        """
        Compute BM25 TF component with length normalization (#1720).

        Uses exact token count via split() for consistency with
        corpus stat computation in KeywordSearcher.
        """
        tokens = doc_text.lower().split()
        tf = tokens.count(term.lower())
        if tf == 0:
            return 0.0
        dl = max(doc_length, 1)
        return bm25_tf_component(tf, dl, self.avg_doc_length, self.k1, self.b)

    def score(self, query_terms: List[str], doc_text: str, doc_length: int) -> float:
        """
        Compute BM25 Okapi score for a document given a list of query terms.

        Args:
            query_terms: Tokenised query terms (lower-case expected).
            doc_text:    Full document text for in-document TF counting.
            doc_length:  Pre-computed document length (token count).

        Returns:
            Non-negative BM25 score; higher means more relevant.
        """
        total = 0.0
        for term in query_terms:
            tf_norm = self._tf_normalized(term, doc_text, doc_length)
            if tf_norm > 0.0:
                total += self.idf(term) * tf_norm
        return total
