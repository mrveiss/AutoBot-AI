#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context Sufficiency Evaluator — validates cached RAG context before serving.

Prevents stale or partial cached answers by checking whether the cached
context actually covers the user's query. Two evaluation tiers:

  1. **Heuristic (fast, ~0.1ms):** Keyword overlap + temporal awareness.
  2. **LLM (optional, ~200-500ms):** Small model YES/NO evaluation when
     heuristic is inconclusive.

Issue: #1374
"""

import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stop words for keyword extraction (common English)
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "about",
        "between",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "and",
        "but",
        "or",
        "not",
        "so",
        "if",
        "then",
        "than",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "they",
        "them",
        "his",
        "her",
        "their",
        "what",
        "which",
        "who",
        "whom",
        "how",
        "when",
        "where",
        "why",
        "all",
        "each",
        "every",
        "any",
        "some",
        "no",
        "just",
        "only",
        "very",
        "also",
        "up",
        "out",
        "there",
        "here",
    }
)

# Temporal signal patterns and their max-age thresholds (seconds)
_TEMPORAL_PATTERNS = [
    (re.compile(r"\b(today|right now|currently)\b", re.I), 86400),
    (re.compile(r"\b(yesterday)\b", re.I), 172800),
    (re.compile(r"\b(this week|past few days)\b", re.I), 604800),
    (re.compile(r"\b(last week)\b", re.I), 1209600),
    (re.compile(r"\b(recently|lately)\b", re.I), 604800),
    (re.compile(r"\b(this month)\b", re.I), 2678400),
    (re.compile(r"\b(last month)\b", re.I), 5356800),
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class SufficiencyVerdict(str, Enum):
    """Result of a sufficiency evaluation."""

    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    INCONCLUSIVE = "inconclusive"


@dataclass
class SufficiencyResult:
    """Outcome of a context sufficiency check."""

    verdict: SufficiencyVerdict
    confidence: float  # 0.0–1.0
    reason: str
    keyword_coverage: float = 0.0
    temporal_ok: bool = True
    llm_used: bool = False
    evaluation_ms: float = 0.0


@dataclass
class SufficiencyConfig:
    """Tunable configuration for the evaluator."""

    enabled: bool = True
    keyword_threshold: float = 0.5
    inconclusive_band: float = 0.15
    enable_llm_pass: bool = True
    llm_timeout: float = 5.0
    max_context_age_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Heuristic evaluation helpers
# ---------------------------------------------------------------------------


def _extract_keywords(text: str) -> List[str]:
    """Extract content words from text, removing stop words."""
    words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 1]


def _compute_keyword_coverage(query_keywords: List[str], context: str) -> float:
    """Fraction of query keywords found in context. Ref: #1374."""
    if not query_keywords:
        return 1.0
    context_lower = context.lower()
    found = sum(1 for kw in query_keywords if kw in context_lower)
    return found / len(query_keywords)


def _check_temporal_freshness(query: str, cached_at: float, now: float) -> bool:
    """Check if cached context is fresh enough for temporal queries.

    Returns True if no temporal signal found or if cache is fresh enough.
    """
    age = now - cached_at
    for pattern, max_age in _TEMPORAL_PATTERNS:
        if pattern.search(query):
            if age > max_age:
                logger.debug(
                    "Temporal staleness: cache age %.0fs > max %.0fs",
                    age,
                    max_age,
                )
                return False
    return True


