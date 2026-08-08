# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The L0+L1 budget actually trims now (#13691).

`_L0_L1_MAX_TOKENS = 900` was commented "acceptance-criterion guard" and did
nothing but log: the warning fired and both layers rendered in full anyway. An
acceptance criterion recorded as met on the strength of it was not met.

These assert the rendered output is within budget — not that a warning was
logged.
"""

from unittest.mock import patch

import pytest

from chat_history.layers import TieredContextBuilder
from context_window_manager import get_context_window_manager

CHARS_PER_TOKEN = 4


def _text(tokens: int, ch: str = "x") -> str:
    return ch * (tokens * CHARS_PER_TOKEN)


@pytest.fixture
def builder():
    return TieredContextBuilder()


@pytest.fixture
def budget():
    cwm = get_context_window_manager()
    return int(cwm.get_prompt_budget(None) * TieredContextBuilder._L0_L1_BUDGET_SHARE)


class TestOverBudgetIsTrimmedNotJustLogged:
    def test_rendered_output_is_within_budget(self, builder, budget):
        """AC: the output fits, rather than a warning being logged about it."""
        cwm = get_context_window_manager()

        l0, l1 = builder._fit_l0_l1(_text(5_000, "i"), _text(5_000, "s"), None)

        assert cwm.estimate_tokens(l0) + cwm.estimate_tokens(l1) <= budget

    def test_the_story_absorbs_the_overflow_not_identity(self, builder, budget):
        """A turn can lose recalled facts and still behave; losing who it is
        cannot be recovered from.

        Priority shows in *who absorbs the overflow*, not in absolute size —
        identity is naturally the smaller block and is capped lower. Under
        contention identity keeps its full share while the story is pushed
        below its own cap to make the total fit.
        """
        cwm = get_context_window_manager()
        identity_cap = int(budget * 0.4)
        story_cap = int(budget * 0.8)

        l0, l1 = builder._fit_l0_l1(_text(5_000, "i"), _text(5_000, "s"), None)

        assert cwm.estimate_tokens(l0) == identity_cap, "identity keeps its whole share"
        assert cwm.estimate_tokens(l1) < story_cap, "the story is what gives way"

    def test_an_oversized_story_cannot_crowd_out_identity(self, builder):
        l0, _ = builder._fit_l0_l1("## Identity\nRole: assistant", _text(50_000, "s"), None)

        assert "## Identity" in l0


class TestUnderBudgetIsUntouched:
    def test_normal_sized_layers_pass_through_verbatim(self, builder):
        l0_in = "## Identity\nRole: assistant\nOwner: mrveiss"
        l1_in = "## Essential Story\n- the deploy ran at 09:00"

        l0, l1 = builder._fit_l0_l1(l0_in, l1_in, None)

        assert l0 == l0_in
        assert l1 == l1_in


class TestBudgetDerivesFromTheModel:
    def test_budget_is_not_a_flat_constant(self):
        """AC: the budget derives from the model's window.

        The old flat 900 meant something different on an 8k model than on a
        200k one, while L1's own token_estimate already read a per-model value.
        """
        assert not hasattr(TieredContextBuilder, "_L0_L1_MAX_TOKENS")
        assert isinstance(TieredContextBuilder._L0_L1_BUDGET_SHARE, float)

    def test_a_bigger_window_yields_a_bigger_budget(self, builder):
        cwm = get_context_window_manager()
        small = int(cwm.get_prompt_budget(None) * TieredContextBuilder._L0_L1_BUDGET_SHARE)

        with patch.object(type(cwm), "get_prompt_budget", return_value=200_000):
            l0, l1 = builder._fit_l0_l1(_text(5_000, "i"), _text(5_000, "s"), None)

        # 10k tokens of input fits comfortably in a 200k-derived budget but not
        # in the small one, so nothing is trimmed at the larger window.
        assert cwm.estimate_tokens(l0) + cwm.estimate_tokens(l1) > small


class TestTrimmingIsReported:
    def test_what_was_trimmed_is_logged(self, builder):
        """AC: what was trimmed is reported, not silently dropped."""
        with patch("chat_history.layers.logger") as log:
            builder._fit_l0_l1(_text(5_000, "i"), _text(5_000, "s"), None)

        messages = [str(c.args[0]) for c in log.info.call_args_list if c.args]
        assert any("#13691" in m and "trimmed" in m for m in messages), messages

    def test_nothing_is_logged_when_nothing_is_trimmed(self, builder):
        with patch("chat_history.layers.logger") as log:
            builder._fit_l0_l1("## Identity", "## Story", None)

        assert not [c for c in log.info.call_args_list if c.args and "#13691" in str(c.args[0])]


class TestNonFatal:
    def test_a_budgeting_failure_renders_untrimmed(self, builder):
        with patch("context_window_manager.get_context_window_manager", side_effect=RuntimeError("boom")):
            l0, l1 = builder._fit_l0_l1("IDENTITY", "STORY", None)

        assert l0 == "IDENTITY"
        assert l1 == "STORY"


class TestNoSecondBudgetingConcept:
    def test_enforcement_goes_through_the_context_window_manager(self, builder):
        """AC: no second budgeting concept alongside ContextWindowManager."""
        real = get_context_window_manager().allocate_sections

        with patch.object(type(get_context_window_manager()), "allocate_sections", side_effect=real) as allocate:
            builder._fit_l0_l1("I", "S", None)

        allocate.assert_called_once()
        names = [sec.name for sec in allocate.call_args.args[0]]
        assert names == ["identity", "essential_story"]
