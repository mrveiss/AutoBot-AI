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
"""

import asyncio

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.knowledge.impact_analysis import find_impact

from ..storage import get_code_collection

logger = get_logger(__name__)

router = APIRouter()


@router.get("/impact")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_impact",
    error_code_prefix="CODEBASE_ANALYTICS",
)
async def analyze_impact(
    node_id: str = Query(..., min_length=1, description="Graph node id to walk back from"),
    max_depth: int | None = Query(
        None,
        ge=1,
        le=20,
        description="Override the configured hop limit. Omit to use impact_analysis_max_depth.",
    ),
):
    """Return what transitively calls *node_id*.

    A 200 with ``indexed: false`` rather than a 404 when the graph is missing:
    "the code graph has not been built" is a different answer from "that node
    does not exist", and collapsing them would send an operator hunting for a
    typo in their node id.
    """
    collection = await asyncio.to_thread(get_code_collection)
    if collection is None:
        return JSONResponse(
            status_code=200,
            content={
                "indexed": False,
                "node_id": node_id,
                "message": "The code graph collection is not available — run an index first.",
            },
        )

    result = await find_impact(collection, node_id, max_depth=max_depth)

    logger.info(
        "Impact walk for %s: %d reached, depth %d/%d%s",
        node_id,
        len(result.reached),
        result.depth_reached,
        result.max_depth,
        " (capped)" if result.depth_capped else "",
    )

    return JSONResponse(
        status_code=200,
        content={
            "indexed": True,
            "root_id": result.root_id,
            "seed_ids": result.seed_ids,
            "reached": result.reached,
            "edges": result.edges,
            # Coverage, in full. A caller that sees `depth_capped` knows the
            # answer is a lower bound; `depth_capped_frontier` says where it
            # stopped so the walk can be resumed or widened deliberately.
            "depth_capped": result.depth_capped,
            "depth_capped_frontier": result.depth_capped_frontier,
            "skipped_edges": result.skipped_edges,
            "resolved_edge_count": result.resolved_edge_count,
            "unresolved_edge_count": result.unresolved_edge_count,
            "max_depth": result.max_depth,
            "depth_reached": result.depth_reached,
        },
    )
