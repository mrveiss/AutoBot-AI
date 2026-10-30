# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pure session-trace projection (#19963): holds, refusals, runs, and what is unknown."""

import pytest

from chat_history import session_trace
from chat_history.session_trace import approval_refs, project_session_trace

GATE = ("gate", "7c1f0e52-0000-4000-8000-000000000001")
TERMINAL = ("terminal", "term-1")


def _msg(sender, text, kind, **meta):
    return {"id": f"{kind}-{len(text)}", "sender": sender, "text": text, "messageType": kind, "metadata": meta}


def _reply(text, iteration, model=""):
    return _msg("assistant", text, "response", message_type="llm_response", iteration=iteration, model=model)


def _held_terminal_turn():
    return [
        _msg("user", "list the dir", "default"),
        _reply("I will run ls", 1),
        _msg(
            "assistant",
            "needs approval",
            "command_approval_request",
            command="ls -la",
            terminal_session_id=TERMINAL[1],
            iteration=1,
        ),
        _reply("waiting", 2, model="m-1"),
    ]


def test_held_terminal_call_shows_its_approval_and_no_result_returned():
    turns = project_session_trace(_held_terminal_turn(), {TERMINAL: "pending_approval"})
    call = turns[0]["iterations"][0]["tool_calls"][0]
    assert call["tool"] == "terminal"
    assert call["verdict"] == "held"
    assert call["approval"] == {"id": "term-1", "kind": "terminal", "state": "pending_approval"}
    assert call["result_returned"] == "no"
    assert call["params"]["command"] == "ls -la"


def test_held_call_whose_approval_state_is_unread_reads_unknown_not_no():
    call = project_session_trace(_held_terminal_turn())[0]["iterations"][0]["tool_calls"][0]
    assert call["approval"]["state"] == "unknown"
    assert call["result_returned"] == "unknown"


def test_approved_hold_does_not_claim_the_result_reached_the_model():
    call = project_session_trace(_held_terminal_turn(), {TERMINAL: "completed"})[0]["iterations"][0]["tool_calls"][0]
    assert call["verdict"] == "held"
    assert call["result_returned"] == "unknown"


def test_turn_model_comes_from_the_last_prose_entry_and_earlier_iterations_report_none():
    turn = project_session_trace(_held_terminal_turn())[0]
    assert turn["model"] == "m-1"
    assert [(i["iteration"], i["model"]) for i in turn["iterations"]] == [(1, None), (2, "m-1")]


def test_refused_call_and_ran_call_in_one_turn():
    messages = [
        _msg("user", "go", "default"),
        _msg("assistant", "blocked", "error", tool="rm", line="floor", category="destructive", error=True, iteration=1),
        _msg("assistant", "out", "tool_result", tool_name="compose", run_id="r1", iteration=2),
    ]
    refused, ran = (c for i in project_session_trace(messages)[0]["iterations"] for c in i["tool_calls"])
    assert (refused["verdict"], refused["result_returned"]) == ("refused", "no")
    assert (ran["verdict"], ran["result_returned"]) == ("ran", "unknown")


def test_gate_hold_carries_the_gate_id_and_a_rejected_state():
    messages = [
        _msg("user", "go", "default"),
        _msg("assistant", "needs approval", "approval_required", tool="compose", approval_id=GATE[1], iteration=1),
    ]
    assert approval_refs(messages) == [GATE]
    call = project_session_trace(messages, {GATE: "rejected"})[0]["iterations"][0]["tool_calls"][0]
    assert call["approval"] == {"id": GATE[1], "kind": "gate", "state": "rejected"}
    assert call["result_returned"] == "no"


def test_output_and_params_are_redacted():
    messages = [
        _msg("user", "go", "default"),
        _msg(
            "assistant",
            "token=abc123supersecret done",
            "tool_result",
            tool_name="x",
            command="curl -H 'password=hunter2'",
        ),
    ]
    call = project_session_trace(messages)[0]["iterations"][0]["tool_calls"][0]
    assert "abc123supersecret" not in call["output"]
    assert "hunter2" not in str(call["params"])


def test_output_is_capped(monkeypatch):
    monkeypatch.setattr(session_trace, "TRACE_OUTPUT_MAX_CHARS", 10)
    messages = [_msg("user", "go", "default"), _msg("assistant", "y" * 50, "tool_result", tool_name="x")]
    assert len(project_session_trace(messages)[0]["iterations"][0]["tool_calls"][0]["output"]) == 10


def test_turns_split_on_user_messages_and_malformed_entries_are_skipped():
    messages = [_msg("user", "a", "default"), "junk", _reply("r", 1), _msg("user", "b", "default"), _reply("r2", 1)]
    turns = project_session_trace(messages)
    assert [t["turn"] for t in turns] == [1, 2]
    assert all(t["iterations"][0]["replied"] for t in turns)


@pytest.mark.parametrize(
    "leak",
    [
        "postgres://admin:%s@db/x",  # pragma: allowlist secret
        '{"password": "%s"}',  # pragma: allowlist secret
        "password=%s",  # pragma: allowlist secret
        "-----BEGIN PRIVATE KEY-----\n%s\n-----END PRIVATE KEY-----",  # pragma: allowlist secret
    ],
)
def test_each_secret_shape_leaves_neither_output_nor_a_command_param(leak):
    secret = "hunter2-very-secret"  # pragma: allowlist secret
    text = leak % secret
    message = {
        "sender": "assistant",
        "messageType": "tool_result",
        "text": text,
        "metadata": {"tool": "t", "iteration": 1, "command": text},
    }
    assert secret not in str(project_session_trace([{"sender": "user", "text": "go"}, message], {}))
