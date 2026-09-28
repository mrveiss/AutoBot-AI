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

    def test_the_source_appears_in_the_key(self):
        assert source_scoped_prefix("codebase:deps:", "src-A") == "codebase:deps:src-A:"

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
