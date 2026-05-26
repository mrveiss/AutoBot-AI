# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for expected_output_tokens factor in TaskComplexityScorer (GH #7353)."""


from llm_shared.tiered_routing.complexity_scorer import TaskComplexityScorer
from llm_shared.tiered_routing.tier_config import TierConfig


def _make_scorer():
    config = TierConfig()
    return TaskComplexityScorer(config)


def _messages(content: str) -> list:
    return [{"role": "user", "content": content}]


# ---------------------------------------------------------------------------
# _score_output_length — explicit expected_output_tokens hint
# ---------------------------------------------------------------------------


class TestScoreOutputLengthExplicit:
    def test_small_tokens_returns_zero(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=50) == 0.0

    def test_medium_tokens_returns_one(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=200) == 1.0

    def test_large_tokens_returns_two(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=1000) == 2.0

    def test_very_large_tokens_returns_three(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=2000) == 3.0

    def test_boundary_exactly_100_returns_one(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=100) == 1.0

    def test_boundary_exactly_500_returns_two(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=500) == 2.0

    def test_boundary_exactly_2000_returns_three(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=2000) == 3.0

    def test_zero_tokens_returns_zero(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=0) == 0.0


# ---------------------------------------------------------------------------
# _score_output_length — max_tokens fallback
# ---------------------------------------------------------------------------


class TestScoreOutputLengthMaxTokens:
    def test_small_max_tokens_returns_zero(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=None, max_tokens=50) == 0.0

    def test_large_max_tokens_returns_three(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=None, max_tokens=4096) == 3.0

    def test_medium_max_tokens_returns_two(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("anything", expected_output_tokens=None, max_tokens=800) == 2.0

    def test_explicit_overrides_max_tokens(self):
        """expected_output_tokens takes priority over max_tokens."""
        scorer = _make_scorer()
        # expected=50 (small) but max_tokens=4096 (large) — should return 0.0
        result = scorer._score_output_length("anything", expected_output_tokens=50, max_tokens=4096)
        assert result == 0.0

    def test_zero_max_tokens_falls_through_to_heuristic(self):
        """max_tokens=0 is treated as absent; heuristic runs instead."""
        scorer = _make_scorer()
        # No patterns in content → 0.0
        result = scorer._score_output_length("hello world", expected_output_tokens=None, max_tokens=0)
        assert result == 0.0


# ---------------------------------------------------------------------------
# _score_output_length — heuristic pattern fallback
# ---------------------------------------------------------------------------


class TestScoreOutputLengthHeuristic:
    def test_no_patterns_returns_zero(self):
        scorer = _make_scorer()
        assert scorer._score_output_length("Hello there", expected_output_tokens=None) == 0.0

    def test_summarize_pattern_bumps_score(self):
        scorer = _make_scorer()
        result = scorer._score_output_length("Please summarize this document", expected_output_tokens=None)
        assert result >= 1.0

    def test_list_all_pattern_bumps_score(self):
        scorer = _make_scorer()
        result = scorer._score_output_length("List all the options available", expected_output_tokens=None)
        assert result >= 1.0

    def test_step_by_step_pattern_bumps_score(self):
        scorer = _make_scorer()
        result = scorer._score_output_length("Explain it step-by-step", expected_output_tokens=None)
        assert result >= 1.0

    def test_multiple_patterns_capped_at_three(self):
        scorer = _make_scorer()
        # Triggers summarize, list all, step-by-step, enumerate all — should cap at 3.0
        content = "summarize and list all items step-by-step and enumerate all details"
        result = scorer._score_output_length(content, expected_output_tokens=None)
        assert result == 3.0

    def test_write_full_pattern(self):
        scorer = _make_scorer()
        result = scorer._score_output_length("Write a full implementation", expected_output_tokens=None)
        assert result >= 1.0

    def test_generate_complete_pattern(self):
        scorer = _make_scorer()
        result = scorer._score_output_length("Generate a complete report", expected_output_tokens=None)
        assert result >= 1.0

    def test_summarise_british_spelling(self):
        scorer = _make_scorer()
        result = scorer._score_output_length("Please summarise the chapter", expected_output_tokens=None)
        assert result >= 1.0


# ---------------------------------------------------------------------------
# score() integration — output_length factor included in result
# ---------------------------------------------------------------------------


class TestScoreIntegration:
    def test_score_includes_output_length_factor(self):
        scorer = _make_scorer()
        result = scorer.score(_messages("Hello"), expected_output_tokens=1500)
        assert "output_length" in result.factors
        assert result.factors["output_length"] == 2.0

    def test_score_backwards_compat_no_new_args(self):
        """Calling score() without expected_output_tokens must still work."""
        scorer = _make_scorer()
        result = scorer.score(_messages("Hello"))
        assert result.score >= 0.0
        assert result.tier in ("simple", "complex")
        assert "output_length" in result.factors

    def test_large_output_hint_bumps_simple_to_complex(self):
        """A request that would be simple gains enough score to become complex
        when expected_output_tokens signals a long decode."""
        scorer = _make_scorer()

        simple_result = scorer.score(_messages("Hello"), expected_output_tokens=50)
        complex_result = scorer.score(_messages("Hello"), expected_output_tokens=3000)

        assert complex_result.score > simple_result.score
        # With output_length=3.0 contributing 0.10 weight, the score delta is:
        # (3.0 * 0.10 / 3.0) * 10 = 1.0 point — verify it moved
        assert complex_result.factors["output_length"] == 3.0
        assert simple_result.factors["output_length"] == 0.0

    def test_max_tokens_in_message_is_extracted(self):
        """max_tokens key inside a message dict is picked up as fallback."""
        scorer = _make_scorer()
        messages = [{"role": "user", "content": "Explain everything", "max_tokens": 2500}]
        result = scorer.score(messages)
        assert result.factors["output_length"] == 3.0

    def test_output_length_in_reasoning_when_dominant(self):
        """When output_length factor is dominant it appears in reasoning text."""
        scorer = _make_scorer()
        # All other inputs minimal; output_length = 3.0 → dominant
        result = scorer.score(_messages("Hi"), expected_output_tokens=3000)
        assert "output length" in result.reasoning

    def test_heuristic_bumps_score_via_score_method(self):
        """step-by-step content should raise output_length factor via heuristic."""
        scorer = _make_scorer()
        result = scorer.score(_messages("Explain step-by-step how to do this"))
        assert result.factors["output_length"] >= 1.0

    def test_existing_factors_still_present(self):
        """All pre-existing factors remain in the result."""
        scorer = _make_scorer()
        result = scorer.score(_messages("Hello"))
        for factor in ("length", "code", "technical", "multistep", "question", "output_length"):
            assert factor in result.factors
