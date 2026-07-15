# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11552 root cause: chat models emit a TRUNCATED closing tag `</TOOL`
(missing `_CALL`) instead of `</TOOL_CALL>`, then hallucinate a success line.
#11545 only made the trailing `>` optional, so `</TOOL` still failed to parse →
tool_calls empty → should_stop → the tool never executed (0 work items live).

These use the EXACT body captured from the live CEO-chat E2E send.
"""

from __future__ import annotations

import pytest

# The verbatim assistant body persisted by the live managed backend (2026-07-11).
LIVE_BODY = (
    'Creating task "Write Q3 financial report" with high priority.\n\n'
    '<TOOL_CALL name="create_task" params=\''
    '{"title":"Write Q3 financial report","priority":"high",'
    '"description":"Generate the Q3 financial report for the company"}'
    "'>Create task</TOOL\n\n"
    "Task 'Write Q3 financial report' created with high priority."
)


def _pattern():
    try:
        from chat_workflow.tool_handler import _TOOL_CALL_PATTERN
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return _TOOL_CALL_PATTERN


def _completion_fires(text):
    """Mirror manager._check_tool_call_completion's structural gate (#11552):
    a well-formed close, OR a bare `</tool` close only when an opening tag is
    already present. Keeps legit `</tool>` prose from truncating a response.
    """
    try:
        from chat_workflow.manager import (
            _TOOL_CALL_BARE_CLOSE_RE,
            _TOOL_CALL_COMPLETE_RE,
            _TOOL_CALL_OPENING_RE,
        )
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return bool(_TOOL_CALL_COMPLETE_RE.search(text)) or bool(
        _TOOL_CALL_OPENING_RE.search(text) and _TOOL_CALL_BARE_CLOSE_RE.search(text)
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
