# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for context-based KB document suggestions (Issue #3284).

Covers:
- _compute_recency_score: exponential decay, missing timestamp, invalid input
- _build_snippet: truncation at word boundary, short content passthrough
- _extract_title: metadata priority, line fallback
- suggest_by_context: combined scoring, filtering, ranking, error path
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from knowledge.suggestions import SuggestionsMixin

# ---------------------------------------------------------------------------
# Minimal concrete subclass so we can instantiate SuggestionsMixin
# ---------------------------------------------------------------------------


class _FakeSuggestions(SuggestionsMixin):
    def ensure_initialized(self) -> None:
        pass  # no-op for unit tests


@pytest.fixture()
def mixin() -> _FakeSuggestions:
    return _FakeSuggestions()


# ---------------------------------------------------------------------------
# _compute_recency_score
# ---------------------------------------------------------------------------


class TestComputeRecencyScore:
    def test_today_scores_one(self, mixin):
        now_str = datetime.now(tz=timezone.utc).isoformat()
        score = mixin._compute_recency_score(now_str)
        assert 0.98 <= score <= 1.0

    def test_half_life_is_thirty_days(self, mixin):
        ts = (datetime.now(tz=timezone.utc) - timedelta(days=30)).isoformat()
        score = mixin._compute_recency_score(ts)
        assert 0.48 <= score <= 0.52  # ~0.5

    def test_empty_timestamp_returns_neutral(self, mixin):
        assert mixin._compute_recency_score("") == 0.5

    def test_invalid_timestamp_returns_neutral(self, mixin):
        assert mixin._compute_recency_score("not-a-date") == 0.5

    def test_naive_timestamp_handled(self, mixin):
        # Naive datetime (no tz) should not raise
        naive = datetime.utcnow().isoformat()
        score = mixin._compute_recency_score(naive)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# _build_snippet
# ---------------------------------------------------------------------------


class TestBuildSnippet:
    def test_short_content_returned_as_is(self, mixin):
        text = "Short text."
        assert mixin._build_snippet(text, 200) == "Short text."

    def test_long_content_truncated(self, mixin):
        text = " ".join(["word"] * 100)  # 499 chars
        snippet = mixin._build_snippet(text, 50)
        assert len(snippet) <= 50 + len(mixin._SNIPPET_ELLIPSIS)
        assert snippet.endswith(mixin._SNIPPET_ELLIPSIS)

    def test_truncation_at_word_boundary(self, mixin):
        # With limit=14, text[:14] = "hello world fo", rsplit splits at space -> "hello world"
        text = "hello world foobar"
        snippet = mixin._build_snippet(text, 14)
        assert snippet == "hello world" + mixin._SNIPPET_ELLIPSIS

    def test_empty_content(self, mixin):
        assert mixin._build_snippet("", 200) == ""


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------


class TestExtractTitle:
    def test_title_from_metadata(self, mixin):
        title = mixin._extract_title("some content", {"title": "My Title"})
        assert title == "My Title"

    def test_source_fallback(self, mixin):
        title = mixin._extract_title("some content", {"source": "docs/guide.md"})
        assert title == "docs/guide.md"

    def test_first_line_fallback(self, mixin):
        title = mixin._extract_title("First line\nSecond line", {})
        assert title == "First line"

    def test_empty_content_fallback(self, mixin):
        title = mixin._extract_title("", {})
        assert title == "Untitled"


# ---------------------------------------------------------------------------
# suggest_by_context
# ---------------------------------------------------------------------------


def _make_doc(
    fact_id: str,
    score: float,
    content: str,
    timestamp: str = "",
    tags: List[str] = None,
    category: str = "",
) -> Dict[str, Any]:
    return {
        "score": score,
        "content": content,
        "node_id": fact_id,
        "metadata": {
            "fact_id": fact_id,
            "timestamp": timestamp,
            "tags": tags or [],
            "category": category,
        },
    }


