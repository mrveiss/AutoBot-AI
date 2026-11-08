# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20493: one defect at one location counts once; test files are categorised as tests."""

import ast
from pathlib import Path

import pytest

from api.codebase_analytics import analyzers
from api.codebase_analytics.problem_dedup import dedupe_same_location_problems
from autobot_shared.status_enums import Severity
from utils.file_categorization import FILE_CATEGORY_CODE, FILE_CATEGORY_TEST, get_file_category

LOW, MEDIUM, HIGH = (Severity.LOW.value, Severity.MEDIUM.value, Severity.HIGH.value)


def _p(type_, line, severity=MEDIUM):
    return {"type": type_, "line": line, "severity": severity, "description": "d"}


class TestDedupe:
    def test_long_function_and_long_method_at_one_line_count_once(self):
        out = dedupe_same_location_problems([_p("long_function", 10), _p("code_smell_long_method", 10)])
        assert [p["type"] for p in out] == ["long_function"]

    def test_the_higher_severity_survives(self):
        out = dedupe_same_location_problems([_p("long_function", 10), _p("code_smell_long_method", 10, HIGH)])
        assert out[0]["severity"] == HIGH and out[0]["type"] == "long_function"

    def test_order_does_not_matter(self):
        out = dedupe_same_location_problems([_p("code_smell_long_method", 10, HIGH), _p("long_function", 10)])
        assert [(p["type"], p["severity"]) for p in out] == [("long_function", HIGH)]

    def test_a_method_only_finding_is_reported_under_the_canonical_type(self):
        out = dedupe_same_location_problems([_p("code_smell_long_method", 7)])
        assert [p["type"] for p in out] == ["long_function"]

    def test_different_locations_and_other_types_are_untouched(self):
        probs = [_p("long_function", 10), _p("long_function", 90), _p("race_condition", 10)]
        assert dedupe_same_location_problems(probs) == probs

    @pytest.mark.parametrize("missing", [{}, {"line": None}, {"line": 0}])
    def test_findings_without_a_line_are_never_merged(self, missing):
        a = {"type": "long_function", "severity": LOW, **missing}
        b = {"type": "code_smell_long_method", "severity": HIGH, **missing}
        out = dedupe_same_location_problems([a, b])
        assert [p["type"] for p in out] == ["long_function", "long_function"]
        assert [p["severity"] for p in out] == [LOW, HIGH]

    def test_input_is_not_mutated(self):
        a, b = _p("long_function", 1), _p("code_smell_long_method", 1, HIGH)
        dedupe_same_location_problems([a, b])
        assert a["severity"] == MEDIUM and b["type"] == "code_smell_long_method"


class TestEveryTypeCountsOncePerLocation:
    def test_the_same_type_twice_at_one_line_counts_once_with_the_higher_severity(self):
        out = dedupe_same_location_problems([_p("code_smell_deep_nesting", 4), _p("code_smell_deep_nesting", 4, HIGH)])
        assert [(p["type"], p["severity"]) for p in out] == [("code_smell_deep_nesting", HIGH)]

    def test_the_same_line_of_two_files_is_two_defects(self):
        a, b = dict(_p("debug_code", 3), file_path="a.py"), dict(_p("debug_code", 3), file_path="b.py")
        assert len(dedupe_same_location_problems([a, b])) == 2

    def test_a_multi_file_list_collapses_per_file(self):
        mk = lambda t, f: dict(_p(t, 8), file_path=f)  # noqa: E731
        probs = [mk("long_function", "a.py"), mk("code_smell_long_method", "a.py"), mk("long_function", "b.py")]
        assert [p["file_path"] for p in dedupe_same_location_problems(probs)] == ["a.py", "b.py"]


class TestReadPathAppliesTheDedupe:
    """Findings stored before the write-path dedupe must not double on read."""

    def test_stored_duplicates_are_collapsed_when_read(self, monkeypatch):
        from api.codebase_analytics.endpoints import stats

        meta = [
            {"problem_type": "long_function", "severity": "medium", "file_path": "a.py", "line_number": 5},
            {"problem_type": "code_smell_long_method", "severity": "high", "file_path": "a.py", "line_number": 5},
        ]
        monkeypatch.setattr(stats, "get_all_paginated", lambda *a, **k: {"metadatas": meta})
        monkeypatch.setattr(stats, "filter_problems_by_file_existence", lambda problems, root: problems)
        out = stats._fetch_problems_from_chromadb(object(), None, source_root=Path("."))
        assert [(p["type"], p["severity"]) for p in out] == [("long_function", "high")]


class TestAnalysisPhasesApplyTheDedupe:
    """Deleting the call in ``_run_analysis_phases`` must fail this test."""

    @pytest.mark.asyncio
    async def test_run_analysis_phases_returns_one_problem_per_defect(self, monkeypatch):
        dup = [_p("long_function", 5), _p("code_smell_long_method", 5, HIGH)]
        monkeypatch.setattr(analyzers, "_analyze_ast_nodes", lambda tree: ([], [], [], list(dup)))
        monkeypatch.setattr(analyzers, "_analyze_content_lines", lambda c, f: ([], [], []))
        monkeypatch.setattr(analyzers, "detect_race_conditions", lambda t, c, f: [])
        monkeypatch.setattr(analyzers, "_run_code_intelligence_analyzers", lambda f: [])
        monkeypatch.setattr(analyzers, "_count_python_line_types", lambda c, t: {})
        result = await analyzers._run_analysis_phases("m.py", "", ast.parse(""), use_llm=False)
        assert [(p["type"], p["severity"]) for p in result["problems"]] == [("long_function", HIGH)]


class TestTestFilesAreTests:
    @pytest.mark.parametrize(
        "name",
        [
            "autobot-backend/x/conversation_file_manager_init_test.py",
            "scripts/workflow_scheduler_e2e_test.py",
            "pkg/test_thing.py",
            "pkg/conftest.py",
            "pkg/tests.py",
            "src/a/Widget.test.ts",
            "src/a/Widget.spec.vue",
        ],
    )
    def test_colocated_test_files(self, name):
        assert get_file_category(Path(name)) == FILE_CATEGORY_TEST

    @pytest.mark.parametrize(
        "name",
        [
            "pkg/contest.py",
            "pkg/latest_result.py",
            "pkg/testing_utils.py",
            "pkg/attestation.py",
            "pkg/attachment_test_support_19756.py",
            "pkg/mod.py",
        ],
    )
    def test_production_files_stay_code(self, name):
        assert get_file_category(Path(name)) == FILE_CATEGORY_CODE


class TestNameRuleIsByNameOnly:
    """The documented rule: a name decides, so a ``test_*.py`` production module is a test."""

    def test_a_production_module_named_test_x_is_classed_as_a_test(self):
        assert get_file_category(Path("pkg/test_runner.py")) == FILE_CATEGORY_TEST

    def test_the_js_alternatives_are_dotted_not_underscored(self):
        from autobot_shared.testfile_names import is_test_filename

        assert is_test_filename("widget.test.ts") and not is_test_filename("widget_test.ts")
        assert not is_test_filename("widget.test.ts", include_js=False)
