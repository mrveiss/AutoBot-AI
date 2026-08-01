# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services.research.extractor (#12622).

Covers the happy path, the anti-hallucination overlap guard, and the
failure paths (LLM error, malformed JSON).
"""

from unittest.mock import AsyncMock

from services.research.extractor import extract_claims

_SOURCE_TEXT = (
    "The Eiffel Tower was completed in 1889 for the World's Fair in Paris. "
    "It stands 330 meters tall and was designed by engineer Gustave Eiffel."
)


def _mock_llm(content: str, error: str = "") -> AsyncMock:
    llm = AsyncMock()
    response = AsyncMock()
    response.content = content
    response.error = error
    llm.chat = AsyncMock(return_value=response)
    return llm


class TestExtractClaims:
    """Happy path + anti-hallucination guard."""

    async def test_supported_claim_is_kept(self):
        """A claim whose wording overlaps the source text is kept."""
        llm = _mock_llm('{"claims": [{"content": "The Eiffel Tower was completed in 1889.", "confidence": 0.9}]}')

        claims = await extract_claims(llm, _SOURCE_TEXT, "https://example.com/eiffel", "doc-1", 8000)

        assert len(claims) == 1
        assert claims[0].confidence == 0.9
        assert claims[0].source_url == "https://example.com/eiffel"
        assert claims[0].source_doc_id == "doc-1"

    async def test_unsupported_claim_is_dropped(self):
        """A claim with no wording overlap with the source is rejected (anti-hallucination)."""
        llm = _mock_llm('{"claims": [{"content": "Bananas grow best in tropical climates.", "confidence": 0.9}]}')

        claims = await extract_claims(llm, _SOURCE_TEXT, "https://example.com/eiffel", "doc-1", 8000)

        assert claims == []

    async def test_confidence_is_clamped(self):
        """An out-of-range confidence value is clamped to [0, 1]."""
        llm = _mock_llm('{"claims": [{"content": "The Eiffel Tower stands 330 meters tall.", "confidence": 5.0}]}')

        claims = await extract_claims(llm, _SOURCE_TEXT, "https://example.com/eiffel", "doc-1", 8000)

        assert claims[0].confidence == 1.0

    async def test_content_truncated_to_budget(self):
        """Only the first max_content_chars of the page are sent to the LLM."""
        llm = _mock_llm('{"claims": []}')
        long_text = "word " * 5000

        await extract_claims(llm, long_text, "https://example.com/x", "doc-2", 100)

        sent_content = llm.chat.await_args.kwargs["messages"][1]["content"]
        assert len(sent_content) == 100


class TestExtractClaimsFailurePaths:
    """LLM failure and malformed-JSON paths must degrade to an empty list."""

    async def test_llm_error_returns_empty(self):
        """A non-empty response.error short-circuits to no claims."""
        llm = _mock_llm("", error="model unavailable")

        claims = await extract_claims(llm, _SOURCE_TEXT, "https://example.com/x", "doc-1", 8000)

        assert claims == []

    async def test_malformed_json_returns_empty(self):
        """Non-JSON LLM output degrades to no claims instead of raising."""
        llm = _mock_llm("this is not json at all")

        claims = await extract_claims(llm, _SOURCE_TEXT, "https://example.com/x", "doc-1", 8000)

        assert claims == []

    async def test_empty_claim_content_is_skipped(self):
        """A claim dict with empty/missing content is dropped, not crashed on."""
        llm = _mock_llm('{"claims": [{"content": "", "confidence": 0.5}, {"confidence": 0.5}]}')

        claims = await extract_claims(llm, _SOURCE_TEXT, "https://example.com/x", "doc-1", 8000)

        assert claims == []
