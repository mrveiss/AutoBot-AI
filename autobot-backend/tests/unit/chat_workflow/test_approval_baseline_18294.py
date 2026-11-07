# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every mutating tool is approval-gated by default; only the SLM relaxes a category (#18294)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.tool_catalogue import valid_approval_categories
from chat_workflow import approval_baseline as ab
from tests.unit.chat_workflow.test_ai_line_support import run_guard

_ONE_TOOL_PER_CATEGORY = [
    ("executing code", "run_shell"),
    ("writing files", "create_file"),
    ("writing data", "set_redis_value"),
    ("browser actions", "navigate"),
    ("delegating work", "delegate"),
]


def _baseline_with(slm_value) -> list:
    with patch.object(ab, "fetch_slm_policy_json", AsyncMock(return_value=slm_value)):
        return asyncio.run(ab.baseline_approval_categories())


def _ctx(categories) -> SimpleNamespace:
    return SimpleNamespace(requires_approval_before=categories, work_item_id=None)


@pytest.mark.parametrize(("category", "tool"), _ONE_TOOL_PER_CATEGORY)
def test_a_default_run_raises_an_approval_request_for_the_category(category, tool):
    results: list = []
    msg, filed = run_guard({"name": tool, "params": {}}, _ctx([]), results)
    assert msg is not None and msg.type == "approval_required" and filed == 1
    assert results[0]["category"] == category and results[0]["status"] == "pending_approval"


@pytest.mark.parametrize("tool", ["read_file", "web_search", "list_dir", "sleep"])
def test_a_read_tool_raises_no_approval_request(tool):
    assert run_guard({"name": tool, "params": {}}, _ctx([]), []) == (None, 0)


def test_the_baseline_is_every_category_when_nothing_is_relaxed():
    assert set(_baseline_with(None)) == valid_approval_categories()
    assert set(_baseline_with([])) == valid_approval_categories()


def test_the_slm_setting_relaxes_exactly_the_named_categories():
    for value in (["browser actions"], {"categories": ["browser actions"]}):
        baseline = _baseline_with(value)
        assert "browser actions" not in baseline
        assert set(baseline) == valid_approval_categories() - {"browser actions"}
    # Relaxed by the administrator: the category floor lifts, and an unset navigate is still a
    # mutating action, so it is line 2 by the unset default -- never silently line 1.
    msg, filed = run_guard({"name": "navigate", "params": {}}, _ctx([]), [], slm_relaxed=["browser actions"])
    assert msg is not None and filed == 1 and msg.metadata["category"] is None


@pytest.mark.parametrize("bad", ["browser actions", 7, {"categories": "browser actions"}, ["no such category"]])
def test_a_malformed_setting_relaxes_nothing(bad):
    assert set(_baseline_with(bad)) == valid_approval_categories()


def test_an_unreachable_slm_fails_closed():
    assert set(_baseline_with(None)) == valid_approval_categories()


def test_a_user_cannot_relax_a_category_through_context_or_session():
    with patch.object(ab, "fetch_slm_policy_json", AsyncMock(return_value=None)):
        ctx = asyncio.run(ab.with_baseline_categories({"requires_approval_before": []}, []))
    assert set(ctx["requires_approval_before"]) == valid_approval_categories()


def test_a_session_or_context_category_extends_the_baseline_without_duplicates():
    relaxed = ["writing data"]
    with patch.object(ab, "fetch_slm_policy_json", AsyncMock(return_value=relaxed)):
        ctx = asyncio.run(
            ab.with_baseline_categories({"x": 1, "requires_approval_before": ["writing data"]}, ["publishing"])
        )
    assert ctx["x"] == 1 and "writing data" in ctx["requires_approval_before"]
    assert (
        len(ctx["requires_approval_before"])
        == len(set(ctx["requires_approval_before"]))
        == len(valid_approval_categories())
    )
