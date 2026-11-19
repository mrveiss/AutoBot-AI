# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The parser reports tag-present / N parsed / M failed, and one bound limits the re-asks (#21843)."""

from __future__ import annotations

from types import SimpleNamespace

from chat_workflow import limits
from chat_workflow.graph_parse_feedback import apply_parse_feedback
from chat_workflow.tool_call_args import parse_failure_step, parse_report, record_parse_failure

GOOD = """<TOOL_CALL name="execute_command" params='{"command": "ls"}'>list</TOOL_CALL>"""
BAD = """<TOOL_CALL name="browser_evaluate" params='{oops}'>run</TOOL_CALL>"""


def test_a_reply_with_no_tag_reports_no_tag():
    report = parse_report("just prose")
    assert (report.tag_present, report.parsed, report.failed) == (False, 0, 0)


def test_one_good_and_one_bad_call_are_counted():
    report = parse_report(f"{GOOD}\n{BAD}")
    assert (report.tag_present, report.parsed, report.failed) == (True, 1, 1)
    assert report.summary() == "tag present, 1 parsed, 1 failed"


def test_an_unclosed_tag_is_a_failure_with_nothing_parsed():
    report = parse_report('<TOOL_CALL name="x" params=\'{"a": 1}\'')
    assert (report.tag_present, report.parsed, report.failed) == (True, 0, 1)


def test_the_counts_reach_the_caller_in_the_step_it_feeds_back():
    step = parse_failure_step(BAD, 2)
    assert (step["parsed"], step["failed"]) == (0, 1)
    assert "tag present, 0 parsed, 1 failed" in step["error"]


def _ctx():
    return SimpleNamespace(execution_history=[], parse_failures=0)


def test_the_legacy_loop_stops_re_asking_at_the_shared_bound():
    ctx = _ctx()
    asked = [record_parse_failure(ctx, BAD, 1, max_iterations=99) for _ in range(limits.INVALID_CALL_LIMIT + 2)]
    assert asked == [True] * limits.INVALID_CALL_LIMIT + [False, False]
    assert len(ctx.execution_history) == limits.INVALID_CALL_LIMIT


def test_the_graph_path_stops_at_the_same_bound(monkeypatch):
    update = {"llm_response": BAD, "iteration_count": 1, "all_llm_responses": [BAD], "workflow_messages": []}
    assert apply_parse_feedback({"parse_retries": limits.INVALID_CALL_LIMIT - 1}, update)["parse_retry_pending"] is True
    assert apply_parse_feedback({"parse_retries": limits.INVALID_CALL_LIMIT}, update)["parse_retry_pending"] is False


def test_there_is_one_definition_of_the_bound():
    import chat_workflow.graph_parse_feedback as feedback

    assert not hasattr(feedback, "PARSE_RETRY_BUDGET")
