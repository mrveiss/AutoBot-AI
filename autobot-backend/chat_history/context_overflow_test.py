# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for context overflow protection. Issue #9043."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_history.context_overflow import (
    ContextOverflowProtection,
    ConversationSummarizer,
    SessionTokenTracker,
    SummarizationFailed,
)


class TestSessionTokenTracker:
    """Test token tracking functionality."""

    @pytest.mark.asyncio
    async def test_add_and_get_session_tokens(self):
        """Verify token accumulation across multiple messages."""
        tracker = SessionTokenTracker()

        # Mock Redis client
        mock_redis = AsyncMock()
        # #13274: the shared client is decode_responses=True, so hgetall returns
        # str keys AND str values. This mock previously returned bytes for both —
        # a shape the live client never produces — and passed only because
        # get_session_usage probed with matching bytes literals. Test and code
        # agreed with each other and both disagreed with Redis.
        mock_redis.hgetall.return_value = {
            "total_tokens": "300",
            "prompt_tokens": "200",
            "completion_tokens": "100",
            "message_count": "2",
        }

        with patch.object(tracker, "_ensure_redis", return_value=mock_redis):
            # Add tokens for first message
            await tracker.add_message_tokens("session-1", prompt_tokens=100, completion_tokens=50)

            # Add tokens for second message
            await tracker.add_message_tokens("session-1", prompt_tokens=100, completion_tokens=50)

            # Get session usage
            usage = await tracker.get_session_usage("session-1")

        assert usage["total_tokens"] == 300
        assert usage["prompt_tokens"] == 200
        assert usage["completion_tokens"] == 100
        assert usage["message_count"] == 2

    @pytest.mark.asyncio
    async def test_get_session_usage_no_data(self):
        """Verify zeros returned when no session data exists."""
        tracker = SessionTokenTracker()

        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {}

        with patch.object(tracker, "_ensure_redis", return_value=mock_redis):
            usage = await tracker.get_session_usage("nonexistent")

        assert usage["total_tokens"] == 0
        assert usage["prompt_tokens"] == 0
        assert usage["completion_tokens"] == 0
        assert usage["message_count"] == 0

    @pytest.mark.asyncio
    async def test_reset_session(self):
        """Verify session reset clears token tracking."""
        tracker = SessionTokenTracker()

        mock_redis = AsyncMock()

        with patch.object(tracker, "_ensure_redis", return_value=mock_redis):
            await tracker.reset_session("session-1")

        mock_redis.delete.assert_called_once_with("chat:tokens:session-1")

    @pytest.mark.asyncio
    async def test_redis_unavailable_graceful_handling(self):
        """Verify graceful handling when Redis is unavailable."""
        tracker = SessionTokenTracker()

        with patch.object(tracker, "_ensure_redis", return_value=None):
            # Should not raise, just log warning
            await tracker.add_message_tokens("session-1", prompt_tokens=100)
            usage = await tracker.get_session_usage("session-1")

        # Returns zeros when Redis unavailable
        assert usage["total_tokens"] == 0


