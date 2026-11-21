# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The persisted per-source call-graph summary (#20945).

``GET /analytics/call-graph`` caches the whole graph for five minutes. The knowledge graph needs only the
size of a codebase, and needs it after that cache has gone, so the build also leaves this small summary
under a key of its own with a long, env-backed TTL. A re-analyse overwrites it. The full graph is never
copied here: it is fetched on demand from ``/analytics/call-graph``.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from api.source_scope import source_scoped_prefix
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.ttl_constants import TTL_1_HOUR, TTL_30_DAYS, TTL_90_DAYS

logger = get_logger(__name__)

CALL_GRAPH_SUMMARY_PREFIX = "callgraph_summary:"
CALL_GRAPH_SUMMARY_TTL = env_int_clamped(
    "AUTOBOT_CALL_GRAPH_SUMMARY_TTL", TTL_30_DAYS, min_v=TTL_1_HOUR, max_v=TTL_90_DAYS
)
SUMMARY_FIELDS = ("total_functions", "total_call_relationships", "resolution_rate", "files_scanned", "files_total")


def _summary_key(source_id: str) -> str:
    return f"{source_scoped_prefix(CALL_GRAPH_SUMMARY_PREFIX, source_id)}summary"


def summarize_call_graph(response_data: Dict[str, Any]) -> Dict[str, Any]:
    """The few counts of a built call-graph response that the knowledge graph reports."""
    summary = response_data.get("summary") or {}
    return {**{f: summary.get(f) for f in SUMMARY_FIELDS}, "truncated": bool(summary.get("truncated"))}


async def store_call_graph_summary(source_id: str, response_data: Dict[str, Any]) -> None:
    """Persist (overwrite) the summary of a freshly built graph; non-fatal, the graph itself was served."""
    try:
        redis = await get_async_redis_client(database="analytics")
        if redis:
            await redis.set(
                _summary_key(source_id), json.dumps(summarize_call_graph(response_data)), ex=CALL_GRAPH_SUMMARY_TTL
            )
    except Exception as exc:
        logger.warning("Call graph summary for source %s not persisted: %s", source_id, exc)


async def load_call_graph_summary(source_id: str) -> Dict[str, Any] | None:
    """The persisted summary of a source, or None when its call graph was never built (or the summary expired)."""
    redis = await get_async_redis_client(database="analytics")
    raw = await redis.get(_summary_key(source_id)) if redis else None
    return json.loads(raw) if raw else None
