# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Query Complexity Classifier for Dynamic Hybrid Search Weight Selection

Issue #1719: Dynamic per-query hybrid search weight selection.
Classifies incoming queries into complexity tiers so that hybrid search
fusion weights can be adapted per query rather than using static globals.
"""

import re
from enum import Enum
from typing import List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Complexity tier
# ---------------------------------------------------------------------------


class QueryComplexity(Enum):
    """Complexity tiers used to select hybrid search fusion weights.

    Issue #1719: Maps to weight presets consumed by HybridSearcher.
    """

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    MULTI_HOP = "multi_hop"


# ---------------------------------------------------------------------------
# Pattern tables (compiled once at import time)
# ---------------------------------------------------------------------------

_MULTI_HOP_PATTERNS: List[re.Pattern] = [
    re.compile(r"what\s+caused\s+\w+.*that\s+led\s+to", re.IGNORECASE),
    re.compile(r"trace\s+\w+.*from\s+\w+.*to\s+\w+", re.IGNORECASE),
    re.compile(r"chain\s+of\s+\w+\s+that", re.IGNORECASE),
    re.compile(r"sequence\s+of\s+events\s+that\s+caused", re.IGNORECASE),
    re.compile(r"how\s+did\s+\w+.*lead\s+to\s+\w+", re.IGNORECASE),
]

_COMPLEX_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bcompare\b.*\band\b", re.IGNORECASE),
    re.compile(r"\banalyze\b.*\bacross\b", re.IGNORECASE),
    re.compile(r"\bpros\s+and\s+cons\b", re.IGNORECASE),
    re.compile(r"\bsimilarities\s+between\b", re.IGNORECASE),
    re.compile(r"\bdifferences\s+between\b", re.IGNORECASE),
    re.compile(r"\bcontrast\b.*\bwith\b", re.IGNORECASE),
    re.compile(r"\badvantages\s+and\s+disadvantages\b", re.IGNORECASE),
]

_MODERATE_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bhow\s+does\s+\w+\s+relate\b", re.IGNORECASE),
    re.compile(r"\bconnection\s+between\b", re.IGNORECASE),
    re.compile(r"\bwhy\s+does\b", re.IGNORECASE),
    re.compile(r"\bwhy\s+did\b", re.IGNORECASE),
    re.compile(r"\bexplain\s+how\s+\w+\s+works\b", re.IGNORECASE),
    re.compile(r"\brelationship\s+between\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+is\s+the\s+impact\s+of\b", re.IGNORECASE),
]

# Clause-boundary markers for heuristic complexity scoring
_CLAUSE_BOUNDARY = re.compile(
    r"[,;]|\b(and|but|or|because|although|whereas|while)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class QueryClassifier:
    """Rule-based query complexity classifier with heuristic fallback.

    Classification order (first match wins):
    1. MULTI_HOP  — multi-step causal / tracing patterns
    2. COMPLEX    — comparison / analysis patterns
    3. MODERATE   — relational / explanatory patterns
    4. Heuristic  — clause count or word count thresholds
    5. SIMPLE     — default

    Issue #1719: Enables adaptive hybrid search weight selection.
    """

    def classify(self, query: str) -> QueryComplexity:
        """Classify a query string into a QueryComplexity tier.

        Args:
            query: Raw user query string.

        Returns:
            QueryComplexity enum value for this query.
        """
        if not query or not query.strip():
            logger.debug("Empty query — defaulting to SIMPLE")
            return QueryComplexity.SIMPLE

        normalized = query.strip()

        tier = self._match_patterns(normalized)
        if tier is None:
            tier = self._heuristic_classify(normalized)

        logger.debug("Query classified as %s: %r", tier.value, query[:80])
        return tier

    def _match_patterns(self, query: str) -> "QueryComplexity | None":
        """Apply ordered regex pattern tables. Returns None if no match.

        Issue #1719: Fast path — avoids heuristic cost when pattern hits.
        """
        if self._any_match(query, _MULTI_HOP_PATTERNS):
            return QueryComplexity.MULTI_HOP
        if self._any_match(query, _COMPLEX_PATTERNS):
            return QueryComplexity.COMPLEX
        if self._any_match(query, _MODERATE_PATTERNS):
            return QueryComplexity.MODERATE
        return None

    @staticmethod
    def _any_match(query: str, patterns: List[re.Pattern]) -> bool:
        """Return True if any compiled pattern matches the query."""
        return any(p.search(query) for p in patterns)

    def _heuristic_classify(self, query: str) -> QueryComplexity:
        """Classify by clause count and word count when patterns miss.

        Thresholds (Issue #1719):
        - clause_count >= 3 OR word_count >= 20  → COMPLEX
        - clause_count >= 2 OR word_count >= 12  → MODERATE
        - otherwise                               → SIMPLE
        """
        clause_count, word_count = self._query_metrics(query)
        if clause_count >= 3 or word_count >= 20:
            return QueryComplexity.COMPLEX
        if clause_count >= 2 or word_count >= 12:
            return QueryComplexity.MODERATE
        return QueryComplexity.SIMPLE

    @staticmethod
    def _query_metrics(query: str) -> Tuple[int, int]:
        """Return (clause_count, word_count) for a normalized query string."""
        word_count = len(query.split())
        clause_boundaries = _CLAUSE_BOUNDARY.findall(query)
        # Number of clauses = boundaries + 1
        clause_count = len(clause_boundaries) + 1
        return clause_count, word_count


get_query_classifier = lazy_singleton(QueryClassifier)
