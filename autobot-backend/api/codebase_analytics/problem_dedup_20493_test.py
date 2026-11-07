# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20493: one defect at one location counts once; test files are categorised as tests."""

from pathlib import Path

import pytest

from api.codebase_analytics.problem_dedup import dedupe_same_location_problems
from utils.file_categorization import FILE_CATEGORY_CODE, FILE_CATEGORY_TEST, get_file_category


def _p(type_, line, severity="medium"):
    return {"type": type_, "line": line, "severity": severity, "description": "d"}


class TestDedupe:
    def test_long_function_and_long_method_at_one_line_count_once(self):
        out = dedupe_same_location_problems([_p("long_function", 10), _p("code_smell_long_method", 10)])
        assert [p["type"] for p in out] == ["long_function"]

    def test_the_higher_severity_survives(self):
        out = dedupe_same_location_problems([_p("long_function", 10), _p("code_smell_long_method", 10, "high")])
        assert out[0]["severity"] == "high" and out[0]["type"] == "long_function"

    def test_order_does_not_matter(self):
        out = dedupe_same_location_problems([_p("code_smell_long_method", 10, "high"), _p("long_function", 10)])
        assert [(p["type"], p["severity"]) for p in out] == [("long_function", "high")]

    def test_a_method_only_finding_is_reported_under_the_canonical_type(self):
        out = dedupe_same_location_problems([_p("code_smell_long_method", 7)])
        assert [p["type"] for p in out] == ["long_function"]

    def test_different_locations_and_other_types_are_untouched(self):
        probs = [_p("long_function", 10), _p("long_function", 90), _p("race_condition", 10)]
        assert dedupe_same_location_problems(probs) == probs

    def test_input_is_not_mutated(self):
        a, b = _p("long_function", 1), _p("code_smell_long_method", 1, "high")
        dedupe_same_location_problems([a, b])
        assert a["severity"] == "medium" and b["type"] == "code_smell_long_method"


class TestTestFilesAreTests:
    @pytest.mark.parametrize(
        "name",
        [
            "autobot-backend/x/conversation_file_manager_init_test.py",
            "scripts/workflow_scheduler_e2e_test.py",
            "pkg/test_thing.py",
            "pkg/conftest.py",
            "src/a/Widget.test.ts",
            "src/a/Widget.spec.vue",
        ],
    )
    def test_colocated_test_files(self, name):
        assert get_file_category(Path(name)) == FILE_CATEGORY_TEST

    @pytest.mark.parametrize("name", ["pkg/contest.py", "pkg/latest_result.py", "pkg/testing_utils.py", "pkg/mod.py"])
    def test_production_files_stay_code(self, name):
        assert get_file_category(Path(name)) == FILE_CATEGORY_CODE