class TestConversationSummarizer:
    """Test conversation summarization functionality."""

    @pytest.mark.asyncio
    async def test_summarize_messages(self):
        """Verify LLM-based summarization."""
        summarizer = ConversationSummarizer()

        messages = [
            {"sender": "user", "text": "What's the weather?"},
            {"sender": "assistant", "text": "It's sunny today."},
            {"sender": "user", "text": "Should I bring an umbrella?"},
            {"sender": "assistant", "text": "No need, no rain expected."},
        ]

        # Mock LLM gateway
        mock_response = MagicMock()
        mock_response.content = "User asked about weather. Assistant confirmed sunny, no rain expected."

        mock_gateway = AsyncMock()
        mock_gateway.chat_completion.return_value = mock_response

        with patch.object(summarizer, "_get_gateway", return_value=mock_gateway):
            summary = await summarizer.summarize_messages(messages, "gpt-4")

        assert "weather" in summary.lower()
        assert len(summary) > 0

    @pytest.mark.asyncio
    async def test_summarize_empty_messages(self):
        """Verify handling of empty message list."""
        summarizer = ConversationSummarizer()

        mock_response = MagicMock()
        mock_response.content = "[Summary: 0 earlier message(s) were summarized to preserve context.]"

        mock_gateway = AsyncMock()
        mock_gateway.chat_completion.return_value = mock_response

        with patch.object(summarizer, "_get_gateway", return_value=mock_gateway):
            summary = await summarizer.summarize_messages([], "gpt-4")

        assert "Summary" in summary

    @pytest.mark.asyncio
    async def test_a_gateway_failure_raises_instead_of_returning_a_placeholder(self):
        """#14065: the old behaviour returned a success-shaped placeholder here.

        This test previously asserted that placeholder ("1 earlier message"),
        pinning the defect in place: the caller could not distinguish "history
        was compressed" from "history was destroyed and replaced with a sentence
        saying it existed", so it reset the token tracker and reported success.
        """
        summarizer = ConversationSummarizer()
        messages = [{"sender": "user", "text": "Hello"}]

        with patch.object(summarizer, "_get_gateway", side_effect=Exception("LLM error")):
            with pytest.raises(SummarizationFailed) as excinfo:
                await summarizer.summarize_messages(messages, "gpt-4")

        assert "LLM error" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_an_empty_completion_raises_rather_than_reading_as_a_summary(self):
        """A provider that returns nothing is a failure, not a very short summary."""
        summarizer = ConversationSummarizer()
        messages = [{"sender": "user", "text": "Hello"}]

        mock_response = MagicMock()
        mock_response.content = "   "
        mock_gateway = AsyncMock()
        mock_gateway.chat_completion.return_value = mock_response

        with patch.object(summarizer, "_get_gateway", return_value=mock_gateway):
            with pytest.raises(SummarizationFailed):
                await summarizer.summarize_messages(messages, "gpt-4")

    @pytest.mark.asyncio
    async def test_malformed_history_degrades_instead_of_500ing_the_turn(self):
        """#14065 review: these helpers run outside the try, so they must be total.

        A multimodal part with ``text: None`` is a shape providers genuinely
        emit, and a non-dict entry can reach here from trimmed history. Both
        used to raise past ``check_and_protect``'s ``except SummarizationFailed``
        and land on ``@with_error_handling`` as a 500 — for a turn whose answer
        had already been generated and stored.
        """
        summarizer = ConversationSummarizer()
        messages = [
            "not a dict at all",
            {"role": "user", "content": [{"type": "text", "text": None}]},
            {"role": "user", "content": "a real one"},
        ]

        mock_response = MagicMock()
        mock_response.content = "Summary."
        mock_gateway = AsyncMock()
        mock_gateway.chat_completion.return_value = mock_response

        with patch.object(summarizer, "_get_gateway", return_value=mock_gateway):
            summary = await summarizer.summarize_messages(messages, "gpt-4")

        assert summary == "Summary."
        prompt = mock_gateway.chat_completion.call_args.kwargs["messages"][0]["content"]
        assert "a real one" in prompt, "the well-formed message must still reach the summarizer"

    @pytest.mark.asyncio
    async def test_a_formatting_bug_is_not_relabelled_a_summarization_failure(self):
        """#14065: the ``except Exception`` used to cover the whole body.

        A crash in ``_format_messages`` is a programming error. Reported as a
        summarization failure it would be retried on every turn forever, and the
        real traceback would be buried under a generic provider-failure message.
        """
        summarizer = ConversationSummarizer()

        with patch.object(summarizer, "_format_messages", side_effect=TypeError("bad message shape")):
            with pytest.raises(TypeError, match="bad message shape"):
                await summarizer.summarize_messages([{"sender": "user", "text": "x"}], "gpt-4")


