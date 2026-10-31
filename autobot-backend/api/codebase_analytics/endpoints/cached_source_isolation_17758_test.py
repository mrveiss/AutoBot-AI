# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Two sources cannot read each other's cached analysis (#17758).

The reported symptom was a project's analytics page showing another project's
dependency and import-tree data. The mechanism was one Redis key:
``{prefix}latest_task_id``, written by whichever ``*/analyze`` ran last and read
by every ``*/cached`` request regardless of which source it named.

These tests assert the two halves that matter behaviourally -- the read is
scoped, and the parameter that scopes it cannot be omitted -- rather than
asserting the presence of a call, which would pass on a scoped read paired with
an unscoped write.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.codebase_analytics.source_scope import source_scoped_prefix

_CACHED = {
    "dependencies": ("api.codebase_analytics.endpoints.dependencies", "get_cached_dependency_result"),
    "import_tree": ("api.codebase_analytics.endpoints.import_tree", "get_cached_import_tree_result"),
    "duplicates": ("api.codebase_analytics.endpoints.duplicates", "get_cached_duplicate_result"),
}


class TestThePrefixBuilder:
    """One builder, so the read and the write cannot disagree."""

    def test_two_sources_get_two_prefixes(self):
        assert source_scoped_prefix("codebase:deps:", "A") != source_scoped_prefix("codebase:deps:", "B")

    def test_the_source_appears_in_the_key_with_its_dimension(self):
        """The dimension is in the key, not only the value.

        Without it, a prefix keyed by `source_id` and one keyed by `path`
        (code_intelligence's security score) share a namespace, and coinciding
        values serve one analysis as the other.
        """
        assert source_scoped_prefix("codebase:deps:", "src-A") == "codebase:deps:source_id:src-A:"

    @pytest.mark.parametrize("hostile", ["*", "?", "a*", "[abc]", "../x", "a/b", "a:b", "a\\b"])
    def test_a_glob_or_separator_is_refused(self, hostile):
        """Rejecting only the empty string left the destructive path open.

        `source_id=*` builds `codebase:*:*`, which SCAN MATCH expands to every
        project -- and the delete path deletes them. That is #17758's worst
        variant re-entered through the VALUE rather than the absence, so the
        shape has to be constrained, not just the emptiness.
        """
        with pytest.raises(ValueError, match="malformed"):
            source_scoped_prefix("codebase:deps:", hostile)

    def test_a_uuid_is_accepted(self):
        """The contrast case: the real id format must still work."""
        import uuid as _uuid

        sid = str(_uuid.uuid4())
        assert source_scoped_prefix("codebase:deps:", sid).endswith(f"{sid}:")

    @pytest.mark.parametrize("empty", ["", None])
    def test_an_absent_source_is_refused_not_globalised(self, empty):
        """The `if source_id else PREFIX` shape is the same leak, narrower.

        Returning the unscoped prefix here would reintroduce #17758 for every
        caller that omits the parameter -- which is how the sites still recorded
        in `_KNOWN_UNSCOPED_FALLBACKS` behave.
        """
        with pytest.raises(ValueError, match="source_id"):
            source_scoped_prefix("codebase:deps:", empty)


class TestEachCachedEndpointReadsItsOwnSourcesKey:
    """The behavioural claim: the prefix reaching Redis carries the source."""

    @pytest.mark.parametrize("module_name,fn_name", list(_CACHED.values()), ids=list(_CACHED))
    async def test_two_sources_read_two_different_keys(self, module_name, fn_name):
        import importlib

        module = importlib.import_module(module_name)
        handler = getattr(module, fn_name)

        seen: list[str] = []

        async def _record(prefix):
            seen.append(prefix)
            return None

        # Patched where the shared body resolves it: the three endpoints now
        # delegate to `source_scope.cached_task_result`, which is the point --
        # one body to scope rather than three to remember.
        with patch("utils.celery_task_status.get_latest_task_result", AsyncMock(side_effect=_record)):
            await handler(source_id="src-A")
            await handler(source_id="src-B")

        assert len(seen) == 2, f"expected two cache reads, got {seen}"
        assert seen[0] != seen[1], f"{fn_name} read the same key for two sources: {seen[0]!r}"
        assert "src-A" in seen[0] and "src-B" in seen[1]

    @pytest.mark.parametrize("module_name,fn_name", list(_CACHED.values()), ids=list(_CACHED))
    async def test_an_empty_source_reaches_no_key_at_all(self, module_name, fn_name):
        """Refused before Redis is touched, so there is no global read to serve.

        FastAPI rejects the request at validation in production (the parameter is
        required), but the handler is also safe when called directly -- a guard
        that only lives in the route signature is one internal caller away from
        being bypassed.
        """
        import importlib

        module = importlib.import_module(module_name)
        handler = getattr(module, fn_name)
        reader = AsyncMock()

        with patch("utils.celery_task_status.get_latest_task_result", reader):
            with pytest.raises(ValueError, match="source_id"):
                await handler(source_id="")

        reader.assert_not_awaited()


