# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The LLM-context projection of a chat session (#18293)."""

from typing import Any, Dict

from chat_history.turn_projection import LLM_CONTEXT_TURN_LIMIT, project_turn_pairs


def _msg(sender: str, text: str, kind: str = "response", **metadata: Any) -> Dict[str, Any]:
    return {"sender": sender, "text": text, "messageType": kind, "metadata": metadata}


def test_a_completed_exchange_is_one_pair() -> None:
    messages = [_msg("user", "hi", "default"), _msg("assistant", "hello")]
    assert project_turn_pairs(messages) == [{"user": "hi", "assistant": "hello"}]


def test_every_prose_reply_in_the_turn_is_joined_and_tool_output_is_not() -> None:
    messages = [
        _msg("user", "uptime?", "default"),
        _msg("assistant", "Checking.", "iteration_prose", message_type="llm_response"),
        _msg("system", "up 3 days", "terminal_output"),
        _msg("assistant", "raw tool json", "tool_result"),
        _msg("assistant", "Up 3 days.", "terminal_interpretation"),
    ]
    assert project_turn_pairs(messages) == [{"user": "uptime?", "assistant": "Checking.\n\nUp 3 days."}]


def test_a_turn_with_no_reply_is_not_a_completed_exchange() -> None:
    messages = [
        _msg("user", "first", "default"),
        _msg("assistant", "one"),
        _msg("user", "failed turn", "default"),
        _msg("assistant", "approve?", "command_approval_request"),
        _msg("user", "in flight", "default"),
    ]
    assert project_turn_pairs(messages) == [{"user": "first", "assistant": "one"}]


def test_the_window_keeps_the_most_recent_exchanges() -> None:
    messages = []
    for i in range(LLM_CONTEXT_TURN_LIMIT + 3):
        messages += [_msg("user", f"q{i}", "default"), _msg("assistant", f"a{i}")]
    pairs = project_turn_pairs(messages)
    assert len(pairs) == LLM_CONTEXT_TURN_LIMIT
    assert pairs[0]["user"] == "q3" and pairs[-1]["user"] == f"q{LLM_CONTEXT_TURN_LIMIT + 2}"


def test_replies_before_any_user_message_and_junk_entries_are_ignored() -> None:
    messages = [_msg("assistant", "welcome"), "not a dict", _msg("user", "  ", "default"), _msg("assistant", "x")]
    assert project_turn_pairs(messages) == []


def test_an_empty_session_projects_to_nothing() -> None:
    assert project_turn_pairs([]) == []
    assert project_turn_pairs([_msg("user", "q", "default"), _msg("assistant", "a")], limit=0) == []
