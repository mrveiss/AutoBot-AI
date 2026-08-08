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
        """The untrusted reference block is the least valuable section."""
        handler = _handler()

        prompt = handler._build_full_prompt(
            _text(20_000, "k"),
            _text(20_000, "c"),
            "question",
            _text(20_000, "t"),
        )

        assert prompt.count("t") < prompt.count("c"), "trajectory must be pruned before conversation history"


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
