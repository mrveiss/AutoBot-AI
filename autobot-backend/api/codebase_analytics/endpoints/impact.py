# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Impact analysis endpoint — "what breaks if I change this" (#13506).

Exposes the reverse-BFS engine that landed with #13471 and has had no caller
since. The engine answers the question the ``dead-code-audit``,
``api-wiring-audit`` and ``gap-audit`` workflows currently reason about by hand.

The response deliberately carries the whole coverage picture rather than a
flattened node list: ``depth_capped`` with its un-expanded frontier, the skipped
edges with their reasons, and the resolved/unresolved edge counts. The engine was
built so a partial answer cannot render as a complete one (#13468), and an
endpoint that dropped those fields would put the defect straight back.

No confidence score is synthesised from the counts — #13482 Q2 bound that
explicitly. Two numbers a caller can interpret beat one number that hides how it
was derived.

This is the REST/GUI path. #13475 covers the MCP tool surface over the same
engine; neither substitutes for the other, and neither should reshape
``ImpactResult`` for its own convenience.

Query logic lives in ``code_graph_queries`` (#21327): the MCP ``code.*`` tools call the same
functions, so the route and the tool cannot diverge.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.source_scope import CROSS_SOURCE_OPENAPI
from autobot_shared.code_graph.commit_freshness import COMMIT_PATTERN
from autobot_shared.error_boundaries import ErrorCategory, bounded, with_error_handling

from ..code_graph_queries import query_affected

router = APIRouter()

ExpectedCommitQuery = Annotated[
    str | None,
    Query(
        pattern=COMMIT_PATTERN,
        description="Commit the caller expects the graph to describe; a mismatch is flagged stale in the answer.",
    ),
]


@router.get("/impact", openapi_extra=CROSS_SOURCE_OPENAPI)
@bounded(60.0)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_impact",
    error_code_prefix="CODEBASE_ANALYTICS",
)
async def analyze_impact(
    node_id: Annotated[str | None, Query(min_length=1, description="Exact graph node id to walk back from")] = None,
    symbol: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=500,
            description="Symbol name (bare, Class.method or node id) instead of node_id; "
            "an ambiguous name returns its candidates, never a guess",
        ),
    ] = None,
    max_depth: int | None = Query(
        None,
        ge=1,
        le=20,
        description="Override the configured hop limit. Omit to use impact_analysis_max_depth.",
    ),
    expected_commit: ExpectedCommitQuery = None,
):
    """Return what transitively calls *node_id*.

    CROSS-SOURCE (#20513): the code-graph collection is not tagged with a code
    source. ``CodeIndexer`` writes ``source``/``source_path``/``node_name`` and, on
    edges, a ``source_id`` that is the *caller node's* id, not a registry source;
    ``POST /api/knowledge_base/index/code`` takes a directory, not a source. So
    this walk cannot be filtered to one source, and node ids are path-based, so the
    same id in two sources is one node here. Every response says so
    (``source_scope``) instead of implying a scoped answer.

    A 200 with ``indexed: false`` rather than a 404 when the graph is missing:
    "the code graph has not been built" is a different answer from "that node
    does not exist", and collapsing them would send an operator hunting for a
    typo in their node id.

    *symbol* resolves a name to its node id first (#21327); several matches come back
    as ``status: ambiguous`` with every candidate and no walk.

    Every answer carries ``indexed_at_commit`` and, when *expected_commit* is
    given, ``stale`` (#21327).
    """
    if (node_id is None) == (symbol is None):
        raise HTTPException(status_code=422, detail="Give exactly one of node_id or symbol")
    return JSONResponse(status_code=200, content=await query_affected(node_id, symbol, max_depth, expected_commit))
