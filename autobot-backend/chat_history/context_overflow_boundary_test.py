# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Compaction boundary, user-message preservation and extracted state (#14066).

Three properties, each of which used to be absent:

1. The cut lands on a turn boundary. ``len(messages) // 2`` is a raw index and
   can fall between an assistant message carrying ``tool_calls`` and its
   ``role="tool"`` responses, orphaning them in the kept half.
2. User messages cross the boundary **verbatim**. They used to survive only if
   the summarizing model chose to include them, and a long session re-summarizes
   the same content repeatedly — each pass another chance to drop it.
3. A deterministic state block crosses alongside the model's summary, so a bad
   summarization turn cannot take the file paths and exit statuses with it.
"""

from unittest.mock import AsyncMock

import pytest

from chat_history.context_overflow import (
    _TOOL_RESULT_CLIP_CHARS,
    ContextOverflowProtection,
    _clip_tool_results,
    _extract_state,
    _pick_boundary,
    _preserved_user_messages,
)


def _tool_batch_history():
    """History whose raw midpoint falls inside a tool batch.

    10 messages; ``len // 2`` is 5, which is a ``role="tool"`` response whose
    assistant parent sits at index 4.
    """
    return [
        {"role": "user", "content": "first ask"},
        {"role": "assistant", "content": "sure"},
        {"role": "user", "content": "second ask"},
        {"role": "assistant", "content": "working"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file"}}]},
        {"role": "tool", "content": "file body"},
        {"role": "tool", "content": "second file body"},
        {"role": "assistant", "content": "done"},
        {"role": "user", "content": "third ask"},
        {"role": "assistant", "content": "ok"},
    ]


class TestBoundaryLandsOnATurnStart:
    """`len(messages) // 2` is an index, not a boundary."""

    def test_the_raw_midpoint_of_the_fixture_really_is_a_tool_message(self):
        # Guards the fixture itself: if this stops being true the tests below
        # would pass while asserting nothing.
        history = _tool_batch_history()
        assert history[len(history) // 2]["role"] == "tool"

    def test_the_chosen_boundary_is_never_inside_a_tool_batch(self):
        history = _tool_batch_history()
        boundary = _pick_boundary(history, len(history) // 2)
        assert history[boundary]["role"] != "tool"

    def test_the_kept_half_carries_no_orphaned_tool_message(self):
        history = _tool_batch_history()
        boundary = _pick_boundary(history, len(history) // 2)
        kept = history[boundary:]
        # A tool message is an orphan unless an assistant with tool_calls
        # precedes it within the kept half.
        in_batch = False
        for msg in kept:
            if msg["role"] == "tool":
                assert in_batch, "kept half starts with, or contains, an orphaned tool message"
                continue
            in_batch = msg["role"] == "assistant" and bool(msg.get("tool_calls"))

    def test_a_user_turn_is_preferred_when_one_is_in_reach(self):
        history = _tool_batch_history()
        boundary = _pick_boundary(history, len(history) // 2)
        assert history[boundary]["role"] == "user"

    def test_a_history_of_only_tool_messages_falls_back_to_zero(self):
        # Degenerate input must not raise and must not pick a tool index.
        history = [{"role": "tool", "content": "x"} for _ in range(4)]
        assert _pick_boundary(history, 2) == 0

    def test_an_empty_history_is_boundary_zero(self):
        assert _pick_boundary([], 0) == 0

    def test_a_leading_user_turn_does_not_drag_the_boundary_to_zero(self):
        """Boundary 0 summarizes nothing — and the caller then skips the reset.

        Found by the clipping wiring test: with the only user turn at index 0,
        the user-turn preference chose 0, so compaction summarized no messages,
        never reset the tracker, and the session re-attempted it every turn while
        reporting that compaction was enabled. Silent, and permanent.
        """
        history = [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file"}}]},
            {"role": "tool", "content": "body"},
            {"role": "assistant", "content": "ok"},
        ]
        boundary = _pick_boundary(history, len(history) // 2)
        assert boundary > 0, "compaction would summarize nothing and never reset the tracker"
        assert history[boundary]["role"] != "tool"


class TestUserMessagesSurviveVerbatim:
    def test_user_text_is_returned_unchanged(self):
        history = [
            {"role": "user", "content": "deploy only to staging, never prod"},
            {"role": "assistant", "content": "understood"},
        ]
        assert _preserved_user_messages(history, cap=40) == ["deploy only to staging, never prod"]

    def test_both_message_schemas_are_read(self):
        # API schema (role/content) and display schema (sender/text) both occur;
        # reading only one silently preserves nothing for the other.
        history = [
            {"role": "user", "content": "api schema"},
            {"sender": "user", "text": "display schema"},
        ]
        assert _preserved_user_messages(history, cap=40) == ["api schema", "display schema"]

    def test_the_cap_keeps_the_most_recent_not_the_oldest(self):
        history = [{"role": "user", "content": f"ask {i}"} for i in range(10)]
        assert _preserved_user_messages(history, cap=3) == ["ask 7", "ask 8", "ask 9"]

    def test_non_user_messages_are_not_preserved_here(self):
        history = [
            {"role": "assistant", "content": "assistant prose"},
            {"role": "tool", "content": "tool output"},
        ]
        assert _preserved_user_messages(history, cap=40) == []


class TestExtractedStateIsDeterministic:
    def _history_with_work(self):
        return [
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": "write_file", "arguments": '{"path": "src/app.py"}'}},
                ],
            },
            {"role": "tool", "content": "ok"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": "execute_command", "arguments": '{"command": "pytest -q"}'}},
                ],
            },
            {"role": "tool", "content": "2 failed, 5 passed\nexit status 1"},
        ]

    def test_a_written_file_is_reported(self):
        state = _extract_state(self._history_with_work())
        assert "src/app.py" in state["files_written"]

    def test_a_shell_command_is_reported(self):
        state = _extract_state(self._history_with_work())
        assert any("pytest -q" in c for c in state["commands"])

    def test_tools_used_are_reported(self):
        state = _extract_state(self._history_with_work())
        assert set(state["tools_used"]) == {"write_file", "execute_command"}

    def test_extraction_needs_no_model_call(self):
        # No gateway is patched here at all. If extraction ever reached for one
        # this test would error rather than fail, which is the point.
        assert _extract_state(self._history_with_work())["files_written"]

    def test_malformed_tool_calls_do_not_raise(self):
        history = [
            {"role": "assistant", "tool_calls": "not-a-list"},
            {"role": "assistant", "tool_calls": [{"function": {"name": "write_file", "arguments": "{bad json"}}]},
            "not-a-dict",
        ]
        state = _extract_state(history)
        assert state["files_written"] == []


class TestToolResultsAreClipped:
    def test_a_long_tool_result_is_clipped(self):
        history = [{"role": "tool", "content": "x" * (_TOOL_RESULT_CLIP_CHARS + 500)}]
        clipped = _clip_tool_results(history, _TOOL_RESULT_CLIP_CHARS)
        assert len(clipped[0]["content"]) <= _TOOL_RESULT_CLIP_CHARS + 32  # + truncation marker

    def test_a_short_tool_result_is_untouched(self):
        history = [{"role": "tool", "content": "short"}]
        assert _clip_tool_results(history, _TOOL_RESULT_CLIP_CHARS)[0]["content"] == "short"

    def test_user_and_assistant_text_is_never_clipped(self):
        long_text = "y" * (_TOOL_RESULT_CLIP_CHARS + 500)
        history = [{"role": "user", "content": long_text}]
        assert _clip_tool_results(history, _TOOL_RESULT_CLIP_CHARS)[0]["content"] == long_text

    @pytest.mark.asyncio
    async def test_create_summary_actually_clips_before_calling_the_summarizer(self):
        """The wiring, not the helper — see the boundary equivalent above.

        The three tests above all pass if ``_create_summary`` stops calling
        ``_clip_tool_results``. This one does not.
        """
        long_body = "x" * (_TOOL_RESULT_CLIP_CHARS + 500)
        history = [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file"}}]},
            {"role": "tool", "content": long_body},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "more"},
            {"role": "assistant", "content": "sure"},
            {"role": "user", "content": "next"},
            {"role": "assistant", "content": "done"},
            {"role": "user", "content": "and again"},
            {"role": "assistant", "content": "yes"},
        ]
        protection = ContextOverflowProtection()
        protection.summarizer.summarize_messages = AsyncMock(return_value="S")
        protection.tracker.reset_session = AsyncMock()
        protection.tracker.add_message_tokens = AsyncMock()

        await protection._create_summary("session-1", history, "gpt-4")

        sent = protection.summarizer.summarize_messages.await_args.args[0]
        tool_bodies = [m["content"] for m in sent if m.get("role") == "tool"]
        assert tool_bodies, "fixture must put a tool result in the summarized region"
        assert all(len(b) < len(long_body) for b in tool_bodies), "tool result reached the summarizer unclipped"
        # And the caller's own history is untouched.
        assert history[2]["content"] == long_body

    def test_the_input_list_is_not_mutated(self):
        history = [{"role": "tool", "content": "z" * (_TOOL_RESULT_CLIP_CHARS + 500)}]
        original = history[0]["content"]
        _clip_tool_results(history, _TOOL_RESULT_CLIP_CHARS)
        assert history[0]["content"] == original


class TestTheComposedSummaryCarriesAllThree:
    """End-to-end through `_create_summary`, with the model stubbed."""

    async def _compact(self, history, summary_text="MODEL SUMMARY"):
        protection = ContextOverflowProtection()
        protection.summarizer.summarize_messages = AsyncMock(return_value=summary_text)
        protection.tracker.reset_session = AsyncMock()
        protection.tracker.add_message_tokens = AsyncMock()
        return await protection._create_summary("session-1", history, "gpt-4")

    @pytest.mark.asyncio
    async def test_state_survives_a_summary_that_mentions_none_of_it(self):
        history = [
            {"role": "user", "content": "ship it"},
            {
                "role": "assistant",
                "tool_calls": [{"function": {"name": "write_file", "arguments": '{"path": "src/app.py"}'}}],
            },
            {"role": "tool", "content": "ok"},
            {"role": "user", "content": "and run the tests"},
            {"role": "assistant", "content": "done"},
            {"role": "user", "content": "thanks"},
        ]
        composed = await self._compact(history, summary_text="The user asked for some changes.")
        # The stub summary names no file. The path must still cross the boundary.
        assert "src/app.py" in composed
        assert "src/app.py" not in "The user asked for some changes."

    @pytest.mark.asyncio
    async def test_user_instructions_cross_verbatim(self):
        history = [
            {"role": "user", "content": "never touch the prod database"},
            {"role": "assistant", "content": "understood"},
            {"role": "user", "content": "now add the endpoint"},
            {"role": "assistant", "content": "added"},
        ]
        composed = await self._compact(history)
        assert "never touch the prod database" in composed

    @pytest.mark.asyncio
    async def test_two_successive_compactions_do_not_erode_the_instruction(self):
        history = [
            {"role": "user", "content": "never touch the prod database"},
            {"role": "assistant", "content": "understood"},
            {"role": "user", "content": "add the endpoint"},
            {"role": "assistant", "content": "added"},
        ]
        first = await self._compact(history)
        # The composed summary becomes a message in the next round's history.
        second_round = [{"role": "user", "content": first}] + history
        second = await self._compact(second_round)
        assert "never touch the prod database" in second

    @pytest.mark.asyncio
    async def test_an_empty_history_still_returns_empty(self):
        assert await self._compact([]) == ""

    @pytest.mark.asyncio
    async def test_create_summary_cuts_at_the_snapped_boundary_not_the_raw_index(self):
        """The wiring, not the helper.

        Every other boundary test calls ``_pick_boundary`` directly, so all of
        them stay green if ``_create_summary`` goes back to ``len // 2``. This
        one fails in that case, which is the only reason it exists.
        """
        history = _tool_batch_history()
        protection = ContextOverflowProtection()
        protection.summarizer.summarize_messages = AsyncMock(return_value="S")
        protection.tracker.reset_session = AsyncMock()
        protection.tracker.add_message_tokens = AsyncMock()

        await protection._create_summary("session-1", history, "gpt-4")

        expected = _pick_boundary(history, len(history) // 2)
        assert expected != len(history) // 2, "fixture no longer distinguishes snapped from raw"

        sent = protection.summarizer.summarize_messages.await_args.args[0]
        assert len(sent) == expected, "summarizer was given the raw-index region, not the snapped one"
        # One refill per retained message: the kept half is everything after the
        # boundary the production path actually used.
        assert protection.tracker.add_message_tokens.await_count == len(history) - expected

    @pytest.mark.asyncio
    async def test_the_kept_half_of_a_real_compaction_has_no_orphaned_tool_message(self):
        """The invariant the boundary exists to protect, through the real path."""
        history = _tool_batch_history()
        protection = ContextOverflowProtection()
        protection.summarizer.summarize_messages = AsyncMock(return_value="S")
        protection.tracker.reset_session = AsyncMock()
        protection.tracker.add_message_tokens = AsyncMock()

        await protection._create_summary("session-1", history, "gpt-4")

        retained = protection.tracker.add_message_tokens.await_count
        kept = history[len(history) - retained :]
        in_batch = False
        for msg in kept:
            if msg["role"] == "tool":
                assert in_batch, f"compaction left an orphaned tool message in the kept half: {kept!r}"
                continue
            in_batch = msg["role"] == "assistant" and bool(msg.get("tool_calls"))


class TestCompactedViewIsSmallerThanWhatItReplaced:
    @pytest.mark.asyncio
    async def test_compaction_measurably_reduces_the_summarized_region(self):
        """The invariant, asserted — not a number quoted in a PR body.

        The whole point of compaction is that the composed replacement is
        smaller than the region it replaces. A change that grows the state block
        or the preserved-user set without bound breaks this and nothing else
        would notice.
        """
        from autobot_shared.token_count import estimate_fast

        history = []
        for i in range(40):
            history.append({"role": "user", "content": f"instruction {i} " + ("detail " * 40)})
            history.append({"role": "assistant", "content": "acknowledged " * 60})

        protection = ContextOverflowProtection()
        protection.summarizer.summarize_messages = AsyncMock(return_value="A short summary.")
        protection.tracker.reset_session = AsyncMock()
        protection.tracker.add_message_tokens = AsyncMock()

        boundary = _pick_boundary(history, len(history) // 2)
        replaced_tokens = sum(estimate_fast(str(m.get("content", ""))) for m in history[:boundary])

        composed = await protection._create_summary("session-1", history, "gpt-4")
        composed_tokens = estimate_fast(composed)

        assert replaced_tokens > 0
        assert (
            composed_tokens < replaced_tokens
        ), f"compaction grew the region it replaced: {replaced_tokens} → {composed_tokens}"


class TestExistingBehaviourIsPreserved:
    @pytest.mark.asyncio
    async def test_a_summarization_failure_still_propagates(self):
        """#14065's guarantee must not regress under #14066's changes."""
        from chat_history.context_overflow import SummarizationFailed

        protection = ContextOverflowProtection()
        protection.summarizer.summarize_messages = AsyncMock(side_effect=SummarizationFailed("boom"))
        protection.tracker.reset_session = AsyncMock()

        history = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
            {"role": "assistant", "content": "d"},
        ]
        with pytest.raises(SummarizationFailed):
            await protection._create_summary("session-1", history, "gpt-4")
        protection.tracker.reset_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_tracker_is_still_reset_and_refilled_on_success(self):
        protection = ContextOverflowProtection()
        protection.summarizer.summarize_messages = AsyncMock(return_value="summary")
        protection.tracker.reset_session = AsyncMock()
        protection.tracker.add_message_tokens = AsyncMock()

        history = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
            {"role": "assistant", "content": "d"},
        ]
        await protection._create_summary("session-1", history, "gpt-4")
        protection.tracker.reset_session.assert_awaited_once_with("session-1")
        assert protection.tracker.add_message_tokens.await_count > 0


