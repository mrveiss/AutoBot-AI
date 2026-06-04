# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for context overflow protection. Issue #9043."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_history.context_overflow import (
    ContextOverflowProtection,
    ConversationSummarizer,
    SessionTokenTracker,
)


class TestSessionTokenTracker:
    """Test token tracking functionality."""

    @pytest.mark.asyncio
    async def test_add_and_get_session_tokens(self):
        """Verify token accumulation across multiple messages."""
        tracker = SessionTokenTracker()

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {
            b"total_tokens": b"300",
            b"prompt_tokens": b"200",
            b"completion_tokens": b"100",
            b"message_count": b"2",
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
    async def test_summarize_llm_failure_fallback(self):
        """Verify fallback when LLM fails."""
        summarizer = ConversationSummarizer()

        messages = [{"sender": "user", "text": "Hello"}]

        mock_gateway = AsyncMock()
        mock_gateway.chat_completion.side_effect = Exception("LLM error")

        with patch.object(summarizer, "_get_gateway", side_effect=Exception("LLM error")):
            summary = await summarizer.summarize_messages(messages, "gpt-4")

        # Should return fallback placeholder
        assert "Summary" in summary
        assert "1 earlier message" in summary


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
