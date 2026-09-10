# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The summary evaluator must see more than the opening of its source (#16110).

``source_preview = text[:200]`` scored a summary of up to ``document_max_words``
(300) against the **first 200 characters** of its input. Any fact dropped from
past that point was invisible to the check, and the refinement loop iterated
against the same blind score.

**That is worse than having no evaluator.** A missing check is visible; a check
that cannot fail returns a confident ``quality_score`` that reads as evidence of
fidelity, and ``best_score`` then selects a "best" summary on that basis.

The tests below are written against the boundary rather than the implementation:
a fact placed where the old code could not see it must now be visible, and the
score must not be presented as a fidelity measure when the source was sampled.
"""

from __future__ import annotations

import pytest

from knowledge.pipeline.cognifiers.recursive_summarizer import (
    _EVAL_SOURCE_BUDGET,
    _PARTIAL_SOURCE_NOTE,
    build_eval_excerpt,
    coverage_percent,
)


class TestAFactPastTheOldBoundaryIsVisible:
    """The regression, expressed as the defect rather than as the fix."""

    def test_a_fact_at_character_500_reaches_the_evaluator(self) -> None:
        """The exact case `text[:200]` could not see."""
        text = "A" * 500 + " THE-LOAD-BEARING-FACT " + "B" * 500
        excerpt, coverage = build_eval_excerpt(text)
        assert "THE-LOAD-BEARING-FACT" in excerpt
        assert coverage == 1.0, "a 1kB document fits the budget whole; nothing should be sampled"

    def test_the_old_truncation_would_have_missed_it(self) -> None:
        """The contrast. Without this the test above proves nothing about the bug.

        A guard that passes on the fixed code and would also have passed on the
        broken code is not a regression test.
        """
        text = "A" * 500 + " THE-LOAD-BEARING-FACT " + "B" * 500
        assert "THE-LOAD-BEARING-FACT" not in text[:200]

    def test_a_fact_at_the_very_end_of_an_oversized_document_is_visible(self) -> None:
        """Head-only truncation of ANY length loses the tail; sampling does not."""
        text = "A" * (_EVAL_SOURCE_BUDGET * 3) + " TAIL-FACT"
        excerpt, coverage = build_eval_excerpt(text)
        assert "TAIL-FACT" in excerpt, "the end of a long document must still reach the evaluator"
        assert coverage < 1.0


class TestTheScoreIsNotPresentedAsFidelityWhenTheSourceWasSampled:
    """Second acceptance criterion. Seeing more is not the same as seeing all,
    and a partial view described as a full one is the original defect resized."""

    def test_a_sampled_source_reports_what_fraction_was_seen(self) -> None:
        text = "X" * (_EVAL_SOURCE_BUDGET * 4)
        _, coverage = build_eval_excerpt(text)
        assert 0.0 < coverage < 1.0
        note = _PARTIAL_SOURCE_NOTE.format(percent=round(coverage * 100))
        assert "%" in note
        assert (
            "absence of a fact you cannot see is not" in note
        ), "the note must tell the evaluator not to treat an unseen fact as a dropped one"

    def test_a_whole_source_is_not_annotated(self) -> None:
        """The note must not appear when it would be false."""
        excerpt, coverage = build_eval_excerpt("short enough to pass whole")
        assert coverage == 1.0
        assert excerpt == "short enough to pass whole"

    def test_omissions_are_marked_rather_than_silently_joined(self) -> None:
        """Concatenating distant passages without a marker invents adjacency —
        a claim about the document that the document does not make."""
        text = "HEAD" + "." * (_EVAL_SOURCE_BUDGET * 2) + "TAIL"
        excerpt, _ = build_eval_excerpt(text)
        assert "[...]" in excerpt


class TestTheExcerptNeverOverstatesOrUnderstatesWhatItSaw:
    """Both bugs found in review, and both are this module's own defect (#16110).

    This PR exists because a score was computed against a source the evaluator
    could not see. A fix that *misreports* what it saw is the same failure with
    a better disguise — it produces a number that looks like measurement.
    """

    def test_a_budget_too_small_to_sample_does_not_return_the_whole_document(self) -> None:
        """`span = budget // 3` is 0 below 3, and `text[-0:]` is `text[0:]`.

        So the excerpt was the ENTIRE source while `coverage` read 0.0: more
        than the budget permitted, described as almost none of it. Inverted, not
        merely wrong.
        """
        text = "X" * 100
        excerpt, coverage = build_eval_excerpt(text, budget=2)
        assert len(excerpt) <= 2, "excerpt exceeds the budget it was given"
        assert len(excerpt) < len(text), "excerpt returned the whole source it was meant to sample"
        assert coverage == pytest.approx(2 / 100), "coverage must describe what was actually handed over"

    def test_the_old_negative_slice_is_what_made_it_whole(self) -> None:
        """The contrast. Without this the test above could pass for a new reason."""
        assert ("ABC"[-0:]) == "ABC", "python's negative-zero slice is the mechanism"
        assert ("ABC"[len("ABC") - 0 :]) == "", "and this is the form that behaves"

    def test_a_sampled_source_never_reports_one_hundred_percent(self) -> None:
        """`round(6000/6001 * 100)` is 100, so the note claimed the evaluator saw
        approximately all of a source whose excerpt still contains `[...]`."""
        text = "Y" * (_EVAL_SOURCE_BUDGET + 1)
        excerpt, coverage = build_eval_excerpt(text)
        assert "[...]" in excerpt, "precondition: this source is sampled, not whole"
        assert coverage < 1.0
        assert coverage_percent(coverage) == 99, "a sampled source must not announce itself as complete"

    def test_a_whole_source_still_reports_one_hundred(self) -> None:
        """The floor must not understate the honest case."""
        assert coverage_percent(1.0) == 100

    def test_the_tail_survives_the_slice_fix(self) -> None:
        """Guarding the negative-zero case must not stop the tail being sampled."""
        text = "A" * (_EVAL_SOURCE_BUDGET * 3) + "TAIL-FACT"
        excerpt, _ = build_eval_excerpt(text)
        assert "TAIL-FACT" in excerpt
