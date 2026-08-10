# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The impact endpoint must not flatten away its own coverage (#13506).

`services/knowledge/impact_analysis.py` was built so a truncated walk cannot be
mistaken for a complete one — that is what #13468 was filed to remove and #13471
delivered. An endpoint that returned a bare node list would put the defect back
while looking like a feature, so these tests assert the coverage fields survive
the HTTP boundary rather than asserting the walk itself (which
`impact_analysis_test.py` already covers).
"""

import asyncio
import json
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest


def _call(node_id="pkg.mod.Thing", max_depth=None, collection=object(), result=None):
    """Invoke the endpoint function directly, with its two dependencies stubbed."""
    from api.codebase_analytics.endpoints import impact

    async def _fake_find_impact(_collection, root_id, max_depth=None):  # noqa: ARG001
        return result

    with (
        patch.object(impact, "get_code_collection", return_value=collection),
        patch.object(impact, "find_impact", _fake_find_impact),
    ):
        response = asyncio.run(impact.analyze_impact(node_id=node_id, max_depth=max_depth))
    return response.status_code, json.loads(response.body)


@dataclass
class _Result:
    """Stands in for ImpactResult with the same field and property names."""

    root_id: str = "pkg.mod.Thing"
    seed_ids: list = field(default_factory=list)
    reached: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    skipped_edges: list = field(default_factory=list)
    max_depth: int = 5
    depth_reached: int = 0
    depth_capped: bool = False
    depth_capped_frontier: list = field(default_factory=list)

    @property
    def resolved_edge_count(self) -> int:
        return len(self.edges)

    @property
    def unresolved_edge_count(self) -> int:
        return len(self.skipped_edges)


def test_a_capped_walk_says_so_and_names_where_it_stopped():
    """The defect this endpoint must not reintroduce.

    A depth-capped walk is a lower bound. If the response omitted
    `depth_capped`/`depth_capped_frontier`, a caller would read a partial answer
    as the complete set of callers — which is worse than no answer, because it
    reads as evidence that nothing else is affected.
    """
    res = _Result(
        reached=["a", "b"],
        edges=[{"from": "a", "to": "b"}],
        depth_capped=True,
        depth_capped_frontier=["b"],
        depth_reached=5,
    )

    status, body = _call(result=res)

    assert status == 200
    assert body["depth_capped"] is True
    assert body["depth_capped_frontier"] == ["b"]
    assert body["depth_reached"] == 5
    assert body["max_depth"] == 5


def test_skipped_edges_and_both_counts_survive_the_http_boundary():
    """#13482 Q2: two interpretable numbers, not one synthesised score."""
    res = _Result(
        reached=["a"],
        edges=[{"from": "a", "to": "root"}],
        skipped_edges=[{"raw": "helper", "reason": "ambiguous"}],
    )

    status, body = _call(result=res)

    assert status == 200
    assert body["skipped_edges"] == [{"raw": "helper", "reason": "ambiguous"}]
    assert body["resolved_edge_count"] == 1
    assert body["unresolved_edge_count"] == 1


def test_no_confidence_score_is_synthesised():
    """Bound by #13482 Q2. A single number would hide how it was derived."""
    res = _Result(reached=["a"], edges=[{"from": "a", "to": "root"}], skipped_edges=[{"raw": "x"}])

    _, body = _call(result=res)

    for forbidden in ("confidence", "score", "certainty", "completeness"):
        assert not any(forbidden in key.lower() for key in body), f"{forbidden!r} leaked into the response"


def test_a_missing_graph_is_not_a_missing_node():
    """`indexed: false` rather than 404.

    "The graph was never built" and "that node does not exist" have different
    fixes; a 404 for the first sends the operator hunting for a typo.
    """
    status, body = _call(collection=None)

    assert status == 200
    assert body["indexed"] is False
    assert body["node_id"] == "pkg.mod.Thing"
    assert "reached" not in body


def test_a_complete_walk_is_reported_as_complete():
    """The guard must not mark every answer partial."""
    res = _Result(reached=["a", "b"], edges=[{"from": "a", "to": "b"}], depth_reached=2)

    _, body = _call(result=res)

    assert body["indexed"] is True
    assert body["depth_capped"] is False
    assert body["depth_capped_frontier"] == []


@pytest.mark.parametrize("depth", [1, 20])
def test_max_depth_override_reaches_the_engine(depth):
    """The knob is useless if the endpoint swallows it."""
    from api.codebase_analytics.endpoints import impact

    seen = {}

    async def _capture(_collection, root_id, max_depth=None):  # noqa: ARG001
        seen["max_depth"] = max_depth
        return _Result()

    with (
        patch.object(impact, "get_code_collection", return_value=object()),
        patch.object(impact, "find_impact", _capture),
    ):
        asyncio.run(impact.analyze_impact(node_id="x", max_depth=depth))

    assert seen["max_depth"] == depth


def test_the_endpoint_is_registered_on_the_router():
    """#13506 is a wiring defect — an endpoint nothing includes repeats it."""
    from api.codebase_analytics.router import router

    # This app wraps includes in `_IncludedRouter`, so the mounted paths live on
    # `.original_router.routes`, not on the top-level route objects.
    paths = {
        p
        for included in router.routes
        for sub in getattr(included, "original_router", None).routes
        if (p := getattr(sub, "path", None))
    }
    assert "/impact" in paths, f"/impact not mounted; got {sorted(paths)[:8]}…"
