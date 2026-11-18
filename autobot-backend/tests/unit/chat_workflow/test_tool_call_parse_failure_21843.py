# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A TOOL_CALL whose args fail to parse is fed back, never persisted raw (#21843)."""

from __future__ import annotations

from chat_workflow.tool_call_args import (
    clean_reply_text,
    parse_failure_step,
    parse_tool_args,
    tool_call_parse_error,
)

_JS = "{'expression': 'document.querySelector('a').click()'  oops}"
BAD = f"""THOUGHT: click it
<TOOL_CALL name="browser_evaluate" params='{_JS}'>run</TOOL_CALL>"""
GOOD = """<TOOL_CALL name="execute_command" params='{"command": "ls"}'>list</TOOL_CALL>"""


def test_apostrophes_inside_single_quoted_values_are_recovered():
    raw = "{'expression': 'document.querySelector('a').click()'}"
    assert parse_tool_args(raw) == {"expression": "document.querySelector('a').click()"}


def test_multi_entry_apostrophe_dict():
    assert parse_tool_args("{'a': 'it's', 'b': 'x'}") == {"a": "it's", "b": "x"}


def test_raw_newline_in_json_string_parses():
    assert parse_tool_args('{"command": "a\nb"}') == {"command": "a\nb"}


def test_unrecoverable_args_report_error():
    assert "not valid JSON" in tool_call_parse_error(BAD)
    assert tool_call_parse_error(GOOD) is None
    assert tool_call_parse_error("plain prose") is None


def test_unclosed_tag_reports_error():
    assert "malformed" in tool_call_parse_error('<TOOL_CALL name="x" params=\'{"a": 1}\'>no close')


def test_failure_step_is_an_error_history_entry():
    step = parse_failure_step(BAD, iteration=2)
    assert step["status"] == "error" and "not executed" in step["error"]
    assert parse_failure_step(GOOD, 2) is None


def test_plan_first_deferral_is_not_a_failure():
    assert parse_failure_step("[PLANNING] 1. do it\n" + GOOD, iteration=1) is None


def test_raw_markup_never_survives_into_reply():
    cleaned = clean_reply_text(BAD)
    assert "TOOL_CALL" not in cleaned and "THOUGHT: click it" in cleaned
    assert clean_reply_text(GOOD) == GOOD


def test_unhashable_dict_key_is_a_parse_error_not_a_crash():
    """`{[1]:2}` makes ast.literal_eval raise TypeError (#21843)."""
    reply = """<TOOL_CALL name="x" params='{[1]:2}'>go</TOOL_CALL>"""
    assert "not valid JSON" in tool_call_parse_error(reply)
    assert parse_failure_step(reply, 2)["tool"] == "tool_call_parse"
    assert "TOOL_CALL" not in clean_reply_text(reply)


def test_deeply_nested_args_are_a_parse_error_not_a_crash():
    deep = "[" * 200_000 + "]" * 200_000
    reply = f"""<TOOL_CALL name="x" params='{deep}'>go</TOOL_CALL>"""
    assert tool_call_parse_error(reply) is not None
    assert "TOOL_CALL" not in clean_reply_text(reply)


def test_lenient_parser_keeps_every_entry_key_as_the_models_own_text():
    """A value that spells `', 'key': '` becomes a sibling key; the dispatcher validates keys against the tool."""
    raw = "{'a': 'it's', 'injected': 'x', 'b': 'y'}"
    assert parse_tool_args(raw) == {"a": "it's", "injected": "x", "b": "y"}
