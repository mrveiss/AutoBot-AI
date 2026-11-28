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
from autobot_shared.self_model_constants import ENTITY_KINDS
from autobot_shared.tool_spec import LOCATION_BACKEND, SELF_MODEL_QUERY_TOOL_NAME, declares_tool
from services.slm_self_model import SelfModelUnavailable, query_entities
from user_management.services.user_role import role_for_user_id

logger = get_logger(__name__)

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
SLM_PAGE = 500  # the SLM's own page ceiling
MAX_PAGES = 10  # pages read for one filter set; a larger set is reported as incomplete, never silently cut
_HOST_KINDS = frozenset({"node", "command", "package"})
_SERVICE_KIND = (
    "service"  # shown only when a permitted tool is served by it; routes, agents, models have no permission source
)
_TOOL_KIND = "tool"
_FILTERS = ("name", "node_id", "status")

#: Re-reads of one filter set after the SLM's ``revision`` moved between its pages,
#: before the read is flagged incomplete.
MAX_REVISION_RESTARTS = 2
_DONE, _TRUNCATED, _REVISION_CHANGED = "done", "truncated", "revision_changed"


def _permitted(tool: Dict[str, Any], role: str | None) -> bool:
    """Whether *role* may use the tool entity: its declared ``required_permission`` (None: any caller)."""
    required = (tool.get("attrs") or {}).get("required_permission")
    return required is None or role_has_permission(role, required)


def _requires(tool: Dict[str, Any]) -> List[str]:
    return (tool.get("attrs") or {}).get("requires") or []


def _depends_on(tool: Dict[str, Any], entity: Dict[str, Any]) -> bool:
    """Whether *entity* is where *tool* runs or something it requires: its service, node, command or package."""
    if entity.get("entity_key") == tool.get("parent_key"):
        return True
    node_id = tool.get("node_id")
    if not node_id or entity.get("kind") not in _HOST_KINDS:
        return False
    if entity["kind"] == "node":
        return node_id in (entity.get("node_id"), entity.get("name"))
    return entity.get("node_id") == node_id and entity.get("name") in _requires(tool)


def _matches(entity: Dict[str, Any], args: Dict[str, Any]) -> bool:
    """Whether *entity* satisfies the caller's name, node_id and status filters (the SLM applied them too)."""
    name = (args.get("name") or "").lower()
    return (
        (not name or name in entity["name"].lower())
        and (not args.get("node_id") or entity.get("node_id") == args["node_id"])
        and (not args.get("status") or entity["status"] == args["status"])
    )


class _Read:
    """What was read from the SLM, and whether any filter set held more rows than were read."""

    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []
        self.incomplete = False

    async def fetch(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Every row matching *filters*, paged; flags ``incomplete`` when the read could not be completed.

        Each page reloads the whole set, so a reconcile between two pages shifts the offsets. A changed
        ``revision`` restarts the read (at most ``MAX_REVISION_RESTARTS`` times), then flags it incomplete.
        """
        for _ in range(MAX_REVISION_RESTARTS + 1):
            rows, outcome = await self._read_pages(filters)
            if outcome != _REVISION_CHANGED:
                self.incomplete = self.incomplete or outcome == _TRUNCATED
                return rows
        self.incomplete = True
        return rows

    async def _read_pages(self, filters: Dict[str, Any]) -> tuple[List[Dict[str, Any]], str]:
        """One pass over the pages: the rows read and why it stopped (done, truncated, or revision changed)."""
        got: List[Dict[str, Any]] = []
        revision = None
        for _ in range(MAX_PAGES):
            data = await query_entities({**filters, "limit": SLM_PAGE, "offset": len(got)})
            if got and data.get("revision") != revision:
                return got, _REVISION_CHANGED
            revision = data.get("revision")
            page = data.get("entities", [])
            got += page
            if not page or len(got) >= data.get("total", len(got)):
                return got, _DONE
        return got, _TRUNCATED


def _call_filters(args: Dict[str, Any]) -> Dict[str, Any]:
    return {key: args[key] for key in _FILTERS if args.get(key)}


async def _dependencies(read: _Read, kind: str, allowed: List[Dict[str, Any]], args: Dict[str, Any]):
    """Rows the permitted tools depend on: nodes and services by filter; commands and packages by node and name."""
    if kind in ("node", _SERVICE_KIND):
        return [
            e
            for e in await read.fetch({"kind": kind, **_call_filters(args)})
            if any(_depends_on(t, e) for t in allowed)
        ]
    nodes = sorted({t["node_id"] for t in allowed if t.get("node_id") and _requires(t)})
    out: List[Dict[str, Any]] = []
    for node_id in nodes:  # one read per node; the required names are matched locally
        rows = await read.fetch({"kind": kind, **{**_call_filters(args), "node_id": node_id}})
        out += [e for e in rows if any(_depends_on(t, e) for t in allowed) and _matches(e, args)]
    return out


async def _gather(args: Dict[str, Any], role: str | None) -> tuple[List[Dict[str, Any]], bool]:
    """The entities *role* may see that match *args*, and whether the read was incomplete."""
    read = _Read()
    tools = await read.fetch({"kind": _TOOL_KIND})  # visibility is decided on every tool, so none is filtered out
    allowed = [t for t in tools if _permitted(t, role)]
    found: List[Dict[str, Any]] = []
    for kind in [args["kind"]] if args.get("kind") else ENTITY_KINDS:
        if kind == _TOOL_KIND:
            found += [t for t in allowed if _matches(t, args)]
        elif kind in _HOST_KINDS or kind == _SERVICE_KIND:
            found += await _dependencies(read, kind, allowed, args)
        else:
            found += await read.fetch({"kind": kind, **_call_filters(args)})
    return found, read.incomplete


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
    """The answer as text for the model; *total* counts the visible matches read, and a partial read says so."""
    entities: List[Dict[str, Any]] = data.get("entities", [])
    note = (
        " The SLM holds more matching rows than were read; narrow with kind, name or node_id."
        if data.get("incomplete")
        else ""
    )
    if not entities:
        return "No self-model entities match." + note
    header = f"{len(entities)} of {data['total']} visible matching entities:{note}"
    return "\n".join([header, *(format_entity(e) for e in entities)])


class SelfModelToolsMixin:
    """``query_self_model`` for ToolRegistry; needs nothing from the registry beyond being a mixin."""

    @declares_tool("self_model", LOCATION_BACKEND, None, name=SELF_MODEL_QUERY_TOOL_NAME)
    async def query_self_model(self, args: Dict[str, Any], user_id: str | None = None) -> Dict[str, Any]:
        """Agent tool: entities of the self-model filtered by kind, name, node and status (read-only)."""
        envelope = {"tool_name": SELF_MODEL_QUERY_TOOL_NAME, "tool_args": args}
        if not user_id:
            logger.warning("self-model query with no user id; returning nothing")
            return {**envelope, "result": "No self-model entities are visible without a user.", "status": "error"}
        role = await role_for_user_id(user_id)
        if role is None:
            return {
                **envelope,
                "result": "No self-model entities are visible to an unknown account.",
                "status": "error",
            }
        try:
            found, incomplete = await _gather(args, role)
        except (SelfModelUnavailable, aiohttp.ClientError) as exc:
            logger.error("Self-model query failed: %s", exc)
            return {**envelope, "result": f"The self-model is not reachable: {exc}", "status": "error"}
        shown = {"total": len(found), "entities": found[: _clamped_limit(args.get("limit"))], "incomplete": incomplete}
        return {**envelope, "result": format_result(shown), "status": "success"}