class TestContextOverflowProtection:
    """Test context overflow detection and protection."""

    @pytest.mark.asyncio
    async def test_warning_at_80_percent(self):
        """Verify warning triggered at 80% context fill."""
        protection = ContextOverflowProtection(
            warning_threshold=0.80,
            compress_threshold=0.90,
        )

        # Mock context limit of 1000 tokens
        with patch.object(protection, "_get_context_limit", return_value=1000):
            # Mock current usage at 810 tokens (81%)
            mock_tracker = AsyncMock()
            mock_tracker.get_session_usage.return_value = {
                "total_tokens": 810,
                "prompt_tokens": 540,
                "completion_tokens": 270,
                "message_count": 10,
            }
            protection.tracker = mock_tracker

            status = await protection.check_and_protect(
                session_id="session-1",
                model_name="gpt-4",
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                mode="warn_only",
            )

        assert status["warning_triggered"] is True
        assert status["summary_created"] is False
        assert status["current_fill_percentage"] >= 0.80

    @pytest.mark.asyncio
    async def test_auto_compress_at_90_percent(self):
        """Verify auto-summarization triggered at 90% context fill."""
        protection = ContextOverflowProtection(
            warning_threshold=0.80,
            compress_threshold=0.90,
        )

        messages = [{"sender": "user", "text": f"Message {i}"} for i in range(10)]

        # Mock context limit of 1000 tokens
        with patch.object(protection, "_get_context_limit", return_value=1000):
            # Mock current usage at 920 tokens (92%)
            mock_tracker = AsyncMock()
            mock_tracker.get_session_usage.return_value = {
                "total_tokens": 920,
                "prompt_tokens": 614,
                "completion_tokens": 306,
                "message_count": 12,
            }
            # #14065 review: without this a bare AsyncMock reports "recently
            # failed" (truthy default) and this test would silently exercise the
            # backoff path instead of the success path it is named for.
            mock_tracker.summarization_recently_failed.return_value = False
            protection.tracker = mock_tracker

            # Mock summarizer
            mock_summarizer = AsyncMock()
            mock_summarizer.summarize_messages.return_value = "Summary of earlier messages."
            protection.summarizer = mock_summarizer

            status = await protection.check_and_protect(
                session_id="session-1",
                model_name="gpt-4",
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                mode="auto",
                messages=messages,
            )

        assert status["warning_triggered"] is True
        assert status["summary_created"] is True
        assert len(status["summary_text"]) > 0

        # Verify summarizer was called
        mock_summarizer.summarize_messages.assert_called_once()

        # The success path must still reset the tracker — the guard added in
        # #14065 must not break working compaction.
        mock_tracker.reset_session.assert_awaited_once_with("session-1")
        assert status["summary_error"] == ""


