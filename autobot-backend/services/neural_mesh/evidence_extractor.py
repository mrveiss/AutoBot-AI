# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Sentence-level evidence extraction for Neural Mesh RAG (#2135).

Instead of including whole chunks (~400 tokens each), EvidenceExtractor
uses the cross-encoder to score individual sentences and returns only the
most relevant ones (~50 tokens each), reducing context window consumption.
"""

import math
import re
from dataclasses import dataclass
from typing import Protocol

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


# =============================================================================
# Protocol — duck-typed for testability
# =============================================================================


class _Reranker(Protocol):
    """Minimal protocol for cross-encoder scoring used by _score_sentences."""

    async def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Score (query, text) pairs and return a list of raw logits."""
        ...


# =============================================================================
# Result type
# =============================================================================


@dataclass
class Evidence:
    """A single relevant sentence extracted from a retrieved chunk.

    Attributes:
        text:            The sentence text.
        source_chunk_id: ID of the chunk this sentence came from.
        relevance:       Sigmoid-normalised cross-encoder score (0-1).
    """

    text: str
    source_chunk_id: str
    relevance: float


# Negative-lookbehind anchors that prevent splitting after common abbreviations.
# Each alternative is a fixed-width lookbehind (Python requires this).
# Referenced by EvidenceExtractor._split_sentences (#2170).
_ABBREVS = (
    r"(?<!Dr\.)"
    r"(?<!Mr\.)"
    r"(?<!Ms\.)"
    r"(?<!Mrs\.)"
    r"(?<!St\.)"
    r"(?<!vs\.)"
    r"(?<!e\.g\.)"
    r"(?<!i\.e\.)"
    r"(?<!U\.S\.)"
)

# =============================================================================
# Extractor
# =============================================================================


class EvidenceExtractor:
    """Extracts sentence-level evidence from retrieved chunks (#2135).

    Instead of including whole chunks (~400 tokens each), extract the
    most relevant sentences (~50 tokens each) using the cross-encoder.

    All dependencies are injected so the class can be fully unit-tested
    without a running model server.
    """

    def __init__(self, reranker: _Reranker, max_evidence: int = 15) -> None:
        """Inject dependencies.

        Args:
            reranker:     Object with an async predict(pairs) method that
                          returns raw cross-encoder logits.
            max_evidence: Maximum number of Evidence objects to return.
        """
        self.reranker = reranker
        self.max_evidence = max_evidence

    async def extract(self, query: str, chunks: list[dict]) -> list[Evidence]:
        """Extract the most relevant sentences from retrieved chunks.

        Args:
            query:  Raw user query string.
            chunks: List of chunk dicts with 'content' and either
                    'chunk_id' or 'metadata.chunk_id' fields.

        Returns:
            Up to max_evidence Evidence objects sorted by descending relevance.
        """
        sentences = self._collect_sentences(chunks)
        if not sentences:
            return []

        scored = await self._score_sentences(query, sentences)
        scored.sort(key=lambda x: x[2], reverse=True)
        return [
            Evidence(text=text, source_chunk_id=cid, relevance=score)
            for text, cid, score in scored[: self.max_evidence]
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _collect_sentences(self, chunks: list[dict]) -> list[tuple[str, str]]:
        """Return (sentence, chunk_id) pairs from all chunks.

        Skips sentence fragments of 10 characters or fewer.

        Args:
            chunks: Chunk dicts as described in extract().

        Returns:
            List of (sentence_text, chunk_id) tuples.
        """
        sentences: list[tuple[str, str]] = []
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id") or chunk.get("metadata", {}).get("chunk_id", "")
            content = chunk.get("content", "")
            for sent in self._split_sentences(content):
                stripped = sent.strip()
                if len(stripped) > 10:
                    sentences.append((stripped, chunk_id))
        return sentences

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences on terminal punctuation.

        Splits on a period, question mark, or exclamation mark followed by
        whitespace, but NOT after common abbreviations such as Dr., Mr., Ms.,
        Mrs., St., vs., e.g., i.e., or U.S. (#2170).

        Args:
            text: Raw paragraph or chunk content.

        Returns:
            List of sentence strings with leading/trailing whitespace stripped.
        """
        pattern = _ABBREVS + r"(?<=[.!?])\s+"
        return [s.strip() for s in re.split(pattern, text) if s.strip()]

    async def _score_sentences(self, query: str, sentences: list[tuple[str, str]]) -> list[tuple[str, str, float]]:
        """Score each sentence against the query with the cross-encoder.

        Applies sigmoid normalisation so raw logits become 0-1 relevance
        scores, consistent with the rest of the reranking pipeline.

        Args:
            query:     Raw user query string.
            sentences: List of (sentence_text, chunk_id) tuples.

        Returns:
            List of (sentence_text, chunk_id, relevance) triples.
        """
        pairs = [(query, sent) for sent, _ in sentences]
        raw_scores = await self.reranker.predict(pairs)
        return [
            (
                sentences[i][0],
                sentences[i][1],
                1.0 / (1.0 + math.exp(-float(raw_scores[i]))),
            )
            for i in range(len(sentences))
        ]
