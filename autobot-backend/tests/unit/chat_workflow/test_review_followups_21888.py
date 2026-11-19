# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Review follow-ups: tool timing per call, whole-token redundancy, one invalid-call limit with a deprecated alias."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chat_workflow import limits, tool_timing
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.reply_persistence import is_redundant_prose

BACKEND = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_concurrent_calls_of_one_tool_in_one_session_each_read_their_own_duration():
    async def call(seconds: float):
        tool_timing.mark_tool_started("s", "web_search")
        await asyncio.sleep(seconds)
        return tool_timing.take_tool_elapsed("s", "web_search")

    slow, fast = await asyncio.gather(call(0.2), call(0.02))
    assert slow >= 0.2 and fast < 0.15  # a shared queue would hand the slow call the fast one's start


def test_a_call_id_closes_exactly_its_own_call():
    first = tool_timing.mark_tool_started("t", "x")
    second = tool_timing.mark_tool_started("t", "x")
    assert first != second
    assert tool_timing.take_tool_elapsed("t", "x", call_id=second) is not None
    assert tool_timing.take_tool_elapsed("t", "x", call_id=second) is None  # already closed
    assert tool_timing.take_tool_elapsed("t", "x", call_id=first) is not None


def test_a_start_older_than_the_max_age_is_dropped(monkeypatch):
    token = tool_timing.mark_tool_started("u", "x")
    monkeypatch.setattr(tool_timing, "TOOL_TIMING_MAX_AGE_SECONDS", -1.0)
    tool_timing.mark_tool_started("u", "other")  # any new mark expires the stale one
    assert tool_timing.take_tool_elapsed("u", "x", call_id=token) is None


def test_a_call_that_never_marked_has_no_duration():
    assert tool_timing.take_tool_elapsed("never", "x") is None


@pytest.mark.parametrize(
    ("narration", "answer", "expected"),
    [("art", "The party starts at nine", False), ("party starts", "The party starts at nine", True)],
)
def test_redundancy_is_a_match_of_whole_tokens_not_a_substring(narration, answer, expected):
    respond = {"sender": "assistant", "text": answer, "metadata": {"message_type": "respond_tool"}}
    assert is_redundant_prose(narration, [respond]) is expected


def test_the_tools_reminder_uses_the_one_invalid_call_limit(monkeypatch):
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    monkeypatch.setattr(limits, "INVALID_CALL_LIMIT", 4)
    assert manager._build_tools_reminder(3) == ""
    assert manager._build_tools_reminder(4) != ""


def _limit_with(env: dict) -> str:
    code = "from chat_workflow import limits; print(limits.INVALID_CALL_LIMIT)"
    clean = {k: v for k, v in os.environ.items() if not k.startswith("AUTOBOT_CHAT_")}
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env={**clean, **env, "PYTHONPATH": f"{BACKEND}:{BACKEND.parent}"},
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip().splitlines()[-1]


def test_the_deprecated_budget_name_is_still_read_as_the_default_for_one_release():
    assert _limit_with({}) == "2"
    assert _limit_with({"AUTOBOT_CHAT_PARSE_RETRY_BUDGET": "5"}) == "5"
    assert _limit_with({"AUTOBOT_CHAT_PARSE_RETRY_BUDGET": "5", "AUTOBOT_CHAT_INVALID_CALL_LIMIT": "3"}) == "3"