class TestSummarizationFailureIsNotReportedAsSuccess:
    """#14065 — what happens to the session when compaction fails.

    The damage was never the failed LLM call. It was that ``reset_session`` ran
    unconditionally afterwards: the token counter went back to a fresh baseline
    while the conversation was still full, so nothing ever re-triggered and the
    session continued with the agent having silently forgotten the first half of
    the work. Every observable signal — return value, status dict, info log —
    said compaction succeeded.

    These assert the *reproduction* (a failing summarization call through the
    real ``check_and_protect`` path), not the predicate.
    """

    @staticmethod
    def _protection_at_92_percent():
        protection = ContextOverflowProtection(warning_threshold=0.80, compress_threshold=0.90)
        mock_tracker = AsyncMock()
        mock_tracker.get_session_usage.return_value = {
            "total_tokens": 920,
            "prompt_tokens": 614,
            "completion_tokens": 306,
            "message_count": 12,
        }
        # Explicit rather than left to AsyncMock's truthy default: a bare mock
        # would report "recently failed" and every test here would silently
        # exercise the backoff path instead of the one it names.
        mock_tracker.summarization_recently_failed.return_value = False
        protection.tracker = mock_tracker
        return protection, mock_tracker

    async def _run_with_failing_summarizer(self, side_effect):
        protection, mock_tracker = self._protection_at_92_percent()
        messages = [{"sender": "user", "text": f"Message {i}"} for i in range(10)]

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize_messages.side_effect = side_effect
        protection.summarizer = mock_summarizer

        with patch.object(protection, "_get_context_limit", return_value=1000):
            status = await protection.check_and_protect(
                session_id="session-1",
                model_name="gpt-4",
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                mode="auto",
                messages=messages,
            )
        return status, mock_tracker

    @pytest.mark.asyncio
    async def test_a_gateway_error_leaves_the_token_tracker_untouched(self):
        status, mock_tracker = await self._run_with_failing_summarizer(
            SummarizationFailed("summarization call failed: provider 429")
        )

        assert status["summary_created"] is False
        assert status["summary_text"] == ""
        assert "429" in status["summary_error"]
        # The load-bearing assertion: an un-reset counter is what makes the next
        # turn retry instead of proceeding on a lie.
        mock_tracker.reset_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_empty_completion_leaves_the_token_tracker_untouched(self):
        status, mock_tracker = await self._run_with_failing_summarizer(
            SummarizationFailed("LLM returned empty summary")
        )

        assert status["summary_created"] is False
        assert status["summary_text"] == ""
        assert status["summary_error"]
        mock_tracker.reset_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_placeholder_text_reaches_the_outbound_view(self):
        """The placeholder is what got injected into the conversation.

        ``summary_text`` is what the caller injects as a system message
        (``create_summary_message``). On failure it must be empty, not a
        sentence claiming the messages were summarized.
        """
        status, _ = await self._run_with_failing_summarizer(SummarizationFailed("provider timeout"))

        assert status["summary_text"] == ""
        assert "were summarized to preserve context" not in status["summary_error"]

    @pytest.mark.asyncio
    async def test_a_recent_failure_backs_off_instead_of_retrying_every_turn(self):
        """#14065 review: compaction is awaited inline under the chat timeout.

        Retrying on every turn against a provider that is already rate-limiting
        spends the whole request budget failing, times out a turn whose answer
        was already generated and stored, and — because the tracker is correctly
        not reset — never recovers. The backoff bounds it to one attempt per
        window without giving up the "stay over threshold and retry later"
        property the issue asks for.
        """
        protection, mock_tracker = self._protection_at_92_percent()
        mock_tracker.summarization_recently_failed.return_value = True

        mock_summarizer = AsyncMock()
        protection.summarizer = mock_summarizer

        with patch.object(protection, "_get_context_limit", return_value=1000):
            status = await protection.check_and_protect(
                session_id="session-1",
                model_name="gpt-4",
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                mode="auto",
                messages=[{"sender": "user", "text": f"Message {i}"} for i in range(10)],
            )

        mock_summarizer.summarize_messages.assert_not_awaited()
        assert status["summary_created"] is False
        assert "backing off" in status["summary_error"]
        mock_tracker.reset_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failure_arms_the_backoff_marker(self):
        _, mock_tracker = await self._run_with_failing_summarizer(SummarizationFailed("provider 429"))

        mock_tracker.mark_summarization_failed.assert_awaited_once_with("session-1")

    @pytest.mark.asyncio
    async def test_the_failure_survives_the_integration_seam(self):
        """``handle_message_completion`` is what production actually calls."""
        from chat_history import overflow_integration

        protection, mock_tracker = self._protection_at_92_percent()
        mock_summarizer = AsyncMock()
        mock_summarizer.summarize_messages.side_effect = SummarizationFailed("provider 503")
        protection.summarizer = mock_summarizer

        llm_response = MagicMock()
        llm_response.usage = {"prompt_tokens": 10, "completion_tokens": 5}

        with (
            patch.object(protection, "_get_context_limit", return_value=1000),
            patch.object(overflow_integration, "get_overflow_protection", return_value=protection),
        ):
            status = await overflow_integration.handle_message_completion(
                session_id="session-1",
                model_name="gpt-4",
                llm_response=llm_response,
                messages=[{"sender": "user", "text": f"Message {i}"} for i in range(10)],
                mode="auto",
            )

        assert status["summary_created"] is False
        assert "503" in status["summary_error"]
        mock_tracker.reset_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_mode_no_action(self):
        """Verify no action taken when mode is disabled."""
        protection = ContextOverflowProtection()

        with patch.object(protection, "_get_context_limit", return_value=1000):
            mock_tracker = AsyncMock()
            mock_tracker.get_session_usage.return_value = {
                "total_tokens": 950,
                "prompt_tokens": 633,
                "completion_tokens": 317,
                "message_count": 15,
            }
            protection.tracker = mock_tracker

            status = await protection.check_and_protect(
                session_id="session-1",
                model_name="gpt-4",
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                mode="disabled",
            )

        assert status["warning_triggered"] is False
        assert status["summary_created"] is False

    @pytest.mark.asyncio
    async def test_warn_only_mode_no_auto_compress(self):
        """Verify warn_only mode does not trigger auto-compression."""
        protection = ContextOverflowProtection()

        with patch.object(protection, "_get_context_limit", return_value=1000):
            mock_tracker = AsyncMock()
            mock_tracker.get_session_usage.return_value = {
                "total_tokens": 920,
                "prompt_tokens": 614,
                "completion_tokens": 306,
                "message_count": 12,
            }
            protection.tracker = mock_tracker

            status = await protection.check_and_protect(
                session_id="session-1",
                model_name="gpt-4",
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                mode="warn_only",
                messages=[{"sender": "user", "text": "Test"}],
            )

        # Warning triggered but no summary created
        assert status["warning_triggered"] is True
        assert status["summary_created"] is False

    @pytest.mark.asyncio
    async def test_token_tracking_integration(self):
        """Verify token usage is tracked when provided."""
        protection = ContextOverflowProtection()

        mock_tracker = AsyncMock()
        protection.tracker = mock_tracker

        with patch.object(protection, "_get_context_limit", return_value=1000):
            mock_tracker.get_session_usage.return_value = {
                "total_tokens": 150,
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "message_count": 1,
            }

            await protection.check_and_protect(
                session_id="session-1",
                model_name="gpt-4",
                usage={"prompt_tokens": 100, "completion_tokens": 50},
                mode="auto",
            )

        # Verify tracker.add_message_tokens was called
        mock_tracker.add_message_tokens.assert_called_once_with(
            "session-1",
            prompt_tokens=100,
            completion_tokens=50,
        )


