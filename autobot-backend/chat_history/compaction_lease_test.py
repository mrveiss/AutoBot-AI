# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Compaction is serialised per session, and fill is the context held, not the spend (#17805, #17802)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from chat_history import context_overflow as context_overflow_module
from chat_history.context_overflow import ContextOverflowProtection


class TestCompactionLease:
    """#17805: two concurrent turns on one session produce at most one summary."""

    @pytest.mark.asyncio
    async def test_the_loser_skips_and_leaves_the_history_and_counter_alone(self, monkeypatch):
        monkeypatch.setattr(context_overflow_module, "_lease_held_elsewhere", AsyncMock(return_value=True))
        protection = ContextOverflowProtection()
        protection.tracker = AsyncMock()
        protection.tracker.summarization_recently_failed.return_value = False
        protection.summarizer = AsyncMock()
        result = {"summary_created": False, "summary_text": "", "summary_error": ""}

        await protection._attempt_summary("session-1", [{"role": "user", "content": "a"}], "m", result)

        protection.summarizer.summarize_messages.assert_not_awaited()
        protection.tracker.reset_session.assert_not_awaited()
        assert result["summary_created"] is False and result["summary_error"] == ""

    @pytest.mark.asyncio
    async def test_two_concurrent_attempts_summarize_once(self, monkeypatch):
        held = set()

        async def contested(lease):
            if lease.key in held:
                return True
            held.add(lease.key)
            return False

        monkeypatch.setattr(context_overflow_module, "_lease_held_elsewhere", contested)
        monkeypatch.setattr(context_overflow_module.LeaderLease, "release", AsyncMock())
        protection = ContextOverflowProtection()
        protection.tracker = AsyncMock()
        protection.tracker.summarization_recently_failed.return_value = False
        gate = asyncio.Event()

        async def slow_summary(*args, **kwargs):
            await gate.wait()
            return "S"

        protection.summarizer = AsyncMock()
        protection.summarizer.summarize_messages.side_effect = slow_summary
        messages = [{"sender": "user", "text": f"m{i}"} for i in range(6)]
        results = [{"summary_created": False, "summary_text": "", "summary_error": ""} for _ in range(2)]

        first = asyncio.ensure_future(protection._attempt_summary("s", messages, "m", results[0]))
        await asyncio.sleep(0)
        await protection._attempt_summary("s", messages, "m", results[1])
        gate.set()
        await first

        assert protection.summarizer.summarize_messages.await_count == 1
        assert [r["summary_created"] for r in results] == [True, False]


class TestFillIsTheContextHeldNotTheSpend:
    """#17802: the 2k-token conversation on an 8k model stays well under threshold after 5 turns."""

    @pytest.mark.asyncio
    async def test_five_same_size_turns_do_not_read_as_over_threshold(self):
        protection = ContextOverflowProtection()
        mock_tracker = AsyncMock()
        mock_tracker.get_session_usage.return_value = {
            "total_tokens": 10000,
            "active_tokens": 2000,
            "prompt_tokens": 10000,
            "completion_tokens": 0,
            "message_count": 5,
        }
        protection.tracker = mock_tracker

        with patch.object(protection, "_get_context_limit", return_value=8000):
            status = await protection.check_and_protect("session-1", "m", usage={"prompt_tokens": 2000}, mode="auto")

        assert status["current_fill_percentage"] == 0.25
        assert status["cumulative_tokens"] == 10000
        assert status["warning_triggered"] is False and status["summary_created"] is False
