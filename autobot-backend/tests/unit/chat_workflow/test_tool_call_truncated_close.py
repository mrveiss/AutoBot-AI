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


def _complete_re():
    try:
        from chat_workflow.manager import _TOOL_CALL_COMPLETE_RE
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return _TOOL_CALL_COMPLETE_RE


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


def test_completion_detector_fires_on_truncated_close():
    # So streaming stops at </TOOL and the hallucinated success line is not emitted.
    assert _complete_re().search("...>Create task</TOOL\n") is not None
