# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Multi-section context allocation (#13640).

Before this, every LLM path truncated in its own way and nothing allocated one
budget *across* competing sections. An overflowing prompt dropped whatever the
code happened to cut last, and no caller could report what was lost.
"""

import pytest

from context_window_manager import ContextAllocation, ContextSection, ContextWindowManager

CHARS_PER_TOKEN = 4


@pytest.fixture
def manager():
    return ContextWindowManager()


def _text(tokens: int, ch: str = "x") -> str:
    """Build text that estimates to exactly *tokens* tokens."""
    return ch * (tokens * CHARS_PER_TOKEN)


class TestUnderBudgetPassthrough:
    def test_under_budget_input_passes_through_byte_identical(self, manager):
        """AC: an under-budget prompt is never touched."""
        sections = [
            ContextSection(name="query", content="what is the deploy status?", priority=100),
            ContextSection(name="retrieved", content="chunk one\nchunk two", priority=50),
        ]
        originals = [s.content for s in sections]

        result = manager.allocate_sections(sections, budget_tokens=10_000)

        assert [s.content for s in result.sections] == originals
        assert result.trimmed == []
        assert result.dropped == []
        assert result.tokens_before == result.tokens_after
        assert result.fits

    def test_inputs_are_not_mutated(self, manager):
        """Pure function: the caller's section objects survive unchanged."""
        section = ContextSection(name="files", content=_text(500), priority=1)
        manager.allocate_sections([section], budget_tokens=10)

        assert manager.estimate_tokens(section.content) == 500


class TestShareCap:
    def test_max_share_binds_even_for_the_highest_priority_section(self, manager):
        """AC: one oversized section cannot crowd out the rest, however important."""
        sections = [
            ContextSection(name="greedy", content=_text(900), priority=999, max_share=0.5),
            ContextSection(name="humble", content=_text(100), priority=1),
        ]

        result = manager.allocate_sections(sections, budget_tokens=1000)

        greedy = next(s for s in result.sections if s.name == "greedy")
        assert manager.estimate_tokens(greedy.content) <= 500
        assert "greedy" in result.trimmed

    def test_cap_applies_before_priority_so_low_priority_survives(self, manager):
        sections = [
            ContextSection(name="greedy", content=_text(2000), priority=999, max_share=0.5),
            ContextSection(name="humble", content=_text(100), priority=1),
        ]

        result = manager.allocate_sections(sections, budget_tokens=1000)

        humble = next(s for s in result.sections if s.name == "humble")
        assert humble.content, "the low-priority section must not be wiped by a greedy neighbour"


class TestPriorityTrim:
    def test_lowest_priority_is_pruned_first(self, manager):
        sections = [
            ContextSection(name="keep", content=_text(600), priority=100),
            ContextSection(name="shed", content=_text(600), priority=1),
        ]

        result = manager.allocate_sections(sections, budget_tokens=700)

        keep = next(s for s in result.sections if s.name == "keep")
        shed = next(s for s in result.sections if s.name == "shed")
        assert manager.estimate_tokens(keep.content) == 600
        assert manager.estimate_tokens(shed.content) < 600
        assert "shed" in result.trimmed
        assert "keep" not in result.trimmed

    def test_priority_ties_break_deterministically(self, manager):
        """AC: ties in priority are broken deterministically (by name)."""
        first = [
            ContextSection(name="alpha", content=_text(400), priority=5),
            ContextSection(name="beta", content=_text(400), priority=5),
        ]
        second = [
            ContextSection(name="beta", content=_text(400), priority=5),
            ContextSection(name="alpha", content=_text(400), priority=5),
        ]

        a = manager.allocate_sections(first, budget_tokens=500)
        b = manager.allocate_sections(second, budget_tokens=500)

        # "alpha" sorts first, so it is pruned first regardless of input order.
        assert a.trimmed == b.trimmed == ["alpha"]

    def test_result_fits_the_budget(self, manager):
        sections = [
            ContextSection(name="a", content=_text(900), priority=3),
            ContextSection(name="b", content=_text(900), priority=2),
            ContextSection(name="c", content=_text(900), priority=1),
        ]

        result = manager.allocate_sections(sections, budget_tokens=1000)

        assert result.tokens_after <= 1000
        assert result.fits


class TestReporting:
    def test_reports_before_and_after_totals(self, manager):
        """AC: the result reports before/after totals."""
        sections = [ContextSection(name="big", content=_text(5000), priority=1)]

        result = manager.allocate_sections(sections, budget_tokens=100)

        assert result.tokens_before == 5000
        assert result.tokens_after <= 100
        assert result.budget == 100

    def test_a_section_reduced_to_zero_is_reported_not_silently_emptied(self, manager):
        """AC: total loss of a section is visible to the caller."""
        sections = [
            ContextSection(name="essential", content=_text(1000), priority=100),
            ContextSection(name="expendable", content=_text(1000), priority=1),
        ]

        result = manager.allocate_sections(sections, budget_tokens=1000)

        expendable = next(s for s in result.sections if s.name == "expendable")
        assert expendable.content == ""
        assert "expendable" in result.trimmed
        assert "expendable" in result.dropped

    def test_render_skips_emptied_sections(self, manager):
        sections = [
            ContextSection(name="kept", content="KEPT", priority=100),
            ContextSection(name="gone", content=_text(5000), priority=1),
        ]

        result = manager.allocate_sections(sections, budget_tokens=1)

        assert "KEPT" not in result.render() or result.render().count("\n\n") == 0


class TestSectionShrinkStrategy:
    def test_a_section_can_supply_its_own_shrink_strategy(self, manager):
        """Existing per-artefact truncation is reused, not replaced."""
        calls = []

        def head_and_tail(content: str, max_chars: int) -> str:
            calls.append(max_chars)
            half = max(1, max_chars // 2)
            return content[:half] + "\n...[trimmed]...\n" + content[-half:]

        sections = [
            ContextSection(name="file", content=_text(2000), priority=1, trim=head_and_tail),
        ]

        result = manager.allocate_sections(sections, budget_tokens=100)

        assert calls, "the section's own trim strategy must be used"
        assert "[trimmed]" in result.sections[0].content

    def test_default_trim_keeps_the_head(self, manager):
        sections = [ContextSection(name="s", content="ABCDEFGH" * 100, priority=1)]

        result = manager.allocate_sections(sections, budget_tokens=2)

        assert result.sections[0].content.startswith("ABC")


class TestEstimationPath:
    def test_estimation_uses_the_managers_configured_ratio(self, manager):
        """No new heuristic: allocation counts tokens the same way the class does.

        #12764 kept ContextWindowManager.estimate_tokens off the shared
        estimator on purpose — chars_per_token here is a runtime config knob.
        The allocator must honour that knob, not a second hardcoded ratio.
        """
        manager.config["token_estimation"]["chars_per_token"] = 2
        sections = [ContextSection(name="s", content="a" * 100, priority=1)]

        result = manager.allocate_sections(sections, budget_tokens=10_000)

        assert result.tokens_before == 50  # 100 chars / 2, not / 4


class TestAllocationShape:
    def test_returns_a_context_allocation(self, manager):
        result = manager.allocate_sections([], budget_tokens=100)
        assert isinstance(result, ContextAllocation)
        assert result.tokens_before == 0
        assert result.fits
