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
            ContextSection(name="greedy", content=_text(1500), priority=999, max_share=0.5),
            ContextSection(name="humble", content=_text(100), priority=1),
        ]

        result = manager.allocate_sections(sections, budget_tokens=1000)

        greedy = next(s for s in result.sections if s.name == "greedy")
        assert manager.estimate_tokens(greedy.content) <= 500
        assert "greedy" in result.trimmed

    def test_caps_do_not_bind_when_there_is_headroom(self, manager):
        """max_share is a *contention* ceiling, not an unconditional cap.

        Enforcing it with the window half empty discards content for nothing —
        strictly worse than the unbudgeted concatenation this replaces.
        """
        sections = [
            ContextSection(name="roomy", content=_text(800), priority=1, max_share=0.2),
        ]

        result = manager.allocate_sections(sections, budget_tokens=10_000)

        assert manager.estimate_tokens(result.sections[0].content) == 800
        assert result.trimmed == []

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

    def test_priority_ties_are_resolved_deterministically(self, manager):
        """AC: ties in priority resolve deterministically, whatever the input order.

        #13717 changed *how*, not *whether*. This used to assert that "alpha"
        sorts first and is therefore drained first — deterministic, but it made
        the trim order total, so one peer absorbed the whole overflow and the
        other kept everything. Peers now share; determinism is still the
        property under test.
        """
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

        by_name_a = {s.name: len(s.content) for s in a.sections}
        by_name_b = {s.name: len(s.content) for s in b.sections}

        assert by_name_a == by_name_b, "input order changed the allocation"
        assert sorted(a.trimmed) == sorted(b.trimmed) == ["alpha", "beta"]

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


# ---------------------------------------------------------------------------
# Branches surfaced by review of PR #13706
# ---------------------------------------------------------------------------


class TestOvershootingTrimStrategy:
    def test_a_strategy_that_overshoots_is_reclamped(self, manager):
        """A section's trim is a ceiling, not a suggestion.

        `prompt_manager._truncate_large_file` — the reuse target this issue
        names — returns head+marker+tail, which exceeds the limit at small
        allocations. Without a re-clamp one such section silently puts the whole
        prompt back over budget.
        """

        def overshoot(content: str, max_chars: int) -> str:
            return content[:max_chars] + "X" * max_chars

        sections = [ContextSection(name="s", content=_text(5000), priority=1, trim=overshoot)]

        result = manager.allocate_sections(sections, budget_tokens=100)

        assert result.tokens_after <= 100
        assert result.fits

    def test_a_strategy_returning_a_non_string_falls_back(self, manager):
        sections = [
            ContextSection(name="s", content=_text(5000), priority=1, trim=lambda c, n: None),
        ]

        result = manager.allocate_sections(sections, budget_tokens=100)

        assert result.fits


class TestDegenerateBudgets:
    def test_zero_budget_empties_everything_and_reports_it(self, manager):
        sections = [ContextSection(name="a", content=_text(100), priority=1)]

        result = manager.allocate_sections(sections, budget_tokens=0)

        assert result.tokens_after == 0
        assert result.dropped == ["a"]

    def test_negative_budget_does_not_crash_or_loop(self, manager):
        sections = [ContextSection(name="a", content=_text(100), priority=1)]

        result = manager.allocate_sections(sections, budget_tokens=-5)

        assert result.tokens_after == 0

    def test_max_share_zero_empties_the_section_under_contention(self, manager):
        sections = [
            ContextSection(name="banned", content=_text(900), priority=99, max_share=0.0),
            ContextSection(name="kept", content=_text(900), priority=1),
        ]

        result = manager.allocate_sections(sections, budget_tokens=1000)

        banned = next(s for s in result.sections if s.name == "banned")
        assert banned.content == ""


class TestDuplicateNames:
    def test_duplicate_names_are_not_double_counted(self, manager):
        """`trimmed`/`dropped` are built from indices, so a repeated name cannot
        double-count or cross-attribute."""
        sections = [
            ContextSection(name="dup", content=_text(900), priority=1),
            ContextSection(name="dup", content=_text(900), priority=2),
        ]

        result = manager.allocate_sections(sections, budget_tokens=100)

        assert result.tokens_after <= 100
        assert len(result.trimmed) == len([s for s in result.sections if manager.estimate_tokens(s.content) < 900])


class TestSharedManager:
    def test_the_factory_returns_one_cached_instance(self):
        """Constructing per turn put ~45ms of YAML parsing on the event loop."""
        from context_window_manager import get_context_window_manager

        assert get_context_window_manager() is get_context_window_manager()


class TestPromptBudgetReservesRoomToAnswer:
    def test_prompt_budget_is_smaller_than_the_window(self, manager):
        window = manager.get_adaptive_context_length(None)
        budget = manager.get_prompt_budget(None)

        assert budget < window, "a prompt filling the window leaves nowhere to generate"
        assert budget > 0


