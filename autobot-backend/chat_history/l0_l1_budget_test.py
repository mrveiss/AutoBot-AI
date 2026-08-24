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


async def _targets():
    """The layers' own per-model targets — what the allocator caps against."""
    from chat_history.layers import Layer0Identity, Layer1EssentialStory

    ctx = {"model_name": None}
    return await Layer0Identity().token_estimate(ctx), await Layer1EssentialStory().token_estimate(ctx)


async def _budget():
    cwm = get_context_window_manager()
    l0_target, l1_target = await _targets()
    ceiling = int(cwm.get_prompt_budget(None) * TieredContextBuilder._L0_L1_BUDGET_SHARE)
    return max(1, min(l0_target + l1_target, ceiling))


class TestOverBudgetIsTrimmedNotJustLogged:
    @pytest.mark.asyncio
    async def test_rendered_output_is_within_budget(self, builder):
        """AC: the output fits, rather than a warning being logged about it."""
        cwm = get_context_window_manager()
        budget = await _budget()

        l0, l1 = await builder._fit_l0_l1(_text(5_000, "i"), _text(5_000, "s"), None)

        assert cwm.estimate_tokens(l0) + cwm.estimate_tokens(l1) <= budget

    @pytest.mark.asyncio
    async def test_the_story_absorbs_the_overflow_not_identity(self, builder):
        """A turn can lose recalled facts and still behave; losing who it is
        cannot be recovered from.

        Priority shows in *who absorbs the overflow*, not in absolute size —
        identity is naturally the smaller block and is capped lower. Under
        contention identity keeps its full share while the story is pushed
        below its own cap to make the total fit.
        """
        cwm = get_context_window_manager()
        budget = await _budget()
        l0_target, l1_target = await _targets()
        identity_cap = int(budget * l0_target / (l0_target + l1_target))

        l0, l1 = await builder._fit_l0_l1(_text(5_000, "i"), _text(5_000, "s"), None)

        assert cwm.estimate_tokens(l0) == identity_cap, "identity keeps its whole share"
        assert cwm.estimate_tokens(l1) <= budget - identity_cap, "the story is what gives way"

    @pytest.mark.asyncio
    async def test_an_oversized_story_cannot_crowd_out_identity(self, builder):
        l0, _ = await builder._fit_l0_l1("## Identity\nRole: assistant", _text(50_000, "s"), None)

        assert "## Identity" in l0


class TestNoBudgetIsStranded:
    @pytest.mark.asyncio
    async def test_an_overflowing_fit_uses_the_whole_budget(self, builder):
        """Identity is a fixed ~3-line block that rarely uses its share.

        Capping the story at its proportional slice would strand that slack —
        measured at ~20% of the budget discarded on every real trim while the
        window sat idle. The story takes the whole ceiling instead, and
        priority is what keeps identity safe.
        """
        cwm = get_context_window_manager()
        budget = await _budget()

        l0, l1 = await builder._fit_l0_l1(_text(5_000, "i"), _text(5_000, "s"), None)

        used = cwm.estimate_tokens(l0) + cwm.estimate_tokens(l1)
        assert used == budget, f"stranded {budget - used} tokens of an available {budget}"


class TestUnderBudgetIsUntouched:
    @pytest.mark.asyncio
    async def test_normal_sized_layers_pass_through_verbatim(self, builder):
        l0_in = "## Identity\nRole: assistant\nOwner: mrveiss"
        l1_in = "## Essential Story\n- the deploy ran at 09:00"

        l0, l1 = await builder._fit_l0_l1(l0_in, l1_in, None)

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

    def test_the_share_is_what_derives_the_ceiling(self):
        """Pins the share itself.

        The earlier version of this test patched the budget to 200k, fed 10k
        tokens, and asserted the output exceeded a small number — which held for
        any share above ~0.003. It survived mutating 0.25 to 1.0, i.e. it never
        tested the constant it was named for.
        """
        assert int(200_000 * TieredContextBuilder._L0_L1_BUDGET_SHARE) == 50_000

    @pytest.mark.asyncio
    async def test_the_ceiling_binds_when_the_per_model_target_exceeds_it(self, builder):
        """The share is a ceiling over the layers' own per-model targets.

        A tiny window must clamp the block even though the per-model targets
        ask for more, so a bad config entry cannot hand L0+L1 the whole prompt.
        """
        cwm = get_context_window_manager()

        with patch.object(type(cwm), "get_prompt_budget", return_value=40):
            l0, l1 = await builder._fit_l0_l1(_text(5_000, "i"), _text(5_000, "s"), None)

        ceiling = max(1, int(40 * TieredContextBuilder._L0_L1_BUDGET_SHARE))
        assert cwm.estimate_tokens(l0) + cwm.estimate_tokens(l1) <= ceiling


class TestTrimmingIsReported:
    @pytest.mark.asyncio
    async def test_what_was_trimmed_is_logged(self, builder):
        """AC: what was trimmed is reported, not silently dropped."""
        with patch("chat_history.layers.logger") as log:
            await builder._fit_l0_l1(_text(5_000, "i"), _text(5_000, "s"), None)

        messages = [str(c.args[0]) for c in log.info.call_args_list if c.args]
        assert any("#13691" in m and "trimmed" in m for m in messages), messages

    @pytest.mark.asyncio
    async def test_nothing_is_logged_when_nothing_is_trimmed(self, builder):
        with patch("chat_history.layers.logger") as log:
            await builder._fit_l0_l1("## Identity", "## Story", None)

        assert not [c for c in log.info.call_args_list if c.args and "#13691" in str(c.args[0])]


class TestNonFatal:
    @pytest.mark.asyncio
    async def test_a_budgeting_failure_renders_untrimmed(self, builder):
        with patch("context_window_manager.get_context_window_manager", side_effect=RuntimeError("boom")):
            l0, l1 = await builder._fit_l0_l1("IDENTITY", "STORY", None)

        assert l0 == "IDENTITY"
        assert l1 == "STORY"


class TestNoSecondBudgetingConcept:
    @pytest.mark.asyncio
    async def test_enforcement_goes_through_the_context_window_manager(self, builder):
        """AC: no second budgeting concept alongside ContextWindowManager."""
        real = get_context_window_manager().allocate_sections

        with patch.object(type(get_context_window_manager()), "allocate_sections", side_effect=real) as allocate:
            await builder._fit_l0_l1("I", "S", None)

        allocate.assert_called_once()
        names = [sec.name for sec in allocate.call_args.args[0]]
        assert names == ["identity", "essential_story"]
