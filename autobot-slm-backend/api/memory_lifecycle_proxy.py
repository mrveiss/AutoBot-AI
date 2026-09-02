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

import logging
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, Query

from autobot_shared import node_proxy
from autobot_shared.ssot_constants import QueryDefaults
from config import settings
from services.auth import get_current_user

# Stdlib logging, not autobot_shared.get_logger: this package's test harness
# replaces `config` with a MagicMock, and the shared logger reads handler sizes
# from config at import time — it dies during collection. Same reason
# api/voice_proxy.py does this, and the documented exception in CLAUDE.md.
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory-lifecycle"])

# URL, key, TLS policy and timeout all come from the shared node client (#14886).
# An earlier revision here read its own AUTOBOT_NODE_PROXY_VERIFY_TLS with a
# "false" default, shipping verification OFF unless an operator opted in — on
# the channel that carries the internal API key (#14653). A per-module switch is
# how that happens; there is now one switch for every node proxy, and this
# module cannot hold an opinion about it.
_NODE_URL = node_proxy.resolve_node_url(settings.authority_base_url)
_INTERNAL_API_KEY = node_proxy.internal_api_key()

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
    if not _INTERNAL_API_KEY:
        # A missing key is a configuration fault, not a node fault. Saying so is
        # the difference between an operator checking the node and checking a var.
        logger.error("memory lifecycle: AUTOBOT_INTERNAL_API_KEY not configured")
        return {"nodes": [_unreachable(_NODE_URL, node_proxy.REASON_KEY_NOT_CONFIGURED)], "degraded": True}

    node = await _fetch_node(_NODE_URL, limit)

    # `degraded` composes. The node reports its own partial reads (#12631), and a
    # proxy that only reported transport failures would show a node whose decay
    # section is broken as perfectly healthy.
    return {"nodes": [node], "degraded": bool(node.get("degraded"))}


async def _fetch_node(base_url: str, limit: int) -> Dict[str, Any]:
    """One node's lifecycle payload, or an unreachable placeholder."""
    if not base_url:
        return _unreachable(base_url, node_proxy.REASON_URL_NOT_CONFIGURED)

    url = f"{base_url.rstrip('/')}/api/memory/lifecycle"
    try:
        async with node_proxy.node_client() as client:
            response = await client.get(url, params={"limit": limit}, headers=node_proxy.internal_headers())
    except httpx.HTTPError as exc:
        failure = node_proxy.classify_transport_error(exc)
        logger.warning("memory lifecycle: %s (%s)", failure.reason, type(exc).__name__)
        return _unreachable(base_url, failure.reason)

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
