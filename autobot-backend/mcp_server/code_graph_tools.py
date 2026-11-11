# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read-only ``code.*`` MCP tools over the persisted code graph (#21327, #13475).

Three tools, each a thin delegation to ``api/codebase_analytics/code_graph_queries.py`` -- the same
functions the HTTP routes call, so the tool and the route cannot give different answers:

* ``code.resolve_symbol`` -- a symbol name to graph node ids; several matches return the candidate list.
* ``code.affected``       -- what transitively calls a symbol (by name or node id); the #13475 tool name.
* ``code.similar``        -- stored code patterns most similar to a snippet.

Read-only by construction: this module imports no indexing, deletion or storage-write function, and
the tool table below is the whole surface. Access is the ``code`` MCP scope; a ``code`` token reads
the cross-source graph exactly as the admin-gated ``/impact`` route does, so it is granted
deliberately and is not part of the default stdio scopes. Similar-code is per source and is
authorised as a caller with no owner identity: only unowned, public or shared sources are readable.

Every response is capped at ``CODE_TOOL_MAX_ITEMS`` entries per list and says what it omitted.
"""

import asyncio
from typing import Any, Dict

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from autobot_shared.code_graph.commit_freshness import COMMIT_PATTERN
from autobot_shared.error_boundaries import DEFAULT_ROUTE_DEADLINE_SECONDS
from constants.threshold_constants import QueryDefaults

#: Entries kept per list in one tool response, so a large subgraph cannot flood a caller's context.
CODE_TOOL_MAX_ITEMS = 200

#: Source authorisation identity for MCP callers: truthy, no id, not the service principal, so
#: ``_caller_owner_id`` fails closed and another owner's PRIVATE source stays invisible.
_MCP_SOURCE_PRINCIPAL = {"mcp_client": True}

_LISTS = ("candidates", "reached", "edges", "skipped_edges", "results")

_EXPECTED_COMMIT = {
    "type": "string",
    "description": "Commit you expect the index to describe; a mismatch comes back with stale=true.",
}

CODE_TOOLS: Dict[str, Dict[str, Any]] = {
    "code.resolve_symbol": {
        "description": "Resolve a symbol name (bare, Class.method, or node id) to code-graph node ids. "
        "Several matches return every candidate and no node_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name to resolve"},
                "expected_commit": _EXPECTED_COMMIT,
            },
            "required": ["symbol"],
        },
    },
    "code.affected": {
        "description": "Who transitively calls a symbol (what breaks if it changes). Give symbol or node_id. "
        "Reports the commit the graph was built at, the walk's coverage and whether it is stale.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name; ambiguous names return candidates"},
                "node_id": {"type": "string", "description": "Exact graph node id"},
                "max_depth": {"type": "integer", "description": "Hop limit, 1-20"},
                "expected_commit": _EXPECTED_COMMIT,
            },
        },
    },
    "code.similar": {
        "description": "Find stored code patterns of one source that are similar to a snippet "
        "(is there already code like this).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code snippet"},
                "source_id": {"type": "string", "description": "Code source to search"},
                "pattern_type": {"type": "string", "description": "Optional pattern type filter"},
                "limit": {
                    "type": "integer",
                    "default": QueryDefaults.DEFAULT_SEARCH_LIMIT,
                    "description": "Maximum results, 1-50",
                },
                "expected_commit": _EXPECTED_COMMIT,
            },
            "required": ["code", "source_id"],
        },
    },
}


class _ResolveArgs(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=500)
    expected_commit: str | None = Field(None, pattern=COMMIT_PATTERN)


class _AffectedArgs(BaseModel):
    symbol: str | None = Field(None, min_length=1, max_length=500)
    node_id: str | None = Field(None, min_length=1, max_length=1000)
    max_depth: int | None = Field(None, ge=1, le=20)
    expected_commit: str | None = Field(None, pattern=COMMIT_PATTERN)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "_AffectedArgs":
        if (self.symbol is None) == (self.node_id is None):
            raise ValueError("give exactly one of symbol or node_id")
        return self


class _SimilarArgs(BaseModel):
    code: str = Field(..., min_length=1, max_length=20_000)
    source_id: str = Field(..., pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    pattern_type: str | None = Field(None, max_length=100)
    limit: int = Field(QueryDefaults.DEFAULT_SEARCH_LIMIT, ge=1, le=50)
    expected_commit: str | None = Field(None, pattern=COMMIT_PATTERN)


def bound_lists(answer: Dict[str, Any]) -> Dict[str, Any]:
    """Cap every list in *answer* at ``CODE_TOOL_MAX_ITEMS`` and record what was left out."""
    omitted = {
        k: len(answer[k]) - CODE_TOOL_MAX_ITEMS for k in _LISTS if len(answer.get(k) or []) > CODE_TOOL_MAX_ITEMS
    }
    if not omitted:
        return answer
    return {**{k: (v[:CODE_TOOL_MAX_ITEMS] if k in omitted else v) for k, v in answer.items()}, "omitted": omitted}


def _queries() -> Any:
    """The shared query module. Imported on first use: its package pulls in the whole analytics router."""
    from api.codebase_analytics import code_graph_queries

    return code_graph_queries


class CodeGraphToolsMixin:
    """The ``code.*`` handlers, resolved by name in ``AutoBotMCPServer._dispatch_tool``."""

    async def _code_resolve_symbol(self, **arguments: Any) -> Dict[str, Any]:
        args = _ResolveArgs(**arguments)
        answer = await asyncio.wait_for(
            _queries().resolve_symbol(args.symbol, args.expected_commit), DEFAULT_ROUTE_DEADLINE_SECONDS
        )
        return bound_lists(answer)

    async def _code_affected(self, **arguments: Any) -> Dict[str, Any]:
        args = _AffectedArgs(**arguments)
        walk = _queries().query_affected(args.node_id, args.symbol, args.max_depth, args.expected_commit)
        return bound_lists(await asyncio.wait_for(walk, DEFAULT_ROUTE_DEADLINE_SECONDS))

    async def _code_similar(self, **arguments: Any) -> Dict[str, Any]:
        args = _SimilarArgs(**arguments)
        from api.codebase_analytics.endpoints.shared import authorize_source_access

        queries = _queries()
        try:
            await authorize_source_access(args.source_id, _MCP_SOURCE_PRINCIPAL)
        except HTTPException as exc:
            return {"error": exc.detail, "source_id": args.source_id}
        hits = await asyncio.wait_for(
            queries.find_similar_code(args.code, args.source_id, args.pattern_type, args.limit),
            DEFAULT_ROUTE_DEADLINE_SECONDS,
        )
        return bound_lists(queries.similar_code_answer(hits, args.source_id, args.expected_commit))
