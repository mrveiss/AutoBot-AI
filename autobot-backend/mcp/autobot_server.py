# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot MCP Server — exposes KB, memory graph, and agent introspection to
external MCP clients (Claude Code, Cline, Gemini CLI, etc.) via JSON-RPC 2.0.

Issue #5072: Implements both stdio (line-by-line JSON-RPC) and HTTP transports.

Architecture:
    AutoBotMCPServer.handle_request(method, params, auth_token)
        |-- kb.*       → KnowledgeBase (knowledge/_composed.py)
        |-- memory.*   → AutoBotMemoryGraph + VerbatimStore
        └── agents.*   → AgentDiaryService + agents/ directory listing

Auth:
    Bearer tokens have the form ``<secret>:<scope1>,<scope2>`` and carry the
    scopes ``kb``, ``memory``, ``agents``.

    ``AUTOBOT_MCP_TOKEN`` is the SECRET SEGMENT ONLY — never the whole bearer
    token (#13266).  It has no default: an unconfigured secret rejects every
    request rather than authenticating everyone.

    HTTP transport:  caller supplies ``Authorization: Bearer <secret>:<scopes>``.
    stdio transport: composes its own bearer from ``AUTOBOT_MCP_TOKEN`` plus
                     ``AUTOBOT_MCP_STDIO_SCOPES`` (see _stdio_bearer_token).

Rate limiting:
    Pre-auth (#13268): failed authentications are counted per client IP *and*
    against an endpoint-wide ceiling before any validation work runs, so the
    secret cannot be brute-forced unmetered and failed attempts cannot be used
    as a Redis amplifier.  See mcp/auth_throttle.py.
    Post-auth: in-memory token bucket per token prefix.
    Both reject with JSON-RPC error code -32029.

Observability:
    Every tool call is logged at INFO level with token-prefix, tool name,
    and wall-clock duration.
"""

import asyncio
import json
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError as PydanticValidationError

from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config
from mcp.auth_throttle import UNKNOWN_IP, get_pre_auth_throttle
from services.run_jwt import validate_run_jwt

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RATE_LIMIT = 50  # requests per 60-second window per token
_WINDOW_SECONDS = 60.0

# Legacy scope → tool prefix (simple token format "secret:kb,memory,agents")
_SCOPE_MAP: Dict[str, str] = {
    "kb": "kb.",
    "memory": "memory.",
    "agents": "agents.",
}

# Run JWT scope → tool prefixes (SEC-2 Phase 2, #6473)
_RUN_JWT_SCOPE_TO_PREFIXES: Dict[str, List[str]] = {
    "mcp:knowledge": ["kb", "memory"],
    "agent:invoke": ["agents"],
    "mcp:filesystem": ["filesystem"],
    "mcp:web_fetch": ["web_fetch"],
    "task:read": ["task"],
    "task:write": ["task"],
}

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _ok(result: Any, req_id: Any = None) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(code: int, message: str, req_id: Any = None) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# stdio bearer composition (#13266)
# ---------------------------------------------------------------------------


def _stdio_bearer_token() -> str:
    """Compose the bearer token the stdio transport presents to itself.

    #13266: ``AUTOBOT_MCP_TOKEN`` used to be read two incompatible ways — as the
    whole ``<secret>:<scopes>`` bearer here, and as the secret segment alone in
    ``_validate_token``. No value satisfied both, so every stdio request was
    rejected. The comparison site is the security boundary, so it keeps owning
    the meaning: ``AUTOBOT_MCP_TOKEN`` is the SECRET, and stdio composes its
    bearer from that secret plus ``AUTOBOT_MCP_STDIO_SCOPES``.

    Raises:
        RuntimeError: if no secret is configured. Deliberately fatal rather than
            defaulted — a shipped default credential authenticates everyone
            exactly as the empty secret did, and this process is the only thing
            standing in front of the kb/memory/agents scopes.
    """
    secret = (config.mcp_token or "").strip()
    if not secret:
        raise RuntimeError(
            "AUTOBOT_MCP_TOKEN is not set. The stdio transport has no default "
            "credential by design; set it to the shared MCP secret to start."
        )
    if ":" in secret:
        # The overloaded pre-#13266 form. _validate_token splits on the first
        # colon, so this value can never match itself; say so instead of
        # emitting an opaque -32001 on every request.
        raise RuntimeError(
            "AUTOBOT_MCP_TOKEN contains ':' — it holds the SECRET SEGMENT ONLY, "
            "not a full '<secret>:<scopes>' token. Move the scopes to "
            "AUTOBOT_MCP_STDIO_SCOPES."
        )
    scopes = ",".join(s.strip() for s in (config.mcp_stdio_scopes or "").split(",") if s.strip())
    if not scopes:
        raise RuntimeError("AUTOBOT_MCP_STDIO_SCOPES resolved to no scopes; stdio transport would grant nothing.")
    return f"{secret}:{scopes}"


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class _TokenBucket:
    """Per-token sliding-window request counter."""

    __slots__ = ("_tokens", "_window_start")

    def __init__(self) -> None:
        self._tokens = 0
        self._window_start = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        if now - self._window_start >= _WINDOW_SECONDS:
            self._tokens = 0
            self._window_start = now
        if self._tokens >= _RATE_LIMIT:
            return False
        self._tokens += 1
        return True


# ---------------------------------------------------------------------------
# Tool definitions (JSON Schema for each parameter set)
# ---------------------------------------------------------------------------

_TOOLS: Dict[str, Dict[str, Any]] = {
    "kb.search": {
        "description": "Hybrid search over the AutoBot knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search query"},
                "filters": {
                    "type": "object",
                    "description": "Optional ChromaDB metadata where clause",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of results",
                },
            },
            "required": ["query"],
        },
    },
    "kb.get_document": {
        "description": "Fetch a full KB document by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Document ID"},
            },
            "required": ["doc_id"],
        },
    },
    "kb.list_categories": {
        "description": "Return the full category tree from the knowledge base.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "kb.list_tags": {
        "description": "Return all tags indexed in the knowledge base.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "memory.entity_lookup": {
        "description": "Look up a memory-graph entity by name — returns entity data and its relations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Entity name to look up"},
            },
            "required": ["name"],
        },
    },
    "memory.timeline": {
        "description": "Return entities related to the given entity, ordered by creation time.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "Entity name"},
                "range": {
                    "type": "string",
                    "description": "Optional ISO-8601 date range string (e.g. '2024-01-01/2024-12-31')",
                },
            },
            "required": ["entity"],
        },
    },
    "memory.related": {
        "description": "Traverse the memory graph starting from an entity up to the specified depth.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "Entity name"},
                "depth": {
                    "type": "integer",
                    "default": 2,
                    "description": "Maximum traversal depth (1-5)",
                },
            },
            "required": ["entity"],
        },
    },
    "memory.path": {
        "description": (
            "Find the shortest relationship path between two memory-graph entities — "
            "answers how two things are connected, not just what is near one of them."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_entity": {"type": "string", "description": "Source entity name"},
                "to_entity": {"type": "string", "description": "Target entity name"},
                "relation": {
                    "type": "string",
                    "description": "Optional relation type to restrict the traversal to",
                },
                "max_depth": {
                    "type": "integer",
                    "default": 6,
                    "description": "Maximum path length in hops (1-10)",
                },
                "direction": {
                    "type": "string",
                    "enum": ["outgoing", "incoming", "both"],
                    "default": "both",
                    "description": "Edge direction to follow; 'both' treats relations as undirected",
                },
            },
            "required": ["from_entity", "to_entity"],
        },
    },
    "memory.verbatim_search": {
        "description": "Search verbatim conversation chunks stored in the VerbatimStore.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "session_filter": {
                    "type": "string",
                    "description": "Optional session_id to restrict results",
                },
            },
            "required": ["query"],
        },
    },
    "agents.list": {
        "description": "List all known AutoBot agent IDs with their descriptions.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "agents.diary_summary": {
        "description": "Return recent diary entries for the named agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Agent name"},
                "last_n": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of entries to return",
                },
            },
            "required": ["agent_name"],
        },
    },
}

# Static agent registry — enumerate agents/ directory names + descriptions.
_AGENT_REGISTRY: List[Dict[str, str]] = [
    {"id": "chat_agent", "description": "General-purpose conversational agent"},
    {"id": "research_agent", "description": "Multi-source research and summarisation"},
    {"id": "code_generation_agent", "description": "Source-code generation and review"},
    {"id": "data_analysis_agent", "description": "Structured data analysis and charting"},
    {"id": "classification_agent", "description": "Text classification via LLM"},
    {"id": "audio_processing_agent", "description": "Transcription and audio analysis"},
    {"id": "kb_librarian_agent", "description": "Knowledge base curation librarian"},
    {"id": "librarian_assistant", "description": "Librarian assistant for KB indexing"},
    {
        "id": "enhanced_system_commands_agent",
        "description": "System-command execution with safety guards",
    },
    {
        "id": "graph_entity_extractor",
        "description": "Extracts entities and relations for the memory graph",
    },
    {
        "id": "development_speedup_agent",
        "description": "Dev workflow acceleration and code scaffolding",
    },
]


# ---------------------------------------------------------------------------
# Main server class
# ---------------------------------------------------------------------------


class AutoBotMCPServer:
    """MCP server that exposes AutoBot KB, memory graph, and agents.

    All tool implementations are thin delegation layers — they call existing
    AutoBot service singletons and serialise results as plain dicts.

    Internal stack traces are never forwarded to the caller; only a generic
    error string is returned to prevent information leakage.
    """

    TOOLS: Dict[str, Dict[str, Any]] = _TOOLS

    def __init__(self) -> None:
        self._buckets: Dict[str, _TokenBucket] = {}

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_run_jwt_scopes(jwt_scopes: List[str]) -> List[str]:
        """Convert run JWT scope claims into the tool-prefix list used by _check_scope."""
        granted: List[str] = []
        for scope in jwt_scopes:
            for prefix in _RUN_JWT_SCOPE_TO_PREFIXES.get(scope, []):
                if prefix not in granted:
                    granted.append(prefix)
        return granted

    @staticmethod
    async def _resolve_run_jwt(token: str) -> Tuple[List[str] | None, str | None]:
        """Validate a run JWT and return (tool_prefixes, error_message).

        Returns (prefixes, None) on success, (None, error) on failure.
        Callers should map None prefixes to a -32001 auth error.
        """
        try:
            claims = await validate_run_jwt(token)
        except JWTExpiredError:
            return None, "Forbidden: run JWT has expired"
        except JWTDecodeError as exc:
            return None, f"Forbidden: {exc}"
        jwt_scopes = claims.get("scope") or []
        if not isinstance(jwt_scopes, list):
            jwt_scopes = []
        prefixes = AutoBotMCPServer._map_run_jwt_scopes([str(s) for s in jwt_scopes])
        return prefixes, None

    @staticmethod
    def _validate_token(token: str) -> List[str] | None:
        """Return the list of granted scopes for *token*, or None if invalid.

        Token format: ``<secret>:<scope1>,<scope2>``.  The secret portion (the
        prefix before the first colon) is compared against ``AUTOBOT_MCP_TOKEN``,
        which holds the secret segment ONLY — this is the single meaning of that
        variable (#13266).  There is no dev override and no default credential.

        Scopes are taken from the token string itself so that the issuer
        controls access.

        Fails closed (#13263): an empty configured secret rejects every token
        rather than matching the empty secret segment of ``":<scopes>"``.
        """
        if not token:
            return None
        try:
            secret_part, scopes_part = token.split(":", 1)
        except ValueError:
            return None
        # #13263: strip so a stray space in .env cannot become the secret —
        # " " is truthy, so " :kb,memory,agents" would otherwise authenticate.
        expected = (config.mcp_token or "").strip()
        # #13263: never authenticate against an unset secret — without this a
        # blank AUTOBOT_MCP_TOKEN would accept ":kb,memory,agents" from anyone,
        # with the scopes chosen by the caller. The `not expected` test must stay
        # first so the empty case never reaches the comparison.
        #
        # compare_digest because this is a long-lived shared secret checked on an
        # endpoint with no other auth layer (CWE-208); same primitive as
        # middleware/service_auth_enforcement.py.
        if not expected or not secrets.compare_digest(secret_part, expected):
            return None
        scopes = [s.strip() for s in scopes_part.split(",") if s.strip()]
        return scopes if scopes else None

    async def _validate_redis_token(self, token: str) -> Optional[List[str]]:
        """Look up *token* in Redis and return its scopes, or None if not found.

        Token format: ``<secret>:<scope1>,<scope2>`` — the secret portion is
        the Redis lookup key under ``mcp:token:by_secret:{secret}``.  On a
        successful lookup ``last_used`` is updated in-place.

        This method is called as a fallback when ``_validate_token()`` rejects
        the token (i.e. the secret does not match the static env-var secret).
        Redis-issued tokens created via ``POST /api/mcp/tokens`` are validated
        here, enabling runtime token issuance and revocation without restart.
        """
        if not token:
            return None
        try:
            secret_part, _ = token.split(":", 1)
        except ValueError:
            return None

        try:
            redis = await get_async_redis_client(database="main")
            if redis is None:
                logger.warning("_validate_redis_token: Redis unavailable")
                return None

            key = f"mcp:token:by_secret:{secret_part}"
            raw = await redis.get(key)
            if raw is None:
                return None

            record = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
            scopes: List[str] = record.get("scopes") or []
            if not scopes:
                return None

            # Update last_used timestamp
            record["last_used"] = time.time()
            await redis.set(key, json.dumps(record, ensure_ascii=False))
            return scopes
        except Exception as exc:
            logger.warning("_validate_redis_token: unexpected error: %s", exc)
            return None

    @staticmethod
    def _pre_auth_gate(method: str, client_ip: str, req_id: Any) -> Dict[str, Any] | None:
        """Reject *client_ip* if it has exhausted its failed-auth budget (#13268).

        Runs BEFORE any validation work: ahead of _validate_redis_token so a
        locked-out caller cannot drive a Redis GET per request, and ahead of the
        secret comparison so guessing the secret is metered.

        Returns a JSON-RPC error to send, or None to continue.
        """
        blocked, reason = get_pre_auth_throttle().check(client_ip)
        if not blocked:
            return None
        logger.warning("mcp_auth: pre-auth throttle blocked method=%s — %s", method or "<none>", reason)
        return _err(-32029, f"Too many failed authentication attempts: {reason}", req_id)

    async def _authenticate(
        self,
        params: Dict[str, Any],
        auth_token: str,
        req_id: Any,
        client_ip: str,
    ) -> Tuple[List[str] | None, bool, Dict[str, Any] | None]:
        """Resolve granted scopes, metering failures against the pre-auth throttle.

        SEC-2 Phase 2 (#6473): a run JWT in ``params`` takes precedence over the
        legacy static token. Agents pass it as a top-level JSON-RPC param; the
        scheduler also exposes it via AUTOBOT_RUN_JWT for in-process callers.

        Returns ``(scopes, using_run_jwt, error_response)`` — exactly one of
        *scopes* and *error_response* is non-None.
        """
        run_jwt_token = params.pop("run_jwt", None) if isinstance(params, dict) else None

        if run_jwt_token:
            scopes, error = await self._resolve_run_jwt(run_jwt_token)
            if error:
                return None, False, self._reject_auth(client_ip, error, req_id)
            get_pre_auth_throttle().record_success(client_ip)
            return scopes, True, None

        scopes = self._validate_token(auth_token)
        if scopes is None:
            # Fallback: check Redis-issued tokens (Issue #6453)
            scopes = await self._validate_redis_token(auth_token)
        if scopes is None:
            return None, False, self._reject_auth(client_ip, "Unauthorized: invalid or missing token", req_id)
        get_pre_auth_throttle().record_success(client_ip)
        return scopes, False, None

    @staticmethod
    def _reject_auth(client_ip: str, message: str, req_id: Any) -> Dict[str, Any]:
        """Count one failed authentication and build its JSON-RPC error (#13268).

        Never silent: every rejection is logged with its reason before returning.
        """
        get_pre_auth_throttle().record_failure(client_ip)
        logger.warning("mcp_auth: rejected MCP request — %s", message)
        return _err(-32001, message, req_id)

    def _check_scope(self, scopes: List[str], tool_name: str) -> bool:
        """Return True if *scopes* grants access to *tool_name*."""
        prefix = tool_name.split(".")[0]  # "kb", "memory", "agents"
        return prefix in scopes

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _is_rate_limited(self, token_key: str) -> bool:
        if token_key not in self._buckets:
            self._buckets[token_key] = _TokenBucket()
        return not self._buckets[token_key].allow()

    # ------------------------------------------------------------------
    # Public dispatch
    # ------------------------------------------------------------------

    async def handle_request(
        self,
        method: str,
        params: Dict[str, Any],
        auth_token: str,
        req_id: Any = None,
        client_ip: str | None = None,
    ) -> Dict[str, Any]:
        """Dispatch a JSON-RPC method call.

        Recognised methods:
            ``initialize``  — returns server capabilities + tool list.
            ``tools/list``  — alias for the MCP tools manifest.
            ``tools/call``  — invoke a named tool.

        Args:
            method:     JSON-RPC method string.
            params:     JSON-RPC params dict.
            auth_token: Bearer token (validated here).
            req_id:     JSON-RPC ``id`` (echoed in response).
            client_ip:  Caller address for the pre-auth throttle (#13268).
                        Transports resolve it; ``None`` collapses to a shared
                        ``UNKNOWN_IP`` bucket, which throttles more, never less.

        Returns:
            JSON-RPC response dict (always includes ``jsonrpc`` and ``id``).
        """
        ip = client_ip or UNKNOWN_IP
        throttled = self._pre_auth_gate(method, ip, req_id)
        if throttled is not None:
            return throttled

        # Bucket key is captured before _authenticate pops run_jwt out of params.
        run_jwt_preview = params.get("run_jwt") if isinstance(params, dict) else None
        rate_key = (run_jwt_preview or auth_token or "")[:16]

        scopes, using_run_jwt, auth_error = await self._authenticate(params, auth_token, req_id, ip)
        if auth_error is not None:
            return auth_error

        # Post-auth bucket stays keyed on the token prefix: it is only reachable
        # by an authenticated caller, so the key space cannot be grown by an
        # anonymous attacker (#13268).
        if self._is_rate_limited(rate_key):
            logger.warning("mcp_auth: post-auth rate limit exceeded for method=%s", method or "<none>")
            return _err(-32029, f"Rate limit exceeded ({_RATE_LIMIT} req/{int(_WINDOW_SECONDS)}s)", req_id)

        if method in ("initialize", "tools/list"):
            return _ok(
                {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "autobot-mcp", "version": "1.0.0"},
                    "tools": [
                        {"name": name, **meta} for name, meta in self.TOOLS.items() if self._check_scope(scopes, name)
                    ],
                },
                req_id,
            )

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            return await self._dispatch_tool(tool_name, arguments, scopes, req_id, using_run_jwt=using_run_jwt)

        return _err(-32601, f"Method not found: {method}", req_id)

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    async def _dispatch_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        scopes: List[str],
        req_id: Any,
        using_run_jwt: bool = False,
    ) -> Dict[str, Any]:
        if tool_name not in self.TOOLS:
            return _err(-32602, f"Unknown tool: {tool_name}", req_id)
        if not self._check_scope(scopes, tool_name):
            if using_run_jwt:
                # 403 Forbidden: valid run JWT but insufficient scope for this tool
                return _err(-32003, f"Forbidden: run JWT lacks scope for tool: {tool_name}", req_id)
            return _err(-32001, f"Scope denied for tool: {tool_name}", req_id)

        t0 = time.monotonic()
        try:
            handler = getattr(self, f"_{tool_name.replace('.', '_')}", None)
            if handler is None:
                return _err(-32603, f"Handler not implemented: {tool_name}", req_id)
            result = await handler(**arguments)
            elapsed = time.monotonic() - t0
            logger.info("mcp tool_call tool=%s elapsed=%.3fs", tool_name, elapsed)
            return _ok({"content": [{"type": "text", "text": json.dumps(result, default=str)}]}, req_id)
        except (TypeError, PydanticValidationError) as exc:
            # #13762: a handler that validates its arguments through a request
            # model raises ValidationError, which is an invalid-arguments error
            # (-32602), not an internal one. Without this it fell to -32603 and
            # read to the caller as a server fault.
            logger.warning("mcp bad_arguments tool=%s error=%s", tool_name, exc)
            return _err(-32602, f"Invalid arguments: {exc}", req_id)
        except Exception as exc:
            logger.error("mcp tool_error tool=%s error=%s", tool_name, exc, exc_info=True)
            return _err(-32603, "Internal error executing tool", req_id)

    # ------------------------------------------------------------------
    # KB tool implementations
    # ------------------------------------------------------------------

    async def _kb_search(
        self,
        query: str,
        filters: Dict[str, Any] | None = None,
        limit: int = 10,
    ) -> Any:
        from knowledge._composed import get_knowledge_base

        kb = await get_knowledge_base()
        results = await kb.search(query, top_k=limit, filters=filters)
        return {"results": results, "count": len(results)}

    async def _kb_get_document(self, doc_id: str) -> Any:
        from knowledge._composed import get_knowledge_base

        kb = await get_knowledge_base()
        doc = await kb.get_fact(doc_id)
        if doc is None:
            return {"error": "Document not found", "doc_id": doc_id}
        return doc

    async def _kb_list_categories(self) -> Any:
        from knowledge._composed import get_knowledge_base

        kb = await get_knowledge_base()
        result = await kb.get_category_tree()
        return result

    async def _kb_list_tags(self) -> Any:
        from knowledge._composed import get_knowledge_base

        kb = await get_knowledge_base()
        result = await kb.list_all_tags()
        return result

    # ------------------------------------------------------------------
    # Memory graph tool implementations
    # ------------------------------------------------------------------

    async def _memory_entity_lookup(self, name: str) -> Any:
        from api.schemas_knowledge import MemoryEntityLookupRequest
        from autobot_memory_graph import AutoBotMemoryGraph

        name = MemoryEntityLookupRequest(name=name).name
        graph = AutoBotMemoryGraph()
        await graph.initialize()
        entity = await graph.get_entity(entity_name=name, include_relations=True)
        if entity is None:
            return {"error": "Entity not found", "name": name}
        return entity

    async def _memory_timeline(self, entity: str, range: str | None = None) -> Any:
        from api.schemas_knowledge import MemoryTimelineRequest
        from autobot_memory_graph import AutoBotMemoryGraph

        args = MemoryTimelineRequest(entity=entity, range=range)
        entity, range = args.entity, args.range
        graph = AutoBotMemoryGraph()
        await graph.initialize()
        base = await graph.get_entity(entity_name=entity, include_relations=True)
        if base is None:
            return {"error": "Entity not found", "entity": entity}

        entity_id = base.get("id", "")
        relations_data = await graph.get_relations(entity_id, direction="both")
        relations = relations_data.get("relations", [])

        # Gather linked entity IDs and their details
        neighbour_ids = {r.get("from_entity") for r in relations} | {r.get("to_entity") for r in relations}
        neighbour_ids.discard(entity_id)

        neighbours = []
        for nid in list(neighbour_ids)[:50]:
            ent = await graph.get_entity(entity_id=nid)
            if ent:
                neighbours.append(ent)

        # Sort by created_at ascending (timeline order)
        neighbours.sort(key=lambda e: (e.get("metadata") or {}).get("created_at", ""), reverse=False)
        if range:
            # range is "start/end"; filter by created_at string prefix comparison
            parts = range.split("/", 1)
            start, end = (parts[0], parts[1]) if len(parts) == 2 else (parts[0], None)
            neighbours = [
                e
                for e in neighbours
                if (e.get("metadata") or {}).get("created_at", "") >= start
                and (end is None or (e.get("metadata") or {}).get("created_at", "") <= end)
            ]

        return {"entity": base, "timeline": neighbours, "count": len(neighbours)}

    async def _memory_related(self, entity: str, depth: int = 2) -> Any:
        from api.schemas_knowledge import MemoryRelatedRequest
        from autobot_memory_graph import AutoBotMemoryGraph

        # #13762: the entity name was unbounded. ``depth`` keeps its existing
        # clamp rather than becoming a rejection, so the model's ge/le is the
        # declared contract and the clamp is what enforces it.
        args = MemoryRelatedRequest(entity=entity, depth=max(1, min(depth, 5)))
        entity, depth = args.entity, args.depth
        graph = AutoBotMemoryGraph()
        await graph.initialize()

        root = await graph.get_entity(entity_name=entity, include_relations=True)
        if root is None:
            return {"error": "Entity not found", "entity": entity}

        visited: Dict[str, Any] = {}
        frontier = [root.get("id", "")]

        for _ in range(depth):
            next_frontier = []
            for eid in frontier:
                if eid in visited:
                    continue
                ent = await graph.get_entity(entity_id=eid)
                if not ent:
                    continue
                visited[eid] = ent
                rels = await graph.get_relations(eid, direction="both")
                for rel in rels.get("relations", []):
                    cand = rel.get("to_entity") or rel.get("from_entity")
                    if cand and cand not in visited:
                        next_frontier.append(cand)
            frontier = next_frontier
            if not frontier:
                break

        return {
            "root": root,
            "related": list(visited.values()),
            "count": len(visited),
        }

    async def _memory_path(
        self,
        from_entity: str,
        to_entity: str,
        relation: str | None = None,
        max_depth: int = 6,
        direction: str = "both",
    ) -> Any:
        """Shortest relationship path between two entities (#13474).

        Delegates to AutoBotMemoryGraph.find_path so name resolution and path
        serialisation are not duplicated against the Graph-RAG ``/path``
        endpoint. #13762 extends that to the input contract: the arguments go
        through ``GraphRAGPathRequest``, the same model the REST route binds, so
        the two surfaces cannot drift on what a valid request is. ``max_depth``
        stays clamped rather than rejected — an untrusted caller must not be
        able to request an unbounded traversal, but asking for too much is not
        an error the way an unbounded entity name is.
        """
        from api.schemas_knowledge import GraphRAGPathRequest
        from autobot_memory_graph import AutoBotMemoryGraph

        allowed_directions = ("outgoing", "incoming", "both")
        if direction not in allowed_directions:
            return {"error": "Invalid direction", "direction": direction, "allowed": list(allowed_directions)}

        args = GraphRAGPathRequest(
            from_entity=from_entity,
            to_entity=to_entity,
            relation=relation,
            max_depth=max(1, min(max_depth, 10)),
            direction=direction,
        )

        graph = AutoBotMemoryGraph()
        await graph.initialize()
        return await graph.find_path(
            from_entity=args.from_entity,
            to_entity=args.to_entity,
            relation=args.relation,
            max_depth=args.max_depth,
            direction=args.direction,
        )

    async def _memory_verbatim_search(self, query: str, session_filter: str | None = None) -> Any:
        from api.schemas_knowledge import MemoryVerbatimSearchRequest
        from memory.verbatim_store import VerbatimStore

        args = MemoryVerbatimSearchRequest(query=query, session_filter=session_filter)
        store = VerbatimStore()
        results = await store.search(args.query, session_filter=args.session_filter)
        return {"results": results, "count": len(results)}

    # ------------------------------------------------------------------
    # Agent tool implementations
    # ------------------------------------------------------------------

    async def _agents_list(self) -> Any:
        return {"agents": _AGENT_REGISTRY, "count": len(_AGENT_REGISTRY)}

    async def _agents_diary_summary(self, agent_name: str, last_n: int = 10) -> Any:
        from memory.agent_diary import AgentDiaryService

        diary = AgentDiaryService()
        entries = await diary.read(agent_name, last_n=last_n)
        return {"agent": agent_name, "entries": entries, "count": len(entries)}

    # ------------------------------------------------------------------
    # stdio transport
    # ------------------------------------------------------------------

    async def serve_stdio(self) -> None:
        """Read JSON-RPC requests from stdin line-by-line, write responses to stdout."""
        import sys

        token = _stdio_bearer_token()
        loop = asyncio.get_event_loop()

        reader = asyncio.StreamReader()
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)

        writer_transport, writer_proto = await loop.connect_write_pipe(asyncio.BaseProtocol, sys.stdout.buffer)

        logger.info("AutoBotMCPServer: stdio transport started")

        while True:
            try:
                line = await reader.readline()
            except Exception as exc:
                logger.warning("stdio read error: %s", exc)
                break
            if not line:
                break
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                response = _err(-32700, "Parse error")
            else:
                method = msg.get("method", "")
                params = msg.get("params") or {}
                req_id = msg.get("id")
                response = await self.handle_request(method, params, token, req_id, client_ip="stdio")
            out = json.dumps(response, default=str) + "\n"
            writer_transport.write(out.encode("utf-8"))

    # ------------------------------------------------------------------
    # HTTP transport
    # ------------------------------------------------------------------

    async def serve_http(
        self,
        host: str = "0.0.0.0",
        port: int = 8200,  # nosec B104  # intentional bind to all interfaces for service/test
    ) -> None:
        """Run an aiohttp server accepting ``POST /mcp/tool`` requests."""
        from aiohttp import web

        async def _handle(request: web.Request) -> web.Response:
            auth_header = request.headers.get("Authorization", "")
            token = auth_header.removeprefix("Bearer ").strip()
            try:
                body = await request.json()
            except Exception:
                return web.Response(
                    status=400,
                    content_type="application/json",
                    text=json.dumps(_err(-32700, "Parse error")),
                )
            method = body.get("method", "")
            params = body.get("params") or {}
            req_id = body.get("id")
            response = await self.handle_request(method, params, token, req_id, client_ip=request.remote)
            status = 200
            if "error" in response:
                code = response["error"].get("code", -32000)
                if code == -32001:
                    status = 401
                elif code == -32003:
                    status = 403
                elif code == -32029:
                    status = 429
            return web.Response(
                status=status,
                content_type="application/json",
                text=json.dumps(response, default=str),
            )

        app = web.Application()
        app.router.add_post("/mcp/tool", _handle)
        app.router.add_post("/mcp", _handle)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info("AutoBotMCPServer: HTTP transport listening on %s:%d", host, port)
        await asyncio.Event().wait()  # run forever
