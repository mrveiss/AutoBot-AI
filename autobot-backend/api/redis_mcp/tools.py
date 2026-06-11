# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
MCP tool definitions (schemas and descriptions) for Redis MCP Bridge.

Issue #2511: 25 tool definitions across 3 categories.
Follows the pattern established by filesystem_mcp.py (Issue #620 refactoring).
"""

from __future__ import annotations

from pydantic import BaseModel

from type_defs.common import JSONObject


class MCPTool(BaseModel):
    """Standard MCP tool definition."""

    name: str
    description: str
    input_schema: JSONObject


# ---------------------------------------------------------------------------
# Data Access Tools (15)
# ---------------------------------------------------------------------------


def _tool_redis_get() -> MCPTool:
    return MCPTool(
        name="redis_get",
        description="Get a string value by key from Redis.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Redis key to retrieve"},
                "database": {
                    "type": "string",
                    "description": "Named database (default: main)",
                    "default": "main",
                },
            },
            "required": ["key"],
        },
    )


def _tool_redis_set() -> MCPTool:
    return MCPTool(
        name="redis_set",
        description="Set a string value with optional TTL. Users: autobot:agent:* only.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Redis key to set"},
                "value": {"type": "string", "description": "Value to store"},
                "ttl": {
                    "type": "integer",
                    "description": "Optional TTL in seconds",
                },
                "database": {
                    "type": "string",
                    "description": "Named database (default: main)",
                    "default": "main",
                },
            },
            "required": ["key", "value"],
        },
    )


def _tool_redis_delete() -> MCPTool:
    return MCPTool(
        name="redis_delete",
        description="Delete one or more keys. Users: autobot:agent:* only. Admins: approval required.",
        input_schema={
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keys to delete",
                },
                "database": {
                    "type": "string",
                    "description": "Named database (default: main)",
                    "default": "main",
                },
            },
            "required": ["keys"],
        },
    )


def _tool_redis_hget() -> MCPTool:
    return MCPTool(
        name="redis_hget",
        description="Get a single field from a Redis hash.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Hash key"},
                "field": {"type": "string", "description": "Field name"},
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key", "field"],
        },
    )


def _tool_redis_hgetall() -> MCPTool:
    return MCPTool(
        name="redis_hgetall",
        description="Get all fields and values from a Redis hash.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Hash key"},
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key"],
        },
    )


def _tool_redis_hset() -> MCPTool:
    return MCPTool(
        name="redis_hset",
        description="Set one or more fields in a Redis hash. Users: autobot:agent:* only.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Hash key"},
                "mapping": {
                    "type": "object",
                    "description": "Field-value pairs to set",
                },
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key", "mapping"],
        },
    )


def _tool_redis_lrange() -> MCPTool:
    return MCPTool(
        name="redis_lrange",
        description="Get a range of elements from a Redis list.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "List key"},
                "start": {
                    "type": "integer",
                    "description": "Start index (0-based)",
                    "default": 0,
                },
                "stop": {
                    "type": "integer",
                    "description": "Stop index (-1 for all)",
                    "default": -1,
                },
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key"],
        },
    )


def _tool_redis_lpush() -> MCPTool:
    return MCPTool(
        name="redis_lpush",
        description=(
            "Push values to the left of a Redis list. Users: autobot:agent:* only. "
            "autobot:agent:memory:* keys receive a 24h TTL automatically; pass ttl=0 to suppress."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "List key"},
                "values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Values to push",
                },
                "ttl": {
                    "type": "integer",
                    "description": "Optional TTL in seconds (0 = no expiry)",
                },
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key", "values"],
        },
    )


def _tool_redis_rpush() -> MCPTool:
    return MCPTool(
        name="redis_rpush",
        description=(
            "Push values to the right of a Redis list. Users: autobot:agent:* only. "
            "autobot:agent:memory:* keys receive a 24h TTL automatically; pass ttl=0 to suppress."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "List key"},
                "values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Values to push",
                },
                "ttl": {
                    "type": "integer",
                    "description": "Optional TTL in seconds (0 = no expiry)",
                },
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key", "values"],
        },
    )


def _tool_redis_zrange() -> MCPTool:
    return MCPTool(
        name="redis_zrange",
        description="Get a range of elements from a sorted set, with optional scores.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Sorted set key"},
                "start": {"type": "integer", "default": 0},
                "stop": {"type": "integer", "default": -1},
                "withscores": {
                    "type": "boolean",
                    "description": "Include scores",
                    "default": False,
                },
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key"],
        },
    )


def _tool_redis_xrange() -> MCPTool:
    return MCPTool(
        name="redis_xrange",
        description="Read entries from a Redis stream.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Stream key"},
                "start": {
                    "type": "string",
                    "description": "Start ID (default: '-' for earliest)",
                    "default": "-",
                },
                "end": {
                    "type": "string",
                    "description": "End ID (default: '+' for latest)",
                    "default": "+",
                },
                "count": {
                    "type": "integer",
                    "description": "Max entries to return",
                },
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key"],
        },
    )


def _tool_redis_xadd() -> MCPTool:
    return MCPTool(
        name="redis_xadd",
        description=(
            "Add an entry to a Redis stream. Users: autobot:agent:* only. "
            "autobot:agent:memory:* keys receive a 24h TTL automatically; pass ttl=0 to suppress."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Stream key"},
                "fields": {
                    "type": "object",
                    "description": "Field-value pairs for the stream entry",
                },
                "maxlen": {
                    "type": "integer",
                    "description": "Optional max stream length (approximate trim)",
                },
                "ttl": {
                    "type": "integer",
                    "description": "Optional TTL in seconds (0 = no expiry)",
                },
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key", "fields"],
        },
    )


def _tool_redis_scan_keys() -> MCPTool:
    return MCPTool(
        name="redis_scan_keys",
        description="Scan keys matching a glob pattern. Returns up to 100 keys per call.",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. 'autobot:agent:*')",
                    "default": "*",
                },
                "count": {
                    "type": "integer",
                    "description": "Hint for keys per scan iteration",
                    "default": 100,
                },
                "database": {"type": "string", "default": "main"},
            },
        },
    )


def _tool_redis_type() -> MCPTool:
    return MCPTool(
        name="redis_type",
        description="Get the data type of a Redis key.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Redis key"},
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key"],
        },
    )


def _tool_redis_ttl() -> MCPTool:
    return MCPTool(
        name="redis_ttl",
        description="Get the remaining TTL (in seconds) of a Redis key. -1 = no expiry, -2 = key missing.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Redis key"},
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key"],
        },
    )


# ---------------------------------------------------------------------------
# Vector Search Tools (4)
# ---------------------------------------------------------------------------


def _tool_redis_vector_create_index() -> MCPTool:
    return MCPTool(
        name="redis_vector_create_index",
        description=(
            "Create a RediSearch vector index on hash keys using HNSW algorithm. "
            "Default: idx:agent_memory on autobot:agent:memory:* with 1536 dims. "
            "RediSearch FT.CREATE requires DB 0; use database='memory' (DB 0 alias) "
            "for agent-memory indexes."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "index_name": {
                    "type": "string",
                    "description": "Index name",
                    "default": "idx:agent_memory",
                },
                "prefix": {
                    "type": "string",
                    "description": "Key prefix to index",
                    "default": "autobot:agent:memory:",
                },
                "vector_field": {
                    "type": "string",
                    "description": "Field name for the vector",
                    "default": "embedding",
                },
                "dimensions": {
                    "type": "integer",
                    "description": "Vector dimensions",
                    "default": 1536,
                },
                "distance_metric": {
                    "type": "string",
                    "enum": ["COSINE", "L2", "IP"],
                    "description": "Distance metric",
                    "default": "COSINE",
                },
                "extra_fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["TEXT", "TAG", "NUMERIC"],
                            },
                        },
                        "required": ["name", "type"],
                    },
                    "description": "Additional schema fields (TEXT, TAG, NUMERIC)",
                },
                "database": {"type": "string", "default": "memory"},
            },
        },
    )


def _tool_redis_vector_search() -> MCPTool:
    return MCPTool(
        name="redis_vector_search",
        description=(
            "Similarity search using a RediSearch index. "
            "Provide query_text (auto-embedded) or query_vector (raw floats)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "index_name": {
                    "type": "string",
                    "description": "Index to search",
                    "default": "idx:agent_memory",
                },
                "query_text": {
                    "type": "string",
                    "description": "Text to embed and search (alternative to query_vector)",
                },
                "query_vector": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Raw embedding vector (alternative to query_text)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results",
                    "default": 10,
                },
                "return_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fields to return (default: all)",
                },
                "database": {"type": "string", "default": "memory"},
            },
        },
    )


def _tool_redis_hybrid_search() -> MCPTool:
    return MCPTool(
        name="redis_hybrid_search",
        description=(
            "Combined vector + filter query using RediSearch. "
            "Provide query_text (auto-embedded) or query_vector (raw floats)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "index_name": {
                    "type": "string",
                    "default": "idx:agent_memory",
                },
                "query_text": {
                    "type": "string",
                    "description": "Text to embed and search (alternative to query_vector)",
                },
                "query_vector": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Raw embedding vector (alternative to query_text)",
                },
                "filter_expression": {
                    "type": "string",
                    "description": "RediSearch filter (e.g. '@agent_id:{agent_42}')",
                },
                "top_k": {"type": "integer", "default": 10},
                "return_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "database": {"type": "string", "default": "memory"},
            },
            "required": ["filter_expression"],
        },
    )


def _tool_redis_vector_index_info() -> MCPTool:
    return MCPTool(
        name="redis_vector_index_info",
        description="Get schema, key count, and stats for a RediSearch index.",
        input_schema={
            "type": "object",
            "properties": {
                "index_name": {
                    "type": "string",
                    "default": "idx:agent_memory",
                },
                "database": {"type": "string", "default": "memory"},
            },
        },
    )


# ---------------------------------------------------------------------------
# Ops Intelligence Tools (6)
# ---------------------------------------------------------------------------


def _tool_redis_server_info() -> MCPTool:
    return MCPTool(
        name="redis_server_info",
        description="Get Redis server stats: memory, clients, replication, keyspace.",
        input_schema={
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Optional INFO section (e.g. 'memory', 'clients', 'stats')",
                },
                "database": {"type": "string", "default": "main"},
            },
        },
    )


def _tool_redis_dbsize() -> MCPTool:
    return MCPTool(
        name="redis_dbsize",
        description="Get the number of keys in the current database.",
        input_schema={
            "type": "object",
            "properties": {
                "database": {"type": "string", "default": "main"},
            },
        },
    )


def _tool_redis_memory_stats() -> MCPTool:
    return MCPTool(
        name="redis_memory_stats",
        description="Get detailed memory analysis: used, peak, fragmentation ratio, allocator stats.",
        input_schema={
            "type": "object",
            "properties": {
                "database": {"type": "string", "default": "main"},
            },
        },
    )


def _tool_redis_stream_health() -> MCPTool:
    return MCPTool(
        name="redis_stream_health",
        description="Check stream health: length, consumer groups, pending entries, last entry ID.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Stream key to inspect"},
                "database": {"type": "string", "default": "main"},
            },
            "required": ["key"],
        },
    )


def _tool_redis_client_list() -> MCPTool:
    return MCPTool(
        name="redis_client_list",
        description="List connected Redis clients. Admin only.",
        input_schema={
            "type": "object",
            "properties": {
                "database": {"type": "string", "default": "main"},
            },
        },
    )


def _tool_redis_slowlog() -> MCPTool:
    return MCPTool(
        name="redis_slowlog",
        description="Get recent slow queries from Redis slowlog. Admin only.",
        input_schema={
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of entries to return",
                    "default": 10,
                },
                "database": {"type": "string", "default": "main"},
            },
        },
    )


# ---------------------------------------------------------------------------
# Grouped accessors (Issue #620 pattern)
# ---------------------------------------------------------------------------


def get_data_access_tools() -> list[MCPTool]:
    """Return all 15 data access tool definitions."""
    return [
        _tool_redis_get(),
        _tool_redis_set(),
        _tool_redis_delete(),
        _tool_redis_hget(),
        _tool_redis_hgetall(),
        _tool_redis_hset(),
        _tool_redis_lrange(),
        _tool_redis_lpush(),
        _tool_redis_rpush(),
        _tool_redis_zrange(),
        _tool_redis_xrange(),
        _tool_redis_xadd(),
        _tool_redis_scan_keys(),
        _tool_redis_type(),
        _tool_redis_ttl(),
    ]


def get_vector_search_tools() -> list[MCPTool]:
    """Return all 4 vector search tool definitions."""
    return [
        _tool_redis_vector_create_index(),
        _tool_redis_vector_search(),
        _tool_redis_hybrid_search(),
        _tool_redis_vector_index_info(),
    ]


def get_ops_intelligence_tools() -> list[MCPTool]:
    """Return all 6 ops intelligence tool definitions."""
    return [
        _tool_redis_server_info(),
        _tool_redis_dbsize(),
        _tool_redis_memory_stats(),
        _tool_redis_stream_health(),
        _tool_redis_client_list(),
        _tool_redis_slowlog(),
    ]


def get_all_tools() -> list[MCPTool]:
    """Return all 25 Redis MCP tool definitions."""
    tools: list[MCPTool] = []
    tools.extend(get_data_access_tools())
    tools.extend(get_vector_search_tools())
    tools.extend(get_ops_intelligence_tools())
    return tools