@pytest.mark.asyncio
class TestSuggestByContext:
    async def test_returns_ranked_suggestions(self, mixin):
        now = datetime.now(tz=timezone.utc).isoformat()
        old = (datetime.now(tz=timezone.utc) - timedelta(days=120)).isoformat()

        docs = [
            _make_doc("fact1", score=0.9, content="Redis pooling guide detailed text here", timestamp=old),
            _make_doc("fact2", score=0.7, content="FastAPI async patterns best practices", timestamp=now),
        ]
        mixin._find_similar_documents = AsyncMock(return_value=docs)

        result = await mixin.suggest_by_context(context="Redis FastAPI", limit=5, recency_weight=0.2, min_score=0.3)

        assert result["success"] is True
        assert len(result["suggestions"]) == 2
        # Verify sorted descending by combined_score
        scores = [s["combined_score"] for s in result["suggestions"]]
        assert scores == sorted(scores, reverse=True)

    async def test_filters_below_min_score(self, mixin):
        docs = [
            _make_doc("fact1", score=0.1, content="Low relevance doc"),
        ]
        mixin._find_similar_documents = AsyncMock(return_value=docs)

        result = await mixin.suggest_by_context(context="anything", min_score=0.9)

        assert result["success"] is True
        assert result["suggestions"] == []

    async def test_respects_limit(self, mixin):
        now = datetime.now(tz=timezone.utc).isoformat()
        docs = [_make_doc(f"fact{i}", score=0.8, content=f"Content {i}", timestamp=now) for i in range(10)]
        mixin._find_similar_documents = AsyncMock(return_value=docs)

        result = await mixin.suggest_by_context(context="test", limit=3)

        assert result["success"] is True
        assert len(result["suggestions"]) == 3

    async def test_suggestion_shape(self, mixin):
        now = datetime.now(tz=timezone.utc).isoformat()
        docs = [
            _make_doc(
                "fact99",
                score=0.75,
                content="This is content for a test document about Python.",
                timestamp=now,
                tags=["python", "test"],
                category="tech/python",
            )
        ]
        mixin._find_similar_documents = AsyncMock(return_value=docs)

        result = await mixin.suggest_by_context(context="Python testing")

        s = result["suggestions"][0]
        assert s["fact_id"] == "fact99"
        assert isinstance(s["title"], str) and s["title"]
        assert isinstance(s["snippet"], str)
        assert 0.0 <= s["relevance_score"] <= 1.0
        assert 0.0 <= s["recency_score"] <= 1.0
        assert 0.0 <= s["combined_score"] <= 1.0
        assert s["tags"] == ["python", "test"]
        assert s["category"] == "tech/python"
        assert s["created_at"] == now

    async def test_empty_context_returns_error(self, mixin):
        result = await mixin.suggest_by_context(context="  ")
        assert result["success"] is False
        assert "error" in result

    async def test_snippet_length_respected(self, mixin):
        long_content = "word " * 200  # 1000 chars
        now = datetime.now(tz=timezone.utc).isoformat()
        docs = [_make_doc("fact1", score=0.8, content=long_content, timestamp=now)]
        mixin._find_similar_documents = AsyncMock(return_value=docs)

        result = await mixin.suggest_by_context(context="test", snippet_length=100)

        snippet = result["suggestions"][0]["snippet"]
        assert len(snippet) <= 100 + len(mixin._SNIPPET_ELLIPSIS)

    async def test_search_exception_returns_error(self, mixin):
        mixin._find_similar_documents = AsyncMock(side_effect=RuntimeError("DB error"))

        result = await mixin.suggest_by_context(context="test query")

        assert result["success"] is False
        assert "error" in result

    async def test_total_candidates_reported(self, mixin):
        now = datetime.now(tz=timezone.utc).isoformat()
        docs = [_make_doc(f"fact{i}", score=0.8, content=f"Content {i}", timestamp=now) for i in range(7)]
        mixin._find_similar_documents = AsyncMock(return_value=docs)

        result = await mixin.suggest_by_context(context="test")

        assert result["total_candidates"] == 7

    async def test_json_encoded_tags_parsed(self, mixin):
        now = datetime.now(tz=timezone.utc).isoformat()
        doc = {
            "score": 0.8,
            "content": "Content with JSON tags",
            "node_id": "fact1",
            "metadata": {
                "fact_id": "fact1",
                "timestamp": now,
                "tags": '["redis", "fastapi"]',
                "category": "",
            },
        }
        mixin._find_similar_documents = AsyncMock(return_value=[doc])

        result = await mixin.suggest_by_context(context="redis fastapi")

        assert result["suggestions"][0]["tags"] == ["redis", "fastapi"]