class TestTheTrackerIsNeverResetWithoutADeliveredSummary:
    """#14065 review finding 3 — the same defect, one layer below the fix.

    ``_create_summary`` reset the tracker and *then* re-added tokens for the
    retained half. A malformed entry in that second half raised ``AttributeError``
    with the counter already cleared and the paid-for summary discarded — not a
    ``SummarizationFailed``, so ``check_and_protect``'s handler did not cover it.
    """

    @pytest.mark.asyncio
    async def test_a_malformed_retained_message_does_not_clear_the_counter(self):
        protection = ContextOverflowProtection()
        mock_tracker = AsyncMock()
        protection.tracker = mock_tracker

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize_messages.return_value = "Summary."
        protection.summarizer = mock_summarizer

        # The malformed entries sit in the retained (second) half only, so the
        # summarizer's own helpers are not what raises.
        messages = [{"sender": "user", "text": f"m{i}"} for i in range(4)] + [
            "not a dict",
            {"sender": "user", "text": None},
            {"sender": "user", "text": 12345},
            {"sender": "user", "text": "fine"},
        ]

        summary = await protection._create_summary("session-1", messages, "gpt-4")

        assert summary == "Summary."
        mock_tracker.reset_session.assert_awaited_once_with("session-1")
        assert mock_tracker.add_message_tokens.await_count == 4