class TestTheParameterCannotBeOmitted:
    """#17758's shape was an optional parameter nothing read. Now it is required."""

    @pytest.mark.parametrize(
        "module_name,route_path",
        [
            ("api.codebase_analytics.endpoints.dependencies", "/analytics/dependencies/cached"),
            ("api.codebase_analytics.endpoints.dependencies", "/analytics/dependencies/analyze"),
            ("api.codebase_analytics.endpoints.import_tree", "/analytics/import-tree/cached"),
            ("api.codebase_analytics.endpoints.import_tree", "/analytics/import-tree/analyze"),
            ("api.codebase_analytics.endpoints.duplicates", "/duplicates/cached"),
            ("api.codebase_analytics.endpoints.duplicates", "/duplicates/analyze"),
        ],
    )
    def test_source_id_is_a_required_query_parameter(self, module_name, route_path):
        import importlib

        module = importlib.import_module(module_name)
        routes = [r for r in module.router.routes if getattr(r, "path", "") == route_path]
        assert len(routes) == 1, f"expected one route at {route_path}, found {len(routes)}"

        params = {p.name: p for p in routes[0].dependant.query_params}
        assert "source_id" in params, f"{route_path} does not take a source_id"
        # field_info.is_required() rather than ModelField.required: the latter is
        # gone under Pydantic v2, and a missing attribute would read as False.
        assert params[
            "source_id"
        ].field_info.is_required(), f"{route_path}'s source_id is optional; an omitted one used to read a global key"


class TestTheReportIsPerProject:
    """Owner ruling, 2026-09-29: `/report` and `/summary` are per-project (#17758).

    This reverses #5112, which made `/api/reporting/report` "the one exception
    that stays global" -- a report aggregating across projects is the
    cross-project leak #17758 exists to remove. The ruling is recorded here as
    an assertion rather than only in a comment, because a comment cannot fail
    when someone restores the optional parameter for convenience.
    """

    @pytest.mark.parametrize("route_path", ["/report", "/summary"])
    def test_source_id_is_required(self, route_path):
        from api import analytics_reporting

        routes = [r for r in analytics_reporting.router.routes if getattr(r, "path", "") == route_path]
        assert len(routes) == 1, f"expected one route at {route_path}, found {len(routes)}"

        params = {p.name: p for p in routes[0].dependant.query_params}
        assert "source_id" in params, f"{route_path} takes no source_id; it would aggregate across projects"
        assert params["source_id"].field_info.is_required(), (
            f"{route_path}'s source_id is optional again -- an omitted one makes the report "
            "cross-project, which is the #17758 leak in the surface that composes every panel"
        )

    def test_the_charts_helper_declines_without_a_source(self):
        """Defence for the internal path: the routes require it, callers can still omit it.

        `fetch_codebase_charts()` is an ordinary function. Requiring the
        parameter at two routes does not stop a third caller passing nothing,
        and the honest answer to "which project?" unanswered is to not ask the
        charts endpoint at all rather than to resolve a default.
        """
        import asyncio

        from api.analytics_reporting import fetch_codebase_charts

        result = asyncio.run(fetch_codebase_charts(None))
        assert result["chart_data"]["problem_types"] == []
        assert result["chart_data"]["severity_counts"] == []


class TestUnavailableChartsAreNotAHealthyProject:
    """Unknown is not zero, and here zero meant a full mark (#17758).

    `_EMPTY_CHARTS` supplies empty `severity_counts`, which sums to zero issues.
    The composite score read that as a perfectly clean project and awarded the
    entire 30% issues component -- for a measurement that never happened. The
    report then called a project healthy that it had not examined, which is the
    empty-versus-unasked defect with a number attached.
    """

    @staticmethod
    def _inputs(charts):
        return {
            "quality_data": {"overall": 50, "breakdown": {"performance": 50}},
            "charts_data": charts,
            "debt_data": {"summary": {"total_hours": 50}},
            "performance_data": {"average_score": 50},
        }

    def test_unavailable_charts_do_not_award_the_issues_component(self):
        from api.analytics_reporting import _EMPTY_CHARTS, calculate_composite_health_score

        unavailable = calculate_composite_health_score(**self._inputs(dict(_EMPTY_CHARTS)))
        clean = calculate_composite_health_score(
            **self._inputs({"chart_data": {"severity_counts": []}, "charts_available": True})
        )
        assert unavailable != clean, (
            "an unavailable charts section scores the same as a genuinely clean project; "
            "that is the full 30% awarded for a measurement that never happened"
        )

    def test_an_unavailable_component_is_dropped_not_zeroed(self):
        """Scoring it 0 would punish a project for a failed fetch; 100 is the bug.

        With every measured component at 50, the renormalised score must stay 50
        -- the missing component neither helps nor harms.
        """
        from api.analytics_reporting import _EMPTY_CHARTS, calculate_composite_health_score

        assert calculate_composite_health_score(**self._inputs(dict(_EMPTY_CHARTS))) == 50.0

    def test_a_clean_project_still_scores_its_full_marks(self):
        """The contrast case: really having no issues must still score 100 there."""
        from api.analytics_reporting import calculate_composite_health_score

        score = calculate_composite_health_score(
            quality_data={"overall": 100, "breakdown": {"performance": 100}},
            charts_data={"chart_data": {"severity_counts": []}, "charts_available": True},
            debt_data={"summary": {"total_hours": 0}},
            performance_data={"average_score": 100},
        )
        assert score == 100.0

    def test_the_default_is_available_so_existing_callers_are_unchanged(self):
        """A caller that never heard of the flag must score as it always did."""
        from api.analytics_reporting import calculate_composite_health_score

        legacy = calculate_composite_health_score(**self._inputs({"chart_data": {"severity_counts": []}}))
        explicit = calculate_composite_health_score(
            **self._inputs({"chart_data": {"severity_counts": []}, "charts_available": True})
        )
        assert legacy == explicit
