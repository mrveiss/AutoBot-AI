# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Older continuation steps collapse to a digest and an anchor; the newest stay whole (#16621)."""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from agent_loop.tool_output_spill import read_spilled
from chat_workflow import step_collapse
from chat_workflow.manager import ChatWorkflowManager

RUN = "run-16621"


@pytest.fixture(autouse=True)
def _bound_run(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOBOT_TOOL_OUTPUT_SPILL_ROOT", str(tmp_path))
    with patch.object(step_collapse, "current_task_id", return_value=RUN):
        yield


def _history(count: int = 6) -> list[dict]:
    return [
        {"command": f"cmd{i}", "status": "success", "stdout": f"START{i} " + "x" * 5000 + f" END{i}"}
        for i in range(1, count + 1)
    ]


def _render(keep: int) -> list[str]:
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    with patch.object(step_collapse, "KEEP_FULL_STEPS", keep):
        return step_collapse.render_history(manager._format_execution_step, _history())


def test_with_two_kept_the_first_four_are_digests_and_the_last_two_are_whole():
    parts = _render(2)
    for older in parts[:4]:
        assert "collapsed" in older and "read_spilled_output" in older and len(older) < 1500
    for newest in parts[4:]:
        assert "collapsed" not in newest and "x" * 5000 in newest


def test_a_collapsed_steps_full_output_is_readable_through_its_anchor():
    collapsed = _render(2)[0]
    anchor = re.search(r"anchor '([^']+)'", collapsed).group(1)
    full = read_spilled(anchor, task_id=RUN)
    assert full.startswith("START1 ") and full.endswith(" END1") and len(full) > 5000
    assert "START1" in collapsed and "END1" in collapsed, "head and tail stay in the digest"


def test_a_short_step_and_an_unbound_run_are_left_whole():
    short = {"command": "ls", "status": "success", "stdout": "a b c"}
    assert step_collapse.collapse_result(short) is short
    with patch.object(step_collapse, "current_task_id", return_value=None):
        long = _history(1)[0]
        assert step_collapse.collapse_result(long) is long
