# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The read-only self-model chat tool of :class:`tools.tool_registry.ToolRegistry` (#22278).

``query_self_model`` asks the SLM (the system of record, #22277) which nodes, services, routes, tools,
models, commands and agents exist, and whether each was only declared or actually probed, with its
``last_seen``. It reads as the user the agent runs for: with no user it returns nothing, like the
knowledge-base read tools (#16665). It never writes.
"""

from __future__ import annotations

from typing import Any, Dict, List

import aiohttp

from autobot_shared.logging_manager import get_logger
from services.slm_self_model import SelfModelUnavailable, query_entities
from tools.tool_records import SELF_MODEL_QUERY_TOOL_NAME

logger = get_logger(__name__)

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
_FILTERS = ("kind", "name", "node_id", "status")


def _clamped_limit(raw: Any) -> int:
    try:
        return min(max(int(raw), 1), MAX_LIMIT)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def format_entity(entity: Dict[str, Any]) -> str:
    """One entity as a line: kind, name, status, node, last_seen and, when unavailable, why."""
    parts = [f"{entity['kind']} {entity['name']}", f"status={entity['status']}", f"last_seen={entity['last_seen']}"]
    if entity.get("node_id"):
        parts.append(f"node={entity['node_id']}")
    if entity.get("version"):
        parts.append(f"version={entity['version']}")
    if not entity.get("available", True):
        parts.append("UNAVAILABLE (needs " + ", ".join(entity["unavailable_because"]) + ")")
    return " | ".join(parts)


def format_result(data: Dict[str, Any]) -> str:
    """The SLM's answer as text for the model."""
    entities: List[Dict[str, Any]] = data.get("entities", [])
    if not entities:
        return "No self-model entities match."
    header = f"{len(entities)} of {data.get('total', len(entities))} matching entities:"
    return "\n".join([header, *(format_entity(e) for e in entities)])


class SelfModelToolsMixin:
    """``query_self_model`` for ToolRegistry; needs nothing from the registry beyond being a mixin."""

    async def query_self_model(self, args: Dict[str, Any], user_id: str | None = None) -> Dict[str, Any]:
        """Agent tool: entities of the self-model filtered by kind, name, node and status (read-only)."""
        envelope = {"tool_name": SELF_MODEL_QUERY_TOOL_NAME, "tool_args": args}
        if not user_id:
            logger.warning("self-model query with no user id; returning nothing")
            return {**envelope, "result": "No self-model entities are visible without a user.", "status": "error"}
        filters = {key: args.get(key) for key in _FILTERS}
        filters["limit"] = _clamped_limit(args.get("limit"))
        try:
            data = await query_entities(filters)
        except (SelfModelUnavailable, aiohttp.ClientError) as exc:
            logger.error("Self-model query failed: %s", exc)
            return {**envelope, "result": f"The self-model is not reachable: {exc}", "status": "error"}
        return {**envelope, "result": format_result(data), "status": "success"}
