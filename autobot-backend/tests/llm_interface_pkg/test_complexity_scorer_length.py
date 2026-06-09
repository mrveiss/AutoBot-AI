# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for token-aware _score_length in TaskComplexityScorer (GH #7348)."""

from llm_shared.tiered_routing.complexity_scorer import TaskComplexityScorer
from llm_shared.tiered_routing.tier_config import TierConfig


def _make_scorer(tokenizer=None):
    config = TierConfig()
    return TaskComplexityScorer(config, tokenizer=tokenizer)


def test_default_fallback_uses_char_div_4():
    scorer = _make_scorer()
    # 400 chars -> 100 tokens -> score 1.0 (between 25 and 125)
    content = "a" * 400
    assert scorer._score_length(content) == 1.0


def test_custom_tokenizer_is_used():
    call_count = {"n": 0}

    def counting_tokenizer(text: str) -> int:
        call_count["n"] += 1
        return len(text.split())  # word count as fake tokenizer

    scorer = _make_scorer(tokenizer=counting_tokenizer)
    content = " ".join(["word"] * 30)  # 30 words -> score 1.0 (25-125 range)
    result = scorer._score_length(content)
    assert call_count["n"] == 1
    assert result == 1.0


def test_code_scores_higher_than_char_count_suggests():
    """CJK / dense content: 1 char ≈ 1 token, so char/4 underestimates."""

    # 500 CJK chars = ~500 tokens; char/4 = 125 tokens -> score 2.0 (125-250 range)
    # With actual tokenizer returning 500 -> score 3.0
    def cjk_tokenizer(text: str) -> int:
        return len(text)  # 1 char = 1 token for CJK

    scorer_with = _make_scorer(tokenizer=cjk_tokenizer)
    scorer_without = _make_scorer()

    content = "字" * 500
    score_with = scorer_with._score_length(content)
    score_without = scorer_without._score_length(content)

    assert score_with == 3.0  # 500 tokens > 250 threshold
    assert score_without == 2.0  # 500//4=125 tokens, boundary case


def test_no_behavior_change_for_callers_without_tokenizer():
    scorer = _make_scorer()
    assert scorer._score_length("hi") == 0.0  # 2//4=0 < 25
    assert scorer._score_length("a" * 100) == 1.0  # 100//4=25, boundary
    assert scorer._score_length("a" * 500) == 2.0  # 500//4=125, boundary
    assert scorer._score_length("a" * 1000) == 3.0  # 1000//4=250, boundary


def test_score_method_still_works_end_to_end():
    scorer = _make_scorer()
    messages = [{"role": "user", "content": "Hello"}]
    result = scorer.score(messages)
    assert result.score >= 0
    assert result.tier in ("simple", "complex")