def _heuristic_evaluate(
    query: str,
    context: str,
    cached_at: float,
    config: SufficiencyConfig,
) -> SufficiencyResult:
    """Fast heuristic evaluation of context sufficiency. Ref: #1374."""
    start = time.monotonic()
    query_kw = _extract_keywords(query)
    coverage = _compute_keyword_coverage(query_kw, context)
    temporal_ok = _check_temporal_freshness(query, cached_at, time.time())

    if not temporal_ok:
        elapsed = (time.monotonic() - start) * 1000
        return SufficiencyResult(
            verdict=SufficiencyVerdict.INSUFFICIENT,
            confidence=0.9,
            reason="cached context is stale for time-sensitive query",
            keyword_coverage=coverage,
            temporal_ok=False,
            evaluation_ms=elapsed,
        )

    upper = config.keyword_threshold + config.inconclusive_band
    lower = config.keyword_threshold

    if coverage >= upper:
        verdict = SufficiencyVerdict.SUFFICIENT
        confidence = min(1.0, 0.7 + coverage * 0.3)
        reason = f"keyword coverage {coverage:.0%} above threshold"
    elif coverage < lower:
        verdict = SufficiencyVerdict.INSUFFICIENT
        confidence = min(1.0, 0.6 + (1.0 - coverage) * 0.3)
        reason = f"keyword coverage {coverage:.0%} below threshold"
    else:
        verdict = SufficiencyVerdict.INCONCLUSIVE
        confidence = 0.5
        reason = f"keyword coverage {coverage:.0%} in inconclusive band"

    elapsed = (time.monotonic() - start) * 1000
    return SufficiencyResult(
        verdict=verdict,
        confidence=confidence,
        reason=reason,
        keyword_coverage=coverage,
        temporal_ok=True,
        evaluation_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# LLM evaluation helper
# ---------------------------------------------------------------------------


def _build_sufficiency_messages(query: str, context: str) -> List[Dict]:
    """Build LLM prompt messages for sufficiency check. Ref: #1374."""
    return [
        {
            "role": "system",
            "content": (
                "You evaluate whether a given context passage "
                "can fully answer a user question. "
                "Respond with ONLY one word: YES or NO."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {query}\n\n"
                f"Context: {context[:2000]}\n\n"
                "Does this context fully answer the question?"
            ),
        },
    ]


def _parse_llm_verdict(answer: str, elapsed_ms: float) -> Optional[SufficiencyResult]:
    """Parse LLM YES/NO response into a SufficiencyResult. Ref: #1374."""
    text = answer.strip().upper()
    if "YES" in text:
        return SufficiencyResult(
            verdict=SufficiencyVerdict.SUFFICIENT,
            confidence=0.85,
            reason="LLM confirmed context sufficiency",
            llm_used=True,
            evaluation_ms=elapsed_ms,
        )
    if "NO" in text:
        return SufficiencyResult(
            verdict=SufficiencyVerdict.INSUFFICIENT,
            confidence=0.85,
            reason="LLM determined context insufficient",
            llm_used=True,
            evaluation_ms=elapsed_ms,
        )
    return None


async def _llm_evaluate(
    query: str,
    context: str,
    timeout: float,
) -> Optional[SufficiencyResult]:
    """Ask a small LLM whether context sufficiently answers the query.

    Returns None if LLM call fails or times out. Ref: #1374.
    """
    import asyncio

    try:
        from llm_interface_pkg.interface import LLMInterface

        llm = LLMInterface()
        messages = _build_sufficiency_messages(query, context)

        start = time.monotonic()
        response = await asyncio.wait_for(
            llm.chat_completion(
                messages=messages,
                llm_type="task",
                max_tokens=5,
                temperature=0.0,
            ),
            timeout=timeout,
        )
        elapsed = (time.monotonic() - start) * 1000
        return _parse_llm_verdict(response.content, elapsed)

    except asyncio.TimeoutError:
        logger.debug("LLM sufficiency check timed out after %.1fs", timeout)
        return None
    except Exception as exc:
        logger.debug("LLM sufficiency check failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main evaluator
# ---------------------------------------------------------------------------


class ContextSufficiencyEvaluator:
    """Evaluates whether cached context adequately answers a query.

    Usage::

        evaluator = ContextSufficiencyEvaluator()
        result = await evaluator.evaluate(query, context, cached_at)
        if result.verdict == SufficiencyVerdict.INSUFFICIENT:
            # trigger fresh retrieval
    """

    def __init__(self, config: Optional[SufficiencyConfig] = None):
        self._config = config or SufficiencyConfig()
        self._sufficient_count = 0
        self._insufficient_count = 0
        self._inconclusive_count = 0
        self._llm_calls = 0
        self._bypassed_count = 0

    async def evaluate(
        self,
        query: str,
        context: str,
        cached_at: float = 0.0,
    ) -> SufficiencyResult:
        """Run sufficiency evaluation pipeline. Ref: #1374.

        Steps:
        1. Heuristic check (always runs, sub-ms)
        2. If inconclusive and LLM pass enabled, ask small model
        3. Return final verdict

        Args:
            query: The user query text.
            context: The cached context/response text.
            cached_at: Timestamp when context was cached (epoch).

        Returns:
            SufficiencyResult with verdict, confidence, and reason.
        """
        if not self._config.enabled:
            self._bypassed_count += 1
            return SufficiencyResult(
                verdict=SufficiencyVerdict.SUFFICIENT,
                confidence=1.0,
                reason="sufficiency check disabled",
            )

        result = _heuristic_evaluate(query, context, cached_at, self._config)

        if result.verdict == SufficiencyVerdict.INCONCLUSIVE:
            self._inconclusive_count += 1

            if self._config.enable_llm_pass:
                llm_result = await _llm_evaluate(
                    query, context, self._config.llm_timeout
                )
                if llm_result is not None:
                    self._llm_calls += 1
                    llm_result.keyword_coverage = result.keyword_coverage
                    llm_result.temporal_ok = result.temporal_ok
                    result = llm_result

        if result.verdict == SufficiencyVerdict.SUFFICIENT:
            self._sufficient_count += 1
        elif result.verdict == SufficiencyVerdict.INSUFFICIENT:
            self._insufficient_count += 1

        return result

    def get_stats(self) -> Dict[str, Any]:
        """Return evaluation metrics."""
        total = (
            self._sufficient_count
            + self._insufficient_count
            + self._inconclusive_count
            + self._bypassed_count
        )
        return {
            "enabled": self._config.enabled,
            "total_evaluations": total,
            "sufficient": self._sufficient_count,
            "insufficient": self._insufficient_count,
            "inconclusive": self._inconclusive_count,
            "bypassed": self._bypassed_count,
            "llm_calls": self._llm_calls,
            "keyword_threshold": self._config.keyword_threshold,
            "enable_llm_pass": self._config.enable_llm_pass,
        }

    def update_config(self, **kwargs) -> Dict[str, Any]:
        """Update evaluator config at runtime."""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        logger.info("Sufficiency config updated: %s", kwargs)
        return self.get_stats()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_instance: Optional[ContextSufficiencyEvaluator] = None


def get_context_sufficiency_evaluator() -> ContextSufficiencyEvaluator:
    """Get or create the global evaluator singleton."""
    global _instance
    if _instance is None:
        _instance = ContextSufficiencyEvaluator()
    return _instance
