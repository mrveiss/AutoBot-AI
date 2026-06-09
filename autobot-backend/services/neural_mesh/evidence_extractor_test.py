# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for EvidenceExtractor (#2135).

All external dependencies are replaced with AsyncMock so the tests run
without a database, Redis, or model server.
"""

from unittest.mock import AsyncMock

import pytest

from services.neural_mesh.evidence_extractor import Evidence, EvidenceExtractor

# =============================================================================
# Factories
# =============================================================================


def _make_chunk(content: str, chunk_id: str, use_metadata: bool = False) -> dict:
    """Return a minimal chunk dict.

    Args:
        content:       Chunk text.
        chunk_id:      Identifier for the chunk.
        use_metadata:  When True, place chunk_id under 'metadata' key instead
                       of at the top level, exercising the fallback path.
    """
    if use_metadata:
        return {"content": content, "metadata": {"chunk_id": chunk_id}}
    return {"content": content, "chunk_id": chunk_id}


def _make_reranker(scores: list[float]) -> AsyncMock:
    """Return a mock reranker whose predict() returns *scores*.

    Args:
        scores: Raw logit values, one per (query, sentence) pair.
    """
    reranker = AsyncMock()
    reranker.predict = AsyncMock(return_value=scores)
    return reranker


def _make_extractor(scores: list[float], max_evidence: int = 15) -> EvidenceExtractor:
    """Construct an EvidenceExtractor with a mock reranker.

    Args:
        scores:       Logit scores returned by the mock reranker.
        max_evidence: Passed through to EvidenceExtractor.
    """
    return EvidenceExtractor(reranker=_make_reranker(scores), max_evidence=max_evidence)


# =============================================================================
# Core extract() behaviour
# =============================================================================


class TestExtractReturnsEvidenceObjects:
    """extract() returns Evidence dataclass instances."""

    @pytest.mark.asyncio
    async def test_extract_returns_evidence_objects(self) -> None:
        """Each returned item must be an Evidence with text, source_chunk_id,
        and relevance."""
        chunk = _make_chunk("The sky is blue. Stars shine at night.", "c1")
        extractor = _make_extractor(scores=[0.5, 1.2])

        results = await extractor.extract("sky colour", [chunk])

        assert len(results) == 2
        for ev in results:
            assert isinstance(ev, Evidence)
            assert isinstance(ev.text, str) and ev.text
            assert isinstance(ev.source_chunk_id, str)
            assert 0.0 <= ev.relevance <= 1.0


class TestExtractSplitsIntoSentences:
    """extract() splits multi-sentence chunks into individual Evidence items."""

    @pytest.mark.asyncio
    async def test_extract_splits_into_sentences(self) -> None:
        """A chunk with three sentences must produce three Evidence objects."""
        chunk = _make_chunk("Redis is fast. It uses memory. Data expires automatically.", "c2")
        extractor = _make_extractor(scores=[0.9, 0.3, 0.6])

        results = await extractor.extract("redis speed", [chunk])

        assert len(results) == 3
        texts = {ev.text for ev in results}
        assert "Redis is fast." in texts
        assert "It uses memory." in texts
        assert "Data expires automatically." in texts


class TestExtractLimitsToMaxEvidence:
    """extract() returns at most max_evidence items."""

    @pytest.mark.asyncio
    async def test_extract_limits_to_max_evidence(self) -> None:
        """With 20 sentences and max_evidence=5 exactly 5 items are returned."""
        sentences = [f"Sentence number {i}." for i in range(20)]
        content = " ".join(sentences)
        chunk = _make_chunk(content, "c3")
        scores = [float(i) / 20.0 for i in range(20)]
        extractor = _make_extractor(scores=scores, max_evidence=5)

        results = await extractor.extract("query", [chunk])

        assert len(results) == 5


class TestExtractSkipsTinyFragments:
    """extract() skips sentence fragments of 10 characters or fewer."""

    @pytest.mark.asyncio
    async def test_extract_skips_tiny_fragments(self) -> None:
        """Fragments with 10 or fewer characters must not appear in results."""
        chunk = _make_chunk("Hi. This is a longer sentence that should pass.", "c4")
        # 'Hi.' has 3 chars — must be skipped; second sentence has 47 chars
        extractor = _make_extractor(scores=[0.8])

        results = await extractor.extract("greeting", [chunk])

        assert len(results) == 1
        assert results[0].text == "This is a longer sentence that should pass."


class TestExtractEmptyChunksReturnsEmpty:
    """extract() returns an empty list when no chunks are provided."""

    @pytest.mark.asyncio
    async def test_extract_empty_chunks_returns_empty(self) -> None:
        """An empty chunks list must return an empty list without calling predict."""
        reranker = AsyncMock()
        reranker.predict = AsyncMock()
        extractor = EvidenceExtractor(reranker=reranker, max_evidence=15)

        results = await extractor.extract("query", [])

        assert results == []
        reranker.predict.assert_not_called()


class TestExtractPreservesSourceAttribution:
    """Each Evidence carries the chunk_id of the chunk it came from."""

    @pytest.mark.asyncio
    async def test_extract_preserves_source_attribution(self) -> None:
        """Sentences from chunk_a must reference chunk_a; same for chunk_b."""
        chunk_a = _make_chunk("Alpha sentence one. Alpha sentence two.", "chunk_a")
        chunk_b = _make_chunk("Beta sentence one. Beta sentence two.", "chunk_b")
        extractor = _make_extractor(scores=[0.9, 0.8, 0.7, 0.6])

        results = await extractor.extract("alpha beta", [chunk_a, chunk_b])

        by_id = {ev.text: ev.source_chunk_id for ev in results}
        assert by_id["Alpha sentence one."] == "chunk_a"
        assert by_id["Alpha sentence two."] == "chunk_a"
        assert by_id["Beta sentence one."] == "chunk_b"
        assert by_id["Beta sentence two."] == "chunk_b"

    @pytest.mark.asyncio
    async def test_extract_preserves_source_attribution_metadata_key(self) -> None:
        """chunk_id nested under 'metadata' must be resolved correctly."""
        chunk = _make_chunk("One sentence here.", "meta_chunk", use_metadata=True)
        extractor = _make_extractor(scores=[0.5])

        results = await extractor.extract("query", [chunk])

        assert results[0].source_chunk_id == "meta_chunk"


# =============================================================================
# _split_sentences
# =============================================================================


class TestSplitSentences:
    """_split_sentences() handles all terminal punctuation types."""

    def test_split_sentences_handles_multiple_delimiters(self) -> None:
        """Period, question mark, and exclamation mark all act as delimiters."""
        extractor = EvidenceExtractor(reranker=AsyncMock(), max_evidence=15)
        text = "Is this a question? Yes it is! And this is a statement."

        parts = extractor._split_sentences(text)

        assert "Is this a question?" in parts
        assert "Yes it is!" in parts
        assert "And this is a statement." in parts
        assert len(parts) == 3

    def test_split_sentences_single_sentence_no_split(self) -> None:
        """A single sentence without trailing whitespace is returned as-is."""
        extractor = EvidenceExtractor(reranker=AsyncMock(), max_evidence=15)

        parts = extractor._split_sentences("Only one sentence.")

        assert parts == ["Only one sentence."]

    def test_split_sentences_empty_string_returns_empty(self) -> None:
        """An empty string yields an empty list."""
        extractor = EvidenceExtractor(reranker=AsyncMock(), max_evidence=15)

        parts = extractor._split_sentences("")

        assert parts == []

    def test_split_does_not_break_on_dr(self) -> None:
        """'Dr. Smith is here.' must not be split into two fragments (#2170)."""
        extractor = EvidenceExtractor(reranker=AsyncMock(), max_evidence=15)

        parts = extractor._split_sentences("Dr. Smith is here.")

        assert parts == ["Dr. Smith is here."]

    def test_split_does_not_break_on_eg(self) -> None:
        """'e.g. this example is valid.' must remain as one sentence (#2170)."""
        extractor = EvidenceExtractor(reranker=AsyncMock(), max_evidence=15)

        parts = extractor._split_sentences("e.g. this example is valid.")

        assert parts == ["e.g. this example is valid."]

    def test_split_does_not_break_on_us(self) -> None:
        """'U.S. is a country.' must not be split after the abbreviation (#2170)."""
        extractor = EvidenceExtractor(reranker=AsyncMock(), max_evidence=15)

        parts = extractor._split_sentences("U.S. is a country.")

        assert parts == ["U.S. is a country."]

    def test_split_still_breaks_on_real_sentence_end(self) -> None:
        """Two genuine sentences still split correctly even with fix applied (#2170)."""
        extractor = EvidenceExtractor(reranker=AsyncMock(), max_evidence=15)

        parts = extractor._split_sentences("First sentence. Second sentence.")

        assert parts == ["First sentence.", "Second sentence."]


# =============================================================================
# Relevance ordering
# =============================================================================


class TestScoredSentencesSortedByRelevance:
    """extract() returns Evidence objects sorted by descending relevance."""

    @pytest.mark.asyncio
    async def test_scored_sentences_sorted_by_relevance(self) -> None:
        """The item with the highest raw logit must appear first."""
        chunk = _make_chunk("Low relevance sentence. High relevance sentence. Medium sentence.", "c5")
        # logits: low=0.1, high=5.0, medium=1.5 — after sigmoid: high > medium > low
        extractor = _make_extractor(scores=[0.1, 5.0, 1.5])

        results = await extractor.extract("high relevance", [chunk])

        assert results[0].text == "High relevance sentence."
        assert results[1].text == "Medium sentence."
        assert results[2].text == "Low relevance sentence."
        assert results[0].relevance > results[1].relevance > results[2].relevance

    @pytest.mark.asyncio
    async def test_relevance_values_are_sigmoid_normalised(self) -> None:
        """Relevance values must be in the 0-1 range (sigmoid of logits)."""
        chunk = _make_chunk("First sentence. Second sentence.", "c6")
        extractor = _make_extractor(scores=[-10.0, 10.0])

        results = await extractor.extract("query", [chunk])

        for ev in results:
            assert 0.0 < ev.relevance < 1.0
        # Highest logit (10.0) must map to relevance close to 1
        high_rel = max(ev.relevance for ev in results)
        assert high_rel > 0.99
