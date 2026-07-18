# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared test suite for the canonical `<TOOL_CALL ...>` grammar module.

Issue #11693: consolidates the two previously-independent suites
`test_tool_call_truncated_close.py` (#11552 — truncated `</TOOL` close) and
`test_tool_call_missing_gt.py` (#11545 — missing trailing `>`) into one
shared suite that exercises `chat_workflow/tool_call_grammar.py` directly,
plus the back-compat aliases both `tool_handler.py` and `manager.py`
re-export from it.

Imports the REAL compiled patterns; skips where the heavy chat_workflow
import chain isn't available in this env (runs in CI).
"""

from __future__ import annotations

import pytest


def _load_grammar():
    try:
        from chat_workflow.tool_call_grammar import (
            TOOL_CALL_BARE_CLOSE_RE,
            TOOL_CALL_COMPLETE_RE,
            TOOL_CALL_OPENING_RE,
            TOOL_CALL_PATTERN,
            strip_unparsed_tool_tags,
        )
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return (
        TOOL_CALL_PATTERN,
        TOOL_CALL_COMPLETE_RE,
        TOOL_CALL_OPENING_RE,
        TOOL_CALL_BARE_CLOSE_RE,
        strip_unparsed_tool_tags,
    )


def _pattern():
    return _load_grammar()[0]


def _completion_fires(text):
    """Mirror manager._check_tool_call_completion's structural gate (#11552):
    a well-formed close, OR a bare `</tool` close only when an opening tag is
    already present. Keeps legit `</tool>` prose from truncating a response.
    """
    _, complete_re, opening_re, bare_close_re, _ = _load_grammar()
    return bool(complete_re.search(text)) or bool(opening_re.search(text) and bare_close_re.search(text))


# --- Single-source-of-truth: tool_handler.py / manager.py re-export the ---
# --- SAME compiled objects from tool_call_grammar.py (Issue #11693). ---


def test_tool_handler_reexports_same_pattern_object():
    try:
        from chat_workflow.tool_call_grammar import TOOL_CALL_PATTERN
        from chat_workflow.tool_handler import _TOOL_CALL_PATTERN
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"chat_workflow not importable here: {exc}")
    assert _TOOL_CALL_PATTERN is TOOL_CALL_PATTERN


def test_manager_reexports_same_detector_objects():
    try:
        from chat_workflow.manager import (
            _TOOL_CALL_BARE_CLOSE_RE,
            _TOOL_CALL_COMPLETE_RE,
            _TOOL_CALL_OPENING_RE,
        )
        from chat_workflow.tool_call_grammar import (
            TOOL_CALL_BARE_CLOSE_RE,
            TOOL_CALL_COMPLETE_RE,
            TOOL_CALL_OPENING_RE,
        )
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"chat_workflow not importable here: {exc}")
    assert _TOOL_CALL_COMPLETE_RE is TOOL_CALL_COMPLETE_RE
    assert _TOOL_CALL_OPENING_RE is TOOL_CALL_OPENING_RE
    assert _TOOL_CALL_BARE_CLOSE_RE is TOOL_CALL_BARE_CLOSE_RE


# --- #11552 root cause: chat models emit a TRUNCATED closing tag `</TOOL` ---
# --- (missing `_CALL`) instead of `</TOOL_CALL>`, then hallucinate a ---
# --- success line. #11545 only made the trailing `>` optional, so ---
# --- `</TOOL` still failed to parse -> tool_calls empty -> should_stop -> ---
# --- the tool never executed (0 work items live). ---
# --- These use the EXACT body captured from the live CEO-chat E2E send. ---

LIVE_BODY = (
    'Creating task "Write Q3 financial report" with high priority.\n\n'
    '<TOOL_CALL name="create_task" params=\''
    '{"title":"Write Q3 financial report","priority":"high",'
    '"description":"Generate the Q3 financial report for the company"}'
    "'>Create task</TOOL\n\n"
    "Task 'Write Q3 financial report' created with high priority."
)


def test_parser_extracts_create_task_from_truncated_close():
    matches = list(_pattern().finditer(LIVE_BODY))
    assert len(matches) == 1, "the </TOOL truncated close must still parse"
    assert matches[0].group(1) == "create_task"
    assert '"title":"Write Q3 financial report"' in matches[0].group(3)


@pytest.mark.parametrize(
    "close",
    ["</TOOL", "</TOOL_CALL", "</TOOL_CALL>", "</tool_call>", "</TOOL_ CALL>", "</Tool "],
)
def test_parser_tolerates_all_close_variants(close):
    body = '<TOOL_CALL name="create_task" params=\'{"title":"X"}\'>desc' + close + "\nprose"
    matches = list(_pattern().finditer(body))
    assert len(matches) == 1 and matches[0].group(1) == "create_task"


def test_parser_does_not_match_bare_close_without_opening():
    # A stray </tool> in prose must never be treated as a tool call.
    assert list(_pattern().finditer("some </tool> markup in prose")) == []


def test_completion_detector_fires_on_truncated_close_after_opening():
    # With a real opening tag present, the truncated </TOOL close stops the stream
    # so the hallucinated success line is not emitted.
    assert _completion_fires(LIVE_BODY) is True
    assert _completion_fires("<TOOL_CALL name=\"create_task\" params='{}'>go</TOOL\n") is True


def test_completion_detector_still_fires_on_wellformed_close():
    assert _completion_fires("...>Create task</TOOL_CALL>\n") is True
    assert _completion_fires("...>Create task</TOOL_CALL\n") is True  # #11545 missing >


@pytest.mark.parametrize(
    "prose",
    [
        "To close the element you write </tool>.",
        "The markup uses <tool>x</tool> pairs, not real calls.",
        "I recommend the </tool-belt> naming pattern here.",
        "a bare </tool. sentence with no opening",
        "</tool_callable> is a different token entirely",
    ],
)
def test_completion_detector_does_not_fire_on_legit_prose(prose):
    # HIGH review finding: bare </tool… in ordinary prose (no opening tag) must
    # NOT truncate a general-chat response.
    assert _completion_fires(prose) is False


# --- #11545: tool-call parsing must tolerate a missing closing '>' — some ---
# --- chat models emit `</TOOL_CALL` (newline/prose after) without it, ---
# --- which previously left the whole tool call unparsed (raw tag leaked, ---
# --- tool never executed). ---

_OPEN = '<TOOL_CALL name="create_task" params=\'{"title":"X"}\'>Create task'
_WELLFORMED = _OPEN + "</TOOL_CALL>"
_MISSING_GT = _OPEN + "</TOOL_CALL\n\nHigh priority created"  # #11545: no closing '>'


def test_pattern_parses_wellformed():
    pat = _pattern()
    m = pat.search(_WELLFORMED)
    assert m and m.group(1) == "create_task" and m.group(4).strip() == "Create task"


def test_pattern_parses_missing_closing_gt():
    """The #11545 fix: `</TOOL_CALL` without `>` still parses + extracts name."""
    pat = _pattern()
    m = pat.search(_MISSING_GT)
    assert m and m.group(1) == "create_task"


def test_pattern_does_not_false_match_callable():
    pat = _pattern()
    text = "<TOOL_CALL name=\"x\" params='{}'>d</tool_callable stuff"
    # closing must be a real </tool_call> boundary, not `</tool_callable`
    m = pat.search(text)
    assert m is None


def test_complete_re_detects_missing_gt_and_wellformed_but_not_callable():
    _, complete_re, _, _, _ = _load_grammar()
    assert complete_re.search("</TOOL_CALL>") is not None
    assert complete_re.search("</TOOL_CALL\n") is not None  # #11545
    assert complete_re.search("</tool_callable>") is None


def test_two_back_to_back_calls_parse_separately_first_missing_gt():
    """#11545: two calls (first missing '>') must parse as 2 separate matches,
    not merge — the risk from making '>' optional."""
    pat = _pattern()
    text = (
        _OPEN.replace("create_task", "a")
        + "</TOOL_CALL\n"
        + '<TOOL_CALL name="b" params=\'{"y":2}\'>second</TOOL_CALL>'
    )
    matches = list(pat.finditer(text))
    assert [m.group(1) for m in matches] == ["a", "b"]
    assert matches[1].group(3) == '{"y":2}'  # second call's params intact


def test_trailing_prose_with_tool_call_mention_not_captured():
    pat = _pattern()
    text = _OPEN + "</TOOL_CALL\n\nLater I referenced </tool_call in prose."
    m = pat.search(text)
    assert m and m.group(4).strip() == "Create task"  # desc not polluted by later mention


# --- #11545 (cosmetic): strip a raw <TOOL_CALL ...> fragment from the ---
# --- final user-visible reply when it genuinely never parsed. ---


def test_strip_unparsed_tool_tags_removes_dangling_open_with_no_match():
    _, _, _, _, strip_fn = _load_grammar()
    # Malformed params (unbalanced quote) — the open tag is well-formed but
    # the FULL pattern can never close it, so it must never render raw.
    text = 'Before.\n<TOOL_CALL name="create_task" params=BROKEN>never closes'
    result = strip_fn(text)
    assert "<TOOL_CALL" not in result
    assert "Before." in result


def test_strip_unparsed_tool_tags_leaves_wellformed_call_untouched():
    _, _, _, _, strip_fn = _load_grammar()
    assert strip_fn(_WELLFORMED) == _WELLFORMED


def test_strip_unparsed_tool_tags_leaves_missing_gt_call_untouched():
    """The #11545 tolerant parser DOES match this — strip must not touch it."""
    _, _, _, _, strip_fn = _load_grammar()
    assert strip_fn(_MISSING_GT) == _MISSING_GT


def test_strip_unparsed_tool_tags_is_noop_on_plain_text():
    _, _, _, _, strip_fn = _load_grammar()
    text = "Just a normal reply with no tags at all."
    assert strip_fn(text) == text
