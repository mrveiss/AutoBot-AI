# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixture v2 (#20843): tool_match, success_criteria, and v1 compatibility."""

import json

import pytest

from eval.runner import tools_match
from eval.store import GoldenTrajectory, load_golden_set


def _fixture(**extra):
    base = {"trajectory_id": "t", "task_class": "c", "inputs": {"prompt": "p"}, "expected_tools": ["a", "b"]}
    return {**base, **extra}


def test_a_v1_fixture_still_loads_with_exact_matching_and_no_criteria():
    golden = GoldenTrajectory.from_fixture(_fixture(fixture_version="1"))
    assert golden.tool_match == "exact" and golden.success_criteria == [] and golden.criteria() == []


def test_a_v2_fixture_carries_its_match_mode_and_criteria():
    criteria = [{"type": "output_pattern", "parameters": {"pattern": "x"}, "weight": 2.0, "required": False}]
    golden = GoldenTrajectory.from_fixture(
        _fixture(fixture_version="2", tool_match="subsequence", success_criteria=criteria)
    )
    (parsed,) = golden.criteria()
    assert golden.tool_match == "subsequence"
    assert (parsed.criteria_type.value, parsed.weight, parsed.required) == ("output_pattern", 2.0, False)


@pytest.mark.parametrize(
    "extra",
    [
        {"tool_match": "fuzzy"},
        {"success_criteria": [{"type": "no_such_type"}]},
        {"success_criteria": [{"type": "custom"}]},
        {"fixture_version": "3"},
    ],
    ids=["bad-mode", "bad-type", "custom-refused", "future-version"],
)
def test_a_bad_v2_fixture_fails_the_load_not_the_run(extra):
    with pytest.raises(ValueError):
        GoldenTrajectory.from_fixture(_fixture(**extra))


def test_subsequence_allows_extra_calls_in_order_and_exact_does_not():
    assert tools_match(["a", "b"], ["a", "x", "b"], "subsequence")
    assert not tools_match(["a", "b"], ["b", "a"], "subsequence")
    assert not tools_match(["a", "b"], ["a", "x", "b"], "exact")
    assert tools_match([], ["anything"], "subsequence")


def test_the_shipped_goldens_are_v2_read_only_and_asserting():
    goldens = load_golden_set()
    assert {g.trajectory_id for g in goldens} >= {"code_fix_null_guard", "qa_deploy_role", "triage_502_websocket"}
    for golden in goldens:
        assert golden.tool_match == "subsequence" and golden.criteria(), golden.trajectory_id
        assert not set(golden.expected_tools) & {"edit_file", "write_file", "run_tests", "execute_command"}


def test_a_shipped_golden_is_valid_json_with_a_version():
    from eval.store import GOLDEN_DIR

    for path in GOLDEN_DIR.glob("*.json"):
        assert json.loads(path.read_text(encoding="utf-8"))["fixture_version"] == "2"


def test_every_shipped_golden_declares_tool_match_allowed_tools_and_two_criteria_explicitly():
    """Read the raw JSON: a default would hide an author who never decided."""
    from eval.store import GOLDEN_DIR

    paths = sorted(GOLDEN_DIR.glob("*.json"))
    assert len(paths) >= 3
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw.get("tool_match") in ("exact", "subsequence"), path.name
        assert isinstance(raw.get("allowed_tools"), list), path.name
        assert len(raw.get("success_criteria") or []) >= 2, path.name
