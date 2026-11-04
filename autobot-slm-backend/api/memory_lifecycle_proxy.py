# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM aggregator for the node's memory lifecycle view (#12632, umbrella #12630).

SLM is the control plane and `autobot-backend` is the managed node: the lifecycle
*data* lives on the node (#12631), the operator *surface* belongs here. This is the
aggregating tier between them.

Fleet-aware in shape, single-node in fact. The payload nests per node rather than
returning the node's body verbatim, so adding a second node is a loop here instead
of a breaking change to every consumer.

Degrades rather than failing. A node that cannot be reached yields empty sections
with `degraded: true`, never a 5xx — a monitoring surface that errors tells an
operator less than one that says which part it could not read.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import QueryDefaults
from services.auth import get_current_user
from services.main_backend_client import MainBackendUnavailable, backend_url, call_main_backend  # #20760

logger = get_logger(__name__)

router = APIRouter(prefix="/memory", tags=["memory-lifecycle"])

_EMPTY_SECTIONS: Dict[str, Any] = {
    "reinforcement": {"hot": [], "cold": []},
    "decay": {"last_run": None, "config": {}, "prune_preview": []},
}


def _unreachable(node: str, reason: str) -> Dict[str, Any]:
    """A node we could not read, shaped like one we could.

    The empty sections are spelled out rather than omitted so a consumer never has
    to branch on whether a key exists — a missing `reinforcement` and an empty one
    would otherwise mean the same thing to a reader and different things to code.
    """
    return {**_EMPTY_SECTIONS, "node": node, "degraded": True, "error": reason}


# The ceiling is MAX_SEARCH_LIMIT, not KNOWLEDGE_DEFAULT_LIMIT which the linter
# suggests: both are 100 today, but one is a maximum and the other a default, and
# a ceiling that silently tracks a default drifts the moment the default moves.
@router.get("/lifecycle")
async def get_memory_lifecycle(
    limit: int = Query(QueryDefaults.DEFAULT_TOP_K * 2, ge=1, le=QueryDefaults.MAX_SEARCH_LIMIT),
    _user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """Aggregate the fleet's memory lifecycle views. Never raises to the client."""
    node = await _fetch_node(backend_url(), limit)

    # `degraded` composes. The node reports its own partial reads (#12631), and a
    # proxy that only reported transport failures would show a node whose decay
    # section is broken as perfectly healthy.
    return {"nodes": [node], "degraded": bool(node.get("degraded"))}


async def _fetch_node(base_url: str, limit: int) -> Dict[str, Any]:
    """One node's lifecycle payload, or an unreachable placeholder.

    The call is the one SLM->backend client's (#20760): a missing key or URL is a configuration
    fault and a transport failure is the shared classification, reported as the placeholder's reason.
    """
    try:
        response = await call_main_backend("GET", "memory/lifecycle", params={"limit": limit}, service="Memory")
    except MainBackendUnavailable as unavailable:
        logger.warning("memory lifecycle: %s", unavailable.reason)
        return _unreachable(base_url, unavailable.reason)

    if response.status_code != 200:
        # A non-200 is reported with its status rather than collapsed into
        # "unreachable": 403 means the key is wrong, 404 means the node predates
        # #12631, and an operator acts differently on each.
        logger.warning("memory lifecycle: node returned %s", response.status_code)
        return _unreachable(base_url, f"node_status_{response.status_code}")

    try:
        body = response.json()
    except ValueError:
        logger.warning("memory lifecycle: node returned a non-JSON body")
        return _unreachable(base_url, "node_bad_payload")

    return {**_EMPTY_SECTIONS, **body, "node": base_url, "degraded": bool(body.get("degraded"))}
