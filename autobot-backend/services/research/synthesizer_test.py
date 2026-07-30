# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services.research.synthesizer (#12622).

Covers grounded synthesis, the anti-hallucinated-citation post-check, and
the no-facts / all-facts-failed caveat paths.
"""

from unittest.mock import AsyncMock

from services.research.models import StoredFact
from services.research.synthesizer import synthesize_answer


def _fact(fact_id: str, content: str) -> StoredFact:
    return StoredFact(
        fact_id=fact_id,
        content=content,
        confidence=0.7,
        source_url=f"https://example.com/{fact_id}",
        source_doc_id=f"doc-{fact_id}",
        is_new=True,
    )


def _mock_llm(content: str, error: str = "") -> AsyncMock:
    llm = AsyncMock()
    response = AsyncMock()
    response.content = content
    response.error = error
    llm.chat = AsyncMock(return_value=response)
    return llm


class TestSynthesizeAnswer:
    """Grounded synthesis + anti-hallucinated-citation post-check."""

    async def test_valid_marker_produces_citation(self):
        """A [F1] marker referencing a real fact survives and is cited."""
        facts = [_fact("abc", "The sky is blue.")]
        llm = _mock_llm('{"answer": "The sky is blue [F1].", "confidence": 0.8}')

        result = await synthesize_answer(llm, "What color is the sky?", facts)

        assert result.answer == "The sky is blue [F1]."
        assert len(result.citations) == 1
        assert result.citations[0].fact_id == "abc"
        assert result.confidence == 0.8

    async def test_out_of_range_marker_is_stripped(self):
        """A [F<n>] marker with no matching fact is stripped, not trusted."""
        facts = [_fact("abc", "The sky is blue.")]
        llm = _mock_llm('{"answer": "The sky is blue [F1]. Grass is green [F2].", "confidence": 0.9}')

        result = await synthesize_answer(llm, "Tell me about colors", facts)

        assert "[F2]" not in result.answer
        assert "[F1]" in result.answer
        assert len(result.citations) == 1

    async def test_no_valid_citations_returns_caveat(self):
        """An answer with zero surviving citations is replaced with a caveat."""
        facts = [_fact("abc", "The sky is blue.")]
        llm = _mock_llm('{"answer": "Grass is green [F9].", "confidence": 0.9}')

        result = await synthesize_answer(llm, "What color is grass?", facts)

        assert result.citations == []
        assert result.confidence == 0.0
        assert "verification" in result.answer.lower()

    async def test_no_facts_returns_caveat_without_llm_call(self):
        """Zero facts short-circuits to a caveat and never calls the LLM."""
        llm = _mock_llm("")

        result = await synthesize_answer(llm, "unanswerable question", [])

        assert result.citations == []
        assert result.confidence == 0.0
        llm.chat.assert_not_awaited()

    async def test_llm_error_returns_caveat(self):
        """An LLM error degrades to a caveat instead of raising."""
        facts = [_fact("abc", "The sky is blue.")]
        llm = _mock_llm("", error="timeout")

        result = await synthesize_answer(llm, "What color is the sky?", facts)

        assert result.citations == []
        assert result.confidence == 0.0

    async def test_confidence_is_clamped(self):
        """An out-of-range confidence value from the LLM is clamped to [0, 1]."""
        facts = [_fact("abc", "The sky is blue.")]
        llm = _mock_llm('{"answer": "The sky is blue [F1].", "confidence": 42}')

        result = await synthesize_answer(llm, "What color is the sky?", facts)

        assert result.confidence == 1.0
