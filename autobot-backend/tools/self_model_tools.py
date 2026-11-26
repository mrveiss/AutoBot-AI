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

from autobot_shared.auth.permissions import role_has_permission
from autobot_shared.logging_manager import get_logger
from services.slm_self_model import SelfModelUnavailable, query_entities
from tools.tool_records import SELF_MODEL_QUERY_TOOL_NAME
from user_management.services.user_role import role_for_user_id

logger = get_logger(__name__)

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
SLM_PAGE = 500  # the SLM's own ceiling: the whole graph is read so visibility is decided on all of it
_HOST_KINDS = frozenset({"node", "command", "package"})


def _permitted(tool: Dict[str, Any], role: str | None) -> bool:
    """Whether *role* may use the tool entity: its declared ``required_permission`` (None: any caller)."""
    required = (tool.get("attrs") or {}).get("required_permission")
    return required is None or role_has_permission(role, required)


def _depends_on(tool: Dict[str, Any], entity: Dict[str, Any]) -> bool:
    """Whether *entity* is where *tool* runs or something it requires: its service, node, command or package."""
    if entity.get("entity_key") == tool.get("parent_key"):
        return True
    node_id = tool.get("node_id")
    if not node_id or entity.get("kind") not in _HOST_KINDS:
        return False
    if entity["kind"] == "node":
        return node_id in (entity.get("node_id"), entity.get("name"))
    needs = (tool.get("attrs") or {}).get("requires") or []
    return entity.get("node_id") == node_id and entity.get("name") in needs


def _entity_visible(entity: Dict[str, Any], allowed: List[Dict[str, Any]]) -> bool:
    """A tool is visible when permitted (*allowed*); a host kind only as a dependency of one; others as ever."""
    if entity["kind"] == "tool":
        return any(entity is t for t in allowed)
    if entity["kind"] in _HOST_KINDS:
        return any(_depends_on(t, entity) for t in allowed)
    return True


def visible_entities(entities: List[Dict[str, Any]], role: str | None) -> List[Dict[str, Any]]:
    """Entities *role* may see: tools it may use and what they depend on; no other node, command or package."""
    allowed = [e for e in entities if e["kind"] == "tool" and _permitted(e, role)]
    return [e for e in entities if _entity_visible(e, allowed)]


def _matches(entity: Dict[str, Any], args: Dict[str, Any]) -> bool:
    """Whether *entity* satisfies the caller's kind, name, node_id and status filters."""
    name = (args.get("name") or "").lower()
    return (
        (not args.get("kind") or entity["kind"] == args["kind"])
        and (not name or name in entity["name"].lower())
        and (not args.get("node_id") or entity.get("node_id") == args["node_id"])
        and (not args.get("status") or entity["status"] == args["status"])
    )


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
        try:
            data = await query_entities({"limit": SLM_PAGE})
        except (SelfModelUnavailable, aiohttp.ClientError) as exc:
            logger.error("Self-model query failed: %s", exc)
            return {**envelope, "result": f"The self-model is not reachable: {exc}", "status": "error"}
        role = await role_for_user_id(user_id)
        if role is None:
            return {
                **envelope,
                "result": "No self-model entities are visible to an unknown account.",
                "status": "error",
            }
        seen = visible_entities(data.get("entities", []), role)
        found = [e for e in seen if _matches(e, args)]
        shown = {"total": len(found), "entities": found[: _clamped_limit(args.get("limit"))]}
        return {**envelope, "result": format_result(shown), "status": "success"}
