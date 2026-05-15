# Redis MCP Bridge Design

**Date:** 2026-03-26
**Status:** Approved
**Issue:** #2511
**Related:** #2133 (Full MCP spec)

## Problem

AutoBot's AI agents cannot directly interact with Redis data. Every query requires a custom API endpoint. Meanwhile, Redis Stack 7.4.0's RediSearch and RedisJSON modules are deployed but unused. Agents also lack visibility into Redis infrastructure health for self-diagnosis.

## Decision

Build `redis_mcp` as the 11th native MCP bridge in AutoBot's registry. Inspired by [redis/mcp-redis](https://github.com/redis/mcp-redis) but implemented natively using `autobot_shared.redis_client` for async support, multi-database routing, connection pooling, and circuit breakers.

**Rejected alternatives:**
- **Subprocess mcp-redis:** Extra process, sync-only, single database, no RBAC — poor fit for AutoBot's architecture.
- **Fork mcp-redis schemas:** Most effort for marginal benefit over native implementation.

## Architecture

```
Agent (LLM) -> tool_call("redis_get", {...})
    -> ToolHandlerMixin._dispatch_tool_call()
        -> MCP Registry lookup (fallback for unknown tools)
            -> redis_mcp bridge (/api/redis/mcp/tools)
                -> RBAC filter (admin vs user role)
                    -> autobot_shared.redis_client (async, pooled, circuit-broken)
                        -> Redis Stack 7.4.0
```

## Tool Definitions (25 tools)

### Data Access (15 tools)

| Tool | Description | User | Admin |
|------|------------|------|-------|
| `redis_get` | Get string value by key | read | read/write |
| `redis_set` | Set string value with optional TTL | scoped | full |
| `redis_delete` | Delete key(s) | scoped | approval |
| `redis_hget` | Get hash field | read | read |
| `redis_hgetall` | Get all hash fields | read | read |
| `redis_hset` | Set hash field | scoped | full |
| `redis_lrange` | Get list range | read | read |
| `redis_lpush` | Push to left of list | scoped | full |
| `redis_rpush` | Push to right of list | scoped | full |
| `redis_zrange` | Get sorted set range | read | read |
| `redis_xrange` | Read stream entries | read | read |
| `redis_xadd` | Add stream entry | scoped | full |
| `redis_scan_keys` | Scan keys by pattern | read | read |
| `redis_type` | Get key type | read | read |
| `redis_ttl` | Get key TTL | read | read |

**Scoped** = writes restricted to `autobot:agent:*` namespace only.

### Vector Search (4 tools)

| Tool | Description | Both Roles |
|------|------------|------------|
| `redis_vector_create_index` | Create vector index on hash keys (HNSW) | full |
| `redis_vector_search` | Similarity search by embedding | full |
| `redis_hybrid_search` | Vector + filter combined query | full |
| `redis_vector_index_info` | Get index schema and key count | full |

### Ops Intelligence (6 tools)

| Tool | Description | User | Admin |
|------|------------|------|-------|
| `redis_server_info` | Server stats (memory, clients, replication) | read | read |
| `redis_dbsize` | Key count per database | read | read |
| `redis_memory_stats` | Detailed memory analysis | read | read |
| `redis_stream_health` | Stream lengths, consumer lag, pending | read | read |
| `redis_client_list` | Connected clients | blocked | read |
| `redis_slowlog` | Recent slow queries | blocked | read |

## RBAC Model

| Role | Data Access | Vector Search | Ops Intelligence | Destructive Ops |
|------|------------|---------------|------------------|-----------------|
| User | Read all + write `autobot:agent:*` | Full | Read-only (no client_list/slowlog) | Blocked |
| Admin | Full read/write | Full | Full | Requires approval |

Approval flow reuses existing `ChatState.pending_approval` mechanism. Agent asks user to confirm before executing destructive operations (DELETE, FLUSHDB, CONFIG SET).

## Vector Search Strategy

**Redis vectors** complement **ChromaDB** — they do not replace it.

| Redis Vectors | ChromaDB |
|--------------|----------|
| Recent conversations (last 24h) | Knowledge base documents |
| Session context embeddings | Long-term facts & relations |
| Real-time agent memory | Indexed files & codebase |
| Quick similarity lookups (<5ms) | Deep RAG retrieval |

**Default index:**

```
Index: idx:agent_memory
  Key prefix: autobot:agent:memory:*
  Schema:
    - embedding: VECTOR (HNSW, 1536 dims, cosine)
    - text: TEXT
    - agent_id: TAG
    - session_id: TAG
    - created_at: NUMERIC
  TTL: 24h auto-expire on underlying keys
```

Embedding generation reuses the existing RAG pipeline's embedding model. The bridge handles text-to-embedding conversion transparently.

## Ops Intelligence

Agents can chain ops tools for composite diagnostics:

1. `redis_server_info` -> check ops/sec and memory
2. `redis_stream_health` -> check pending entry counts
3. `redis_memory_stats` -> check fragmentation ratio
4. Agent synthesizes diagnosis and recommends action

No automated remediation. Agents report findings but do not auto-fix infrastructure.

## Dynamic Tool Discovery

Extends the existing architecture minimally to enable registry-aware dispatch:

1. **Registry-aware dispatch** in `_dispatch_tool_call()`:
   - Known hardcoded tool? Execute directly (existing behavior, unchanged)
   - Unknown tool? Query MCP registry for matching bridge, route to it
   - No match? Return "unknown tool" error (existing #2305 behavior)

2. **Dynamic tool injection** at agent initialization:
   - Fetch available tools from registry, filtered by user role
   - Append to system prompt tool list
   - Registry already has schemas and descriptions

This is a stepping stone toward #2133 (Full MCP spec), not a replacement.

## File Structure

```
autobot-backend/api/redis_mcp/
    __init__.py
    router.py              # FastAPI router, registered in mcp_registry
    tools.py               # Tool definitions (schemas, descriptions)
    data_access.py         # Data access tool handlers
    vector_search.py       # RediSearch vector tool handlers
    ops_intelligence.py    # Server stats / health tool handlers
    rbac.py                # Role-based permission filtering
```

Registered in `mcp_registry.py` as:

```python
MCPBridge(
    name="redis_mcp",
    display_name="Redis Data & Operations",
    endpoint="/api/redis/mcp/tools",
    description="Direct Redis access: data structures, vector search, server ops",
    category="data",
)
```

## Database Routing

Each tool accepts an optional `database` parameter (defaults to `main`). Maps to AutoBot's named databases via `get_redis_client(database=...)`. Supported databases: main, knowledge, prompts, agents, cache, sessions, workflows, vectors, metrics, analytics, facts, logs.

## Error Handling

- Circuit breaker from `redis_management` catches connection failures
- Tools return structured errors: `{"status": "error", "message": "...", "code": "REDIS_UNAVAILABLE"}`
- Agent receives error and can self-correct (per existing #2305 pattern)
- Retry logic handled by the underlying connection manager (exponential backoff, max 3 attempts)
