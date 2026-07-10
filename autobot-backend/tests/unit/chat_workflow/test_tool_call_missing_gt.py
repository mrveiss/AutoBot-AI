# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11545: tool-call parsing must tolerate a missing closing '>' — some chat
models emit `</TOOL_CALL` (newline/prose after) without it, which previously
left the whole tool call unparsed (raw tag leaked, tool never executed).

Imports the REAL compiled patterns; skips where the heavy chat_workflow import
chain isn't available in this env (runs in CI).
"""

from __future__ import annotations

import pytest


def _load_patterns():
    try:
        from chat_workflow.manager import _TOOL_CALL_COMPLETE_RE
        from chat_workflow.tool_handler import _TOOL_CALL_PATTERN
    except Exception as exc:  # noqa: BLE001 — env-dependent import chain
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return _TOOL_CALL_PATTERN, _TOOL_CALL_COMPLETE_RE


_OPEN = "<TOOL_CALL name=\"create_task\" params='{\"title\":\"X\"}'>Create task"
_WELLFORMED = _OPEN + "</TOOL_CALL>"
_MISSING_GT = _OPEN + "</TOOL_CALL\n\nHigh priority created"  # #11545: no closing '>'


def test_pattern_parses_wellformed():
    pat, _ = _load_patterns()
    m = pat.search(_WELLFORMED)
    assert m and m.group(1) == "create_task" and m.group(4).strip() == "Create task"


def test_pattern_parses_missing_closing_gt():
    """The #11545 fix: `</TOOL_CALL` without `>` still parses + extracts name."""
    pat, _ = _load_patterns()
    m = pat.search(_MISSING_GT)
    assert m and m.group(1) == "create_task"


def test_pattern_does_not_false_match_callable():
    pat, _ = _load_patterns()
    text = "<TOOL_CALL name=\"x\" params='{}'>d</tool_callable stuff"
    # closing must be a real </tool_call> boundary, not `</tool_callable`
    m = pat.search(text)
    assert m is None


def test_complete_re_detects_missing_gt_and_wellformed_but_not_callable():
    _, complete = _load_patterns()
    assert complete.search("</TOOL_CALL>") is not None
    assert complete.search("</TOOL_CALL\n") is not None  # #11545
    assert complete.search("</tool_callable>") is None