class TestClippingLandsWhereTheSummarizerReads:
    """Review finding on this PR: the clip must land in the key that is *read*.

    `_format_messages` reads `msg.get("content") or msg.get("text", "")`. Writing
    the clipped body to `text` while a truthy `content` survives means the full
    body still reaches the summarizer — with every clipping test still green,
    because they all used string content.
    """

    def _summarizer_view(self, msg):
        """What ConversationSummarizer._format_messages would actually read."""
        from chat_history.context_overflow import ConversationSummarizer

        return ConversationSummarizer()._format_messages([msg])

    def test_a_list_content_tool_result_is_actually_clipped(self):
        long_text = "x" * (_TOOL_RESULT_CLIP_CHARS + 500)
        msg = {"role": "tool", "content": [{"type": "text", "text": long_text}]}
        clipped = _clip_tool_results([msg], _TOOL_RESULT_CLIP_CHARS)[0]
        assert len(self._summarizer_view(clipped)) < len(long_text)

    def test_an_empty_content_beside_a_populated_text_is_actually_clipped(self):
        long_text = "y" * (_TOOL_RESULT_CLIP_CHARS + 500)
        msg = {"role": "tool", "content": "", "text": long_text}
        clipped = _clip_tool_results([msg], _TOOL_RESULT_CLIP_CHARS)[0]
        assert len(self._summarizer_view(clipped)) < len(long_text)

    def test_a_string_content_tool_result_is_still_clipped(self):
        long_text = "z" * (_TOOL_RESULT_CLIP_CHARS + 500)
        msg = {"role": "tool", "content": long_text}
        clipped = _clip_tool_results([msg], _TOOL_RESULT_CLIP_CHARS)[0]
        assert len(self._summarizer_view(clipped)) < len(long_text)

    def test_a_list_content_with_no_text_parts_falls_back_to_text(self):
        long_text = "w" * (_TOOL_RESULT_CLIP_CHARS + 500)
        msg = {"role": "tool", "content": [{"type": "image", "url": "u"}], "text": long_text}
        clipped = _clip_tool_results([msg], _TOOL_RESULT_CLIP_CHARS)[0]
        assert len(clipped["text"]) < len(long_text)
