# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20493: `/problems` category filter and where read-path dedup lives."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.codebase_analytics.endpoints import stats as stats_mod
from api.codebase_analytics.problem_query import ProblemCategory, problem_where, select_category
from autobot_shared.status_enums import Severity

MEDIUM, HIGH = Severity.MEDIUM.value, Severity.HIGH.value


def _row(ptype, severity=MEDIUM, category=None, line=5, path="a.py"):
    row = {"problem_type": ptype, "severity": severity, "file_path": path, "line_number": line, "description": "d"}
    if category:
        row["file_category"] = category
    return row


class _Collection:
    def __init__(self, rows):
        self.rows = rows


def _patched(rows, root=Path(".")):
    """Stand-ins that check their arguments: the collection read, the query shape and the validation root."""

    def paginated(collection, where=None, include=None, **_kw):
        assert isinstance(collection, _Collection) and collection.rows is rows, "the read must use the collection"
        assert {"type": "problem"} in (where or {}).get("$and", [where]), "the query must select problem rows"
        assert include == ["metadatas"]
        return {"metadatas": rows}

    def existing(problems, validation_root):
        assert validation_root == root, "paths are validated against the source's own root"
        return problems

    return (
        patch.object(stats_mod, "get_all_paginated", paginated),
        patch.object(stats_mod, "filter_problems_by_file_existence", existing),
    )


class TestWhere:
    def test_test_category_is_pushed_down(self):
        assert {"file_category": "test"} in problem_where("s", None, "test")["$and"]

    @pytest.mark.parametrize("category", ["code", "all", None])
    def test_code_all_and_none_are_not_pushed_down(self, category):
        assert "file_category" not in json.dumps(problem_where("s", None, category))

    def test_junk_is_not_a_category(self):
        with pytest.raises(ValueError):
            ProblemCategory("bogus")


class TestSelect:
    def test_legacy_rows_without_a_category_read_as_code(self):
        legacy, test = {"type": "a"}, {"type": "b", "file_category": "test"}
        assert select_category([legacy, test], "code") == [legacy]
        assert select_category([legacy, test], "test") == [test]

    def test_all_keeps_everything(self):
        rows = [{"type": "a"}, {"type": "b", "file_category": "test"}]
        assert select_category(rows, "all") == rows


class TestFetchReachesTheWhere:
    """#21782: ``problem_type`` and the source clause are not dropped between the route and the read."""

    def test_problem_type_and_source_reach_problem_where_and_the_fetch(self):
        seen = {}

        def fetch(_collection, where=None, include=None):
            seen["where"] = where
            return {"metadatas": []}

        with patch.object(stats_mod, "get_all_paginated", fetch):
            stats_mod._fetch_problems_from_chromadb(_Collection([]), "race_condition", "src-1", Path("."), "test")
        clauses = seen["where"]["$and"]
        assert {"source_id": "src-1"} in clauses
        assert {"problem_type": "race_condition"} in clauses
        assert {"file_category": "test"} in clauses

    def test_problem_where_keeps_both_clauses(self):
        clauses = problem_where("src-2", "debug_code", None)["$and"]
        assert {"source_id": "src-2"} in clauses and {"problem_type": "debug_code"} in clauses


class TestCategoryIsAppliedBeforeParsing:
    def test_a_bad_line_number_in_another_category_does_not_fail_the_request(self):
        """#21782: a test-file row with a non-numeric line must not 503 a ``code`` request."""
        rows = [_row("long_function"), _row("debug_code", category="test", line="n/a")]
        p1, p2 = _patched(rows)
        parsed = []
        real = stats_mod._parse_problem_metadata

        def spy(metadata):
            parsed.append(metadata)
            return real(metadata)

        with p1, p2, patch.object(stats_mod, "_parse_problem_metadata", spy):
            out = stats_mod._fetch_problems_from_chromadb(_Collection(rows), None, "s", Path("."), "code")
        assert [p["type"] for p in out] == ["long_function"]
        assert [m["problem_type"] for m in parsed] == ["long_function"], "only the code row is ever parsed"

    def test_a_non_numeric_line_is_no_line_when_every_category_is_read(self):
        rows = [_row("debug_code", line="n/a")]
        p1, p2 = _patched(rows)
        with p1, p2:
            out = stats_mod._fetch_problems_from_chromadb(_Collection(rows), None, "s", Path("."), "all")
        assert out[0]["line_number"] is None

    def test_legacy_rows_without_a_category_still_read_as_code(self):
        rows = [_row("long_function")]
        p1, p2 = _patched(rows)
        with p1, p2:
            out = stats_mod._fetch_problems_from_chromadb(_Collection(rows), None, "s", Path("."), "code")
        assert len(out) == 1


class TestWhereDedupRuns:
    def test_the_shared_fetch_stays_raw_for_other_readers(self):
        rows = [_row("long_function"), _row("code_smell_long_method", HIGH)]
        p1, p2 = _patched(rows)
        with p1, p2:
            out = stats_mod._fetch_problems_from_chromadb(_Collection(rows), None, source_id="s", source_root=Path("."))
        assert len(out) == 2

    @pytest.mark.asyncio
    async def test_the_problems_route_returns_one_defect_once(self):
        rows = [_row("long_function"), _row("code_smell_long_method", HIGH), _row("long_function", category="test")]
        p1, p2 = _patched(rows)
        with (
            p1,
            p2,
            patch.object(stats_mod, "get_code_collection", return_value=_Collection(rows)),
            patch.object(stats_mod, "resolve_scan_root", new=AsyncMock(return_value=Path("."))),
            patch.object(stats_mod, "index_state", return_value={"status": "success", "indexed": True}),
        ):
            body = json.loads(
                (await stats_mod.get_codebase_problems(source_id="s", file_category=ProblemCategory.CODE)).body
            )
        assert [(p["type"], p["severity"]) for p in body["problems"]] == [("long_function", HIGH)]


class TestReportPathDedup:
    def test_the_report_fetch_returns_one_defect_once(self):
        from api.codebase_analytics.endpoints import report as report_mod

        rows = [_row("long_function"), _row("code_smell_long_method", HIGH)]
        with (
            patch.object(report_mod, "get_code_collection", return_value=_Collection(rows)),
            patch.object(report_mod, "get_all_paginated", lambda *a, **k: {"metadatas": rows}),
            patch.object(report_mod, "filter_problems_by_file_existence", lambda p, _r: p),
        ):
            out = report_mod._fetch_problems_from_chromadb("s", Path("."))
        assert [(p["type"], p["severity"]) for p in out] == [("long_function", HIGH)]


class TestProblemsRouteHttp:
    def test_a_bad_file_category_is_422(self):
        app = FastAPI()
        app.include_router(stats_mod.router)
        resp = TestClient(app).get("/problems", params={"file_category": "bogus"})
        assert resp.status_code == 422
