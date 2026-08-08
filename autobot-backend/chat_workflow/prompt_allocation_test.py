# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The migrated caller for the #13640 allocator.

``_build_full_prompt`` assembles four competing sections — retrieved knowledge,
the trajectory reference block, conversation history, and the user's message —
and before #13640 concatenated all four with no budget whatsoever. These tests
prove the assembly now fits the model window and reports what it shed.
"""

from unittest.mock import patch

from chat_workflow.llm_handler import LLMHandlerMixin
from context_window_manager import ContextWindowManager

CHARS_PER_TOKEN = 4


def _handler():
    return LLMHandlerMixin.__new__(LLMHandlerMixin)


def _text(tokens: int, ch: str = "x") -> str:
    return ch * (tokens * CHARS_PER_TOKEN)


class TestPromptFitsTheWindow:
    def test_oversized_prompt_is_reduced_to_the_budget(self):
        """Before #13640 this concatenation had no budget at all."""
        handler = _handler()
        cwm = ContextWindowManager()

        knowledge = _text(20_000, "k")
        conversation = _text(20_000, "c")
        trajectory = _text(20_000, "t")
        message = "what changed in the deploy?"

        untrimmed = len(knowledge + conversation + trajectory + message) // CHARS_PER_TOKEN
        prompt = handler._build_full_prompt(knowledge, conversation, message, trajectory, model_name=None)
        after = cwm.estimate_tokens(prompt)

        budget = cwm.get_adaptive_context_length(None)
        assert untrimmed > budget, "fixture must actually overflow for this to mean anything"
        assert after < untrimmed
        assert after <= budget * 1.05, f"expected ~{budget} tokens, got {after}"

    def test_the_user_message_always_survives(self):
        """Priority ordering must never cost the user their own question."""
        handler = _handler()
        message = "PLEASE_KEEP_THIS_EXACT_QUESTION"

        prompt = handler._build_full_prompt(_text(50_000, "k"), _text(50_000, "c"), message, _text(50_000, "t"))

        assert message in prompt

    def test_trajectory_is_shed_before_conversation(self):
        """The untrusted reference block is the least valuable section.

        Asserts on the allocator's own report, not on character counts of the
        assembled prompt: the earlier version of this test passed just as
        happily with the priorities reversed, because `max_share` alone (0.2 vs
        0.5) satisfied a `count("t") < count("c")` comparison, and the prompt
        template contains literal "t" and "c" of its own.
        """
        handler = _handler()

        with patch("chat_workflow.llm_handler.logger") as log:
            handler._build_full_prompt(_text(20_000, "k"), _text(20_000, "c"), "question", _text(20_000, "t"))

        [call] = [c for c in log.info.call_args_list if c.args and "#13640" in str(c.args[0])]
        dropped = call.args[6]
        assert "trajectory" in dropped, f"trajectory must be dropped first, got dropped={dropped!r}"
        assert "conversation" not in dropped, "conversation outranks trajectory and must survive it"


class TestMessageIsReservedNotTrimmed:
    def test_a_modest_message_does_not_evict_sections_that_fit_beside_it(self):
        """#13640 review B2: the message used to be entered as a trimmable peer.

        At priority 100 it won every contest, wiping knowledge, history and
        trajectory to make room for text that was then restored in full. With
        the message reserved out of the budget instead, sections that genuinely
        fit alongside it are kept.
        """
        handler = _handler()
        message = "what changed in the deploy?"

        prompt = handler._build_full_prompt("KB-KEEP", "HISTORY-KEEP", message, "TRAJ-KEEP")

        assert message in prompt
        assert "KB-KEEP" in prompt
        assert "HISTORY-KEEP" in prompt
        assert "TRAJ-KEEP" in prompt

    def test_a_message_larger_than_the_window_survives_and_is_reported_honestly(self):
        """When the message alone exhausts the budget there is genuinely no room
        for context — but the message is still never truncated, and the logged
        total is the real one rather than the budget the code aimed at."""
        handler = _handler()
        cwm = ContextWindowManager()
        huge_message = _text(50_000, "m")

        with patch("chat_workflow.llm_handler.logger") as log:
            prompt = handler._build_full_prompt("KB", "HISTORY", huge_message, "TRAJ")

        assert huge_message in prompt, "the user's own message is never truncated"
        assert cwm.estimate_tokens(prompt) >= 50_000

        [call] = [c for c in log.info.call_args_list if c.args and "#13640" in str(c.args[0])]
        assert call.args[2] >= 50_000, "reported total must include the message actually shipped"

    def test_reported_totals_include_the_message(self):
        """The logged number must be what was actually shipped."""
        handler = _handler()

        with patch("chat_workflow.llm_handler.logger") as log:
            handler._build_full_prompt(_text(20_000, "k"), _text(20_000, "c"), _text(500, "m"), _text(20_000, "t"))

        [call] = [c for c in log.info.call_args_list if c.args and "#13640" in str(c.args[0])]
        before, after, _budget, message_tokens = call.args[1], call.args[2], call.args[3], call.args[4]
        assert message_tokens == 500
        assert before >= 60_000 + 500
        assert after >= message_tokens, "the message is part of the shipped total"


class TestUnderBudgetUnchanged:
    def test_a_small_prompt_is_untouched(self):
        """AC: under-budget input passes through byte-identical."""
        handler = _handler()
        knowledge = "KB: the deploy ran at 09:00."
        conversation = "User: hi\nAssistant: hello"
        trajectory = "Past: similar deploy question"
        message = "what changed?"

        prompt = handler._build_full_prompt(knowledge, conversation, message, trajectory)

        assert knowledge in prompt
        assert conversation in prompt
        assert trajectory in prompt
        assert message in prompt


class TestNonFatal:
    def test_allocation_failure_falls_back_to_untrimmed_sections(self):
        """A budgeting error must never cost the user their turn."""
        handler = _handler()

        with patch("context_window_manager.ContextWindowManager") as cls:
            cls.side_effect = RuntimeError("config unreadable")
            prompt = handler._build_full_prompt("KB", "HISTORY", "MESSAGE", "TRAJ")

        assert "KB" in prompt
        assert "HISTORY" in prompt
        assert "MESSAGE" in prompt

    def test_trimming_is_logged_not_silent(self):
        """AC: what was lost is reportable, not silently dropped."""
        handler = _handler()

        with patch("chat_workflow.llm_handler.logger") as log:
            handler._build_full_prompt(_text(50_000, "k"), _text(50_000, "c"), "q", _text(50_000, "t"))

        messages = [str(c.args[0]) for c in log.info.call_args_list if c.args]
        assert any("#13640" in m and "trimmed" in m for m in messages), messages
