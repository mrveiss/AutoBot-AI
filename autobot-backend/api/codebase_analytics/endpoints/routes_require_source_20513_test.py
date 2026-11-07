# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every analytics route requires its source, or says it has none (#20513).

Read from the REGISTERED routes (``effective_routes``), not from a grep of ``@router.``:
``add_clear_stuck_route`` registers routes no decorator shows, so a grep undercounts.

A route is exactly one of:

* TASK -- addressed by ``{task_id}``;
* cross-source -- carries ``openapi_extra["x-source-scope"] == "cross-source"``;
* OPS -- a named process-wide or source-creating operation;
* deferred -- named in ``DEFERRED_TO_PR2`` with its reason;
* source-required -- ``source_id`` is a path parameter, a REQUIRED query parameter, or a REQUIRED
  field of its body model (``POST /index`` takes exactly one of ``source_id`` / ``root_path``).

Anything else is the defect this issue reports: an optional or absent ``source_id`` that a
handler answers by defaulting to the most recent source, or to every source.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter
from repo_tests._analytics_routes_20513 import (
    CROSS_SOURCE_PATHS,
    DEFERRED_TO_PR2,
    EXACTLY_ONE_BODY,
    OPS_EXACT,
    OPS_SUFFIXES,
    TASK_MARKER,
)

from autobot_shared.api_routing.router_routes import effective_routes

#: Counted on the day this was written: 86 registered routes. A walk that finds fewer has stopped
#: seeing routes (the deferred-inclusion shape of #15093 walks to nothing without raising).
MIN_ROUTES_EXAMINED = 70
MIN_SOURCE_REQUIRED = 55


def _requires_source(route) -> bool:
    """Whether *route* cannot be called without a ``source_id``."""
    dependant = route.dependant
    if any(p.name == "source_id" for p in dependant.path_params):
        return True
    if any(q.name == "source_id" and q.field_info.is_required() for q in dependant.query_params):
        return True
    for body in dependant.body_params:
        model_fields = getattr(body.field_info.annotation, "model_fields", {})
        field = model_fields.get("source_id")
        if field is not None and field.is_required():
            return True
    return False


def _classify(mounted) -> str:
    """The class of one mounted route; ``"LEAK"`` is the one that fails."""
    route = mounted.route
    methods = mounted.methods
    path = mounted.path
    if TASK_MARKER in path:
        return "TASK"
    if (route.openapi_extra or {}).get("x-source-scope") == "cross-source":
        return "XS"
    if any((m, path) in OPS_EXACT for m in methods) or path.endswith(OPS_SUFFIXES):
        return "OPS"
    if path in DEFERRED_TO_PR2:
        return "DEFERRED"
    if any((m, path) in EXACTLY_ONE_BODY for m in methods):
        return "EXACTLY_ONE"
    return "REQUIRED" if _requires_source(route) else "LEAK"


def _classes(router) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for mounted in effective_routes(router):
        out.setdefault(_classify(mounted), []).append(f"{sorted(mounted.methods)} {mounted.path}")
    return out


@pytest.fixture(scope="module")
def analytics_router():
    from api.codebase_analytics.router import router

    return router


def test_no_route_leaks_its_source(analytics_router):
    classes = _classes(analytics_router)
    assert not classes.get(
        "LEAK"
    ), "routes that neither require a source_id nor declare themselves cross-source (#20513):\n  " + "\n  ".join(
        sorted(classes.get("LEAK", []))
    )


def test_the_walk_still_sees_the_routes(analytics_router):
    classes = _classes(analytics_router)
    examined = sum(len(v) for v in classes.values())
    assert examined >= MIN_ROUTES_EXAMINED, f"only {examined} routes examined; the walk stopped seeing them"
    assert len(classes.get("REQUIRED", [])) >= MIN_SOURCE_REQUIRED, {k: len(v) for k, v in classes.items()}


def test_the_cross_source_marker_names_exactly_the_shared_list(analytics_router):
    marked = {m.path for m in effective_routes(analytics_router) if _classify(m) == "XS"}
    assert marked == set(CROSS_SOURCE_PATHS)


def test_every_deferred_and_ops_entry_is_a_real_route(analytics_router):
    """A stale allowlist entry is an exemption nobody is using, and a name a future route could take."""
    mounted = effective_routes(analytics_router)
    paths = {m.path for m in mounted}
    pairs = {(method, m.path) for m in mounted for method in m.methods}
    assert DEFERRED_TO_PR2 <= paths
    assert OPS_EXACT <= pairs
    assert EXACTLY_ONE_BODY <= pairs
    assert any(p.endswith(OPS_SUFFIXES) for p in paths)


def test_index_takes_exactly_one_target():
    from pydantic import ValidationError

    from api.codebase_analytics.endpoints.indexing import IndexCodebaseRequest

    assert IndexCodebaseRequest(source_id="src-a").source_id == "src-a"
    assert IndexCodebaseRequest(root_path="/some/dir").root_path == "/some/dir"
    for bad in ({}, {"source_id": "a", "root_path": "/x"}, {"source_id": "a:*"}):
        with pytest.raises(ValidationError):
            IndexCodebaseRequest(**bad)


def test_pattern_analyze_body_requires_a_well_formed_source():
    from pydantic import ValidationError

    from api.codebase_analytics.endpoints.pattern_analysis import PatternAnalysisRequest

    assert PatternAnalysisRequest(source_id="src-a").path is None
    for bad in ({}, {"source_id": ""}, {"source_id": "*"}):
        with pytest.raises(ValidationError):
            PatternAnalysisRequest(**bad)


# --- controls: the classifier must be able to fail, or a green run says nothing -------------


def _throwaway():
    from fastapi import Query

    from api.codebase_analytics.source_scope import CROSS_SOURCE_OPENAPI, SourceIdQuery

    router = APIRouter()

    @router.get("/leaky")
    async def leaky(source_id: str | None = Query(None)):  # the reported defect
        return {}

    @router.get("/ok")
    async def ok(source_id: SourceIdQuery):
        return {}

    @router.get("/marked", openapi_extra=CROSS_SOURCE_OPENAPI)
    async def marked():
        return {}

    @router.get("/unmarked")
    async def unmarked():
        return {}

    @router.get("/by-path/{source_id}")
    async def by_path(source_id: str):
        return {}

    @router.get("/thing/{task_id}")
    async def task(task_id: str):
        return {}

    return router


def test_control_a_leaky_route_is_flagged_and_an_ok_route_passes():
    classes = _classes(_throwaway())
    assert "['GET'] /leaky" in classes["LEAK"]
    assert "['GET'] /ok" in classes["REQUIRED"]
    assert "['GET'] /by-path/{source_id}" in classes["REQUIRED"]


def test_control_the_marker_exempts_a_route_and_its_absence_does_not():
    classes = _classes(_throwaway())
    assert "['GET'] /marked" in classes["XS"]
    assert "['GET'] /unmarked" in classes["LEAK"]
    assert "['GET'] /thing/{task_id}" in classes["TASK"]
