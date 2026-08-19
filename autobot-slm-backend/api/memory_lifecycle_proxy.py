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
import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, Query

from config import settings
from services.auth import get_current_user

# Stdlib logging, not autobot_shared.get_logger: this package's test harness
# replaces `config` with a MagicMock, and the shared logger reads handler sizes
# from config at import time — it dies during collection. Same reason
# api/voice_proxy.py does this, and the documented exception in CLAUDE.md.
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory-lifecycle"])

_NODE_URL = os.getenv("AUTOBOT_BACKEND_URL", "") or settings.authority_base_url  # noqa: ssot-fallback
_INTERNAL_API_KEY = os.getenv("AUTOBOT_INTERNAL_API_KEY", "")
_TIMEOUT = float(os.getenv("AUTOBOT_NODE_PROXY_TIMEOUT_SECONDS", "15"))
_VERIFY_TLS = os.getenv("AUTOBOT_NODE_PROXY_VERIFY_TLS", "false").lower() == "true"

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


@router.get("/lifecycle")
async def get_memory_lifecycle(
    limit: int = Query(20, ge=1, le=100),
    _user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """Aggregate the fleet's memory lifecycle views. Never raises to the client."""
    if not _INTERNAL_API_KEY:
        # A missing key is a configuration fault, not a node fault. Saying so is
        # the difference between an operator checking the node and checking a var.
        logger.error("memory lifecycle: AUTOBOT_INTERNAL_API_KEY not configured")
        return {"nodes": [_unreachable(_NODE_URL, "internal_api_key_not_configured")], "degraded": True}

    node = await _fetch_node(_NODE_URL, limit)

    # `degraded` composes. The node reports its own partial reads (#12631), and a
    # proxy that only reported transport failures would show a node whose decay
    # section is broken as perfectly healthy.
    return {"nodes": [node], "degraded": bool(node.get("degraded"))}


async def _fetch_node(base_url: str, limit: int) -> Dict[str, Any]:
    """One node's lifecycle payload, or an unreachable placeholder."""
    if not base_url:
        return _unreachable(base_url, "node_url_not_configured")

    url = f"{base_url.rstrip('/')}/api/memory/lifecycle"
    try:
        async with httpx.AsyncClient(verify=_VERIFY_TLS, timeout=_TIMEOUT) as client:
            response = await client.get(
                url,
                params={"limit": limit},
                headers={"X-Internal-API-Key": _INTERNAL_API_KEY},
            )
    except httpx.TimeoutException:
        logger.warning("memory lifecycle: node timed out after %ss", _TIMEOUT)
        return _unreachable(base_url, "node_timeout")
    except httpx.HTTPError as exc:
        logger.warning("memory lifecycle: node unreachable: %s", type(exc).__name__)
        return _unreachable(base_url, "node_unreachable")

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