class TestEqualPrioritySectionsShare:
    """Peers share the tier's budget instead of queueing (#13717).

    Trimming lowest-priority-first with `name` as a tie-break made the order
    *total*, so the first peers by name absorbed the whole overflow and the last
    kept everything. Correct for sections that genuinely rank; wrong for peers —
    N retrieved chunks, N file contents, N tool results.
    """

    def test_four_peers_each_retain_a_share(self, manager):
        """AC 1. The reported failure was alpha=0 bravo=0 charlie=0 delta=100."""
        sections = [
            ContextSection(name=n, content=_text(100), priority=5)
            for n in ("alpha", "bravo", "charlie", "delta")
        ]

        result = manager.allocate_sections(sections, budget_tokens=100)

        kept = {s.name: manager.estimate_tokens(s.content) for s in result.sections}
        assert all(v > 0 for v in kept.values()), f"a peer was zeroed: {kept}"
        assert sum(kept.values()) <= 100

    def test_twenty_peers_do_not_collapse_onto_one(self, manager):
        """The reported case where s9 kept everything because it sorts last."""
        sections = [ContextSection(name=f"s{i}", content=_text(50), priority=5) for i in range(20)]

        result = manager.allocate_sections(sections, budget_tokens=100)

        kept = {s.name: manager.estimate_tokens(s.content) for s in result.sections}
        assert max(kept.values()) < 100, f"one section took the whole budget: {kept}"

    def test_a_larger_peer_keeps_proportionally_more(self, manager):
        """Sharing is proportional to size, not a flat split."""
        sections = [
            ContextSection(name="big", content=_text(300), priority=5),
            ContextSection(name="small", content=_text(100), priority=5),
        ]

        result = manager.allocate_sections(sections, budget_tokens=200)

        kept = {s.name: manager.estimate_tokens(s.content) for s in result.sections}
        assert kept["big"] > kept["small"]

    def test_the_allocation_is_independent_of_input_order(self, manager):
        """AC 2. Same inputs in any order produce the same allocation."""
        names = ["a", "b", "c", "d", "e"]
        forward = [ContextSection(name=n, content=_text(80), priority=5) for n in names]
        backward = [ContextSection(name=n, content=_text(80), priority=5) for n in reversed(names)]

        a = {s.name: s.content for s in manager.allocate_sections(forward, budget_tokens=150).sections}
        b = {s.name: s.content for s in manager.allocate_sections(backward, budget_tokens=150).sections}

        assert a == b

    def test_rounding_leftovers_never_exceed_the_budget(self, manager):
        """AC 3. Proportional shares rarely land on integers."""
        for count in (3, 7, 11, 13):
            sections = [ContextSection(name=f"s{i}", content=_text(37), priority=5) for i in range(count)]

            result = manager.allocate_sections(sections, budget_tokens=100)

            assert result.tokens_after <= 100, f"{count} peers overflowed to {result.tokens_after}"
            assert result.fits

    def test_distinct_tiers_still_prune_lowest_first(self, manager):
        """AC 4. A section that genuinely outranks another must not lose tokens to it."""
        sections = [
            ContextSection(name="low", content=_text(400), priority=1),
            ContextSection(name="high", content=_text(400), priority=9),
        ]

        result = manager.allocate_sections(sections, budget_tokens=400)

        kept = {s.name: manager.estimate_tokens(s.content) for s in result.sections}
        assert kept["high"] == 400, "a higher tier paid for the lower one"
        assert kept["low"] == 0

    def test_a_share_that_rounds_to_zero_is_reported_as_dropped(self, manager):
        """AC 5. A section emptied by the split must not vanish silently."""
        sections = [ContextSection(name=f"s{i}", content=_text(40), priority=5) for i in range(40)]

        result = manager.allocate_sections(sections, budget_tokens=10)

        emptied = [s.name for s in result.sections if not s.content]
        assert emptied, "the budget cannot seat 40 peers; some must be emptied"
        assert set(emptied) <= set(result.dropped), "an emptied section was not reported in dropped"

    def test_peers_within_each_of_several_tiers_share(self, manager):
        """Tier ordering and intra-tier sharing compose."""
        sections = [
            ContextSection(name="lo1", content=_text(200), priority=1),
            ContextSection(name="lo2", content=_text(200), priority=1),
            ContextSection(name="hi1", content=_text(200), priority=9),
            ContextSection(name="hi2", content=_text(200), priority=9),
        ]

        result = manager.allocate_sections(sections, budget_tokens=600)

        kept = {s.name: manager.estimate_tokens(s.content) for s in result.sections}
        assert kept["hi1"] == kept["hi2"] == 200, "the untouched tier was trimmed"
        assert kept["lo1"] > 0 and kept["lo2"] > 0, "the trimmed tier collapsed onto one peer"
