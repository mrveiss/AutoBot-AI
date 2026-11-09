# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Failure categories of a live run (#20843): one case per category, a clean control, a multi-category case.

Each case builds a record whose only deviation is the signal under test, so a category that fires on the
control, or fails to fire on its case, is a defect in the detector wiring and not in the fixture.
"""

import pytest

from chat_workflow import limits
from chat_workflow.tool_call_loop import _LOOP_ABORT_THRESHOLD
from eval.live_classify import (
    CATEGORIES,
    FALSE_DONE,
    LOOP_STALL,
    MALFORMED_TOOL_CALL,
    SUBSTANTIVE_MIN_WORDS,
    UNKNOWN_TOOL,
    UNSUPPORTED_CLAIM,
    LiveRunRecord,
    classify_failures,
    is_heuristic,
)

_GOOD_CALL = '<TOOL_CALL name="web_search" params=\'{"query": "x"}\'>look it up</TOOL_CALL>'
_BROKEN_CALL = '<TOOL_CALL name="web_search" params=\'{"query": \'>look it up'
_LONG_ANSWER = " ".join(["word"] * (SUBSTANTIVE_MIN_WORDS + 5))


def _clean(**overrides) -> LiveRunRecord:
    base = dict(final_text="a finished answer", raw_responses=["a finished answer"], criteria_overall="full")
    base.update(overrides)
    return LiveRunRecord(**base)


def test_a_clean_run_has_no_category():
    assert classify_failures(_clean()) == []


def test_a_well_formed_tool_call_is_not_malformed():
    """Control for the malformed case: the handler's own extractor parses this one."""
    assert MALFORMED_TOOL_CALL not in classify_failures(_clean(raw_responses=[_GOOD_CALL]))


def test_markers_without_a_parsed_call_are_a_malformed_tool_call():
    assert classify_failures(_clean(raw_responses=[_BROKEN_CALL])) == [MALFORMED_TOOL_CALL]


def test_a_dispatcher_unknown_tool_message_is_an_unknown_tool():
    message = {"type": "error", "content": "x", "metadata": {"message_type": "unknown_tool", "tool_name": "nope"}}
    assert classify_failures(_clean(messages=[message])) == [UNKNOWN_TOOL]


def test_the_real_unknown_tool_error_is_what_unknown_tool_looks_for():
    """Drive the dispatcher's own constructor, so a changed metadata key breaks this and not just a fixture."""
    from chat_workflow.tool_dispatch_guards import unknown_tool_error

    message = unknown_tool_error("nope", None, [], {"web_search"})
    record = _clean(messages=[{"type": message.type, "content": message.content, "metadata": message.metadata}])
    assert classify_failures(record) == [UNKNOWN_TOOL]


@pytest.mark.parametrize(
    "overrides",
    [
        {"tool_loop_count": _LOOP_ABORT_THRESHOLD},
        {"should_continue": True, "iteration_count": limits.MAX_CONTINUATION_ITERATIONS},
        {"timed_out": True},
    ],
    ids=["loop-abort-threshold", "iteration-cap-with-continue", "timeout"],
)
def test_each_stall_signal_is_a_loop_stall(overrides):
    assert classify_failures(_clean(**overrides)) == [LOOP_STALL]


def test_below_the_loop_threshold_and_cap_is_not_a_stall():
    record = _clean(tool_loop_count=_LOOP_ABORT_THRESHOLD - 1, iteration_count=limits.MAX_CONTINUATION_ITERATIONS)
    assert classify_failures(record) == []  # at the cap but not asking to continue: it finished


@pytest.mark.parametrize("verdict", ["failed", "partial"])
def test_an_answer_that_misses_its_criteria_is_false_done(verdict):
    record = _clean(criteria_overall=verdict)
    assert classify_failures(record) == [FALSE_DONE]
    assert not is_heuristic(record, FALSE_DONE)


def test_without_criteria_false_done_is_a_labelled_heuristic():
    record = _clean(criteria_overall=None, execution_history=[{"tool": "t", "status": "error"}])
    assert classify_failures(record) == [FALSE_DONE]
    assert is_heuristic(record, FALSE_DONE)


def test_without_criteria_and_with_a_success_there_is_no_false_done():
    record = _clean(
        criteria_overall=None, execution_history=[{"tool": "t", "status": "error"}, {"tool": "u", "status": "success"}]
    )
    assert classify_failures(record) == []


def test_an_empty_answer_is_not_a_false_done():
    assert FALSE_DONE not in classify_failures(_clean(final_text="", criteria_overall="failed"))


def test_an_ungrounded_substantive_answer_on_a_grounded_golden_is_an_unsupported_claim():
    record = _clean(final_text=_LONG_ANSWER, grounding_required=True)
    assert classify_failures(record) == [UNSUPPORTED_CLAIM]


@pytest.mark.parametrize(
    "overrides",
    [{"used_knowledge": True}, {"rag_citations": [{"id": "1"}]}, {"grounding_required": False}, {"final_text": "ok"}],
    ids=["knowledge-used", "cited", "golden-needs-no-grounding", "not-substantive"],
)
def test_grounding_evidence_or_no_need_for_it_is_not_an_unsupported_claim(overrides):
    base = {"final_text": _LONG_ANSWER, "grounding_required": True}
    assert UNSUPPORTED_CLAIM not in classify_failures(_clean(**{**base, **overrides}))


def test_a_judge_verdict_alone_makes_an_unsupported_claim():
    assert classify_failures(_clean(judge_unsupported=True)) == [UNSUPPORTED_CLAIM]


def test_several_categories_are_reported_together_in_catalogue_order():
    record = _clean(
        raw_responses=[_BROKEN_CALL],
        timed_out=True,
        criteria_overall="failed",
        final_text=_LONG_ANSWER,
        grounding_required=True,
    )
    found = classify_failures(record)
    assert found == [MALFORMED_TOOL_CALL, LOOP_STALL, FALSE_DONE, UNSUPPORTED_CLAIM]
    assert found == [c for c in CATEGORIES if c in found]
