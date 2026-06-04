# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
BM25 Scorer Module

Issue #1720: Upgrade keyword search from TF-only to BM25 Okapi scoring.
Provides IDF with Laplace smoothing and document length normalization.
"""

import math
from typing import Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


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
        denom = tf + self.k1 * (1.0 - self.b + self.b * dl / self.avg_doc_length)
        return (tf * (self.k1 + 1.0)) / denom

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
