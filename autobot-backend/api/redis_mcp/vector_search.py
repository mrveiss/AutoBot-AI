# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Vector Search tool handlers for Redis MCP Bridge (4 tools).

Issue #2511: RediSearch vector index creation, similarity search,
hybrid search, and index info — using Redis Stack 7.4.0 FT.* commands.
Issue #2623: Transparent text-to-embedding conversion via NPU/Ollama fallback.
"""

import re
import struct
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from type_defs.common import Metadata

logger = get_logger(__name__)

# Upper bound for KNN top_k to prevent resource exhaustion (#2511)
_MAX_TOP_K = 500

# Allow only safe RediSearch filter tokens: alphanumerics, field refs (@),
# comparisons, parentheses, spaces, colons, hyphens, underscores, dots.
_SAFE_FILTER_PATTERN = re.compile(r"^[@\w\s:.\-()=<>|&*{}\[\],\"']+$")


async def _text_to_embedding(text: str) -> List[float]:
    """Convert text to embedding using the existing RAG pipeline (Issue #2623).

    Uses NPU worker with Ollama fallback — same pipeline as knowledge base.
    """
    from knowledge.facts import _generate_embedding_with_npu_fallback

    return await _generate_embedding_with_npu_fallback(text)


async def _get_client(database: str = "vectors"):
    """Get an async Redis client for vector operations."""
    return await get_async_redis_client(database=database)


def _float_list_to_bytes(vector: List[float]) -> bytes:
    """Pack a list of floats into a binary blob for RediSearch KNN queries."""
    return struct.pack(f"{len(vector)}f", *vector)


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


def _build_index_schema(
    vector_field: str,
    dimensions: int,
    distance_metric: str,
    extra_fields: List[Dict[str, str]] | None = None,
) -> List[Any]:
    """Build FT.CREATE SCHEMA arguments for a vector index (#2511)."""
    schema: List[Any] = []
    if extra_fields:
        for field in extra_fields:
            schema.extend([field["name"], field["type"]])
    schema.extend(
        [
            vector_field,
            "VECTOR",
            "HNSW",
            "6",
            "TYPE",
            "FLOAT32",
            "DIM",
            str(dimensions),
            "DISTANCE_METRIC",
            distance_metric,
        ]
    )
    return schema


async def handle_redis_vector_create_index(
    index_name: str = "idx:agent_memory",
    prefix: str = "autobot:agent:memory:",
    vector_field: str = "embedding",
    dimensions: int = 1536,
    distance_metric: str = "COSINE",
    extra_fields: List[Dict[str, str]] | None = None,
    database: str = "vectors",
) -> Metadata:
    """Create a RediSearch vector index using HNSW."""
    client = await _get_client(database)
    schema_args = _build_index_schema(vector_field, dimensions, distance_metric, extra_fields)
    try:
        await client.execute_command(
            "FT.CREATE",
            index_name,
            "ON",
            "HASH",
            "PREFIX",
            "1",
            prefix,
            "SCHEMA",
            *schema_args,
        )
        return {
            "status": "success",
            "index_name": index_name,
            "prefix": prefix,
            "dimensions": dimensions,
            "distance_metric": distance_metric,
        }
    except Exception as e:
        if "Index already exists" in str(e):
            return {
                "status": "success",
                "index_name": index_name,
                "message": "Index already exists",
            }
        raise


async def _execute_vector_query(
    query_str: str,
    query_vector: List[float] | None,
    query_text: str | None,
    index_name: str,
    top_k: int,
    return_fields: List[str] | None,
    database: str,
    extra_meta: Dict[str, Any] | None = None,
) -> Metadata:
    """Shared KNN query execution for vector and hybrid search (#2511)."""
    if query_vector is None and query_text is None:
        return {
            "status": "error",
            "message": "Provide either query_text or query_vector",
            "code": "MISSING_QUERY",
        }
    top_k = min(max(1, top_k), _MAX_TOP_K)
    if query_vector is None:
        query_vector = await _text_to_embedding(query_text)
    client = await _get_client(database)
    blob = _float_list_to_bytes(query_vector)

    cmd_args = [
        "FT.SEARCH",
        index_name,
        query_str,
        "PARAMS",
        "2",
        "BLOB",
        blob,
        "SORTBY",
        "score",
        "DIALECT",
        "2",
    ]
    if return_fields:
        cmd_args.extend(["RETURN", str(len(return_fields) + 1), "score"])
        cmd_args.extend(return_fields)

    raw = await client.execute_command(*cmd_args)
    results = _parse_ft_search_results(raw)
    meta: Dict[str, Any] = {
        "status": "success",
        "index_name": index_name,
        "results": results,
        "count": len(results),
    }
    if extra_meta:
        meta.update(extra_meta)
    return meta


async def handle_redis_vector_search(
    query_vector: List[float] | None = None,
    query_text: str | None = None,
    index_name: str = "idx:agent_memory",
    top_k: int = 10,
    return_fields: List[str] | None = None,
    database: str = "vectors",
) -> Metadata:
    """Similarity search by embedding vector or text (Issue #2623)."""
    top_k = min(max(1, top_k), _MAX_TOP_K)
    query_str = f"*=>[KNN {top_k} @embedding $BLOB AS score]"
    return await _execute_vector_query(
        query_str,
        query_vector,
        query_text,
        index_name,
        top_k,
        return_fields,
        database,
    )


async def handle_redis_hybrid_search(
    query_vector: List[float] | None = None,
    query_text: str | None = None,
    filter_expression: str = "",
    index_name: str = "idx:agent_memory",
    top_k: int = 10,
    return_fields: List[str] | None = None,
    database: str = "vectors",
) -> Metadata:
    """Vector + filter combined query (Issue #2623: accepts query_text)."""
    if filter_expression and not _SAFE_FILTER_PATTERN.match(filter_expression):
        return {
            "status": "error",
            "message": "Invalid filter_expression: contains disallowed characters",
            "code": "INVALID_FILTER",
        }
    top_k = min(max(1, top_k), _MAX_TOP_K)
    pre = f"({filter_expression})" if filter_expression else "*"
    query_str = f"{pre}=>[KNN {top_k} @embedding $BLOB AS score]"
    return await _execute_vector_query(
        query_str,
        query_vector,
        query_text,
        index_name,
        top_k,
        return_fields,
        database,
        extra_meta={"filter": filter_expression} if filter_expression else None,
    )


async def handle_redis_vector_index_info(
    index_name: str = "idx:agent_memory",
    database: str = "vectors",
) -> Metadata:
    """Get index schema and stats."""
    client = await _get_client(database)
    try:
        raw = await client.execute_command("FT.INFO", index_name)
        info = _parse_ft_info(raw)
        return {"status": "success", "index_name": index_name, "info": info}
    except Exception as e:
        if "Unknown Index name" in str(e):
            return {
                "status": "error",
                "message": f"Index '{index_name}' does not exist",
                "code": "INDEX_NOT_FOUND",
            }
        raise


# ---------------------------------------------------------------------------
# Result parsers
# ---------------------------------------------------------------------------


def _parse_ft_search_results(raw) -> List[Dict[str, Any]]:
    """Parse FT.SEARCH response into a list of result dicts."""
    if not raw or not isinstance(raw, (list, tuple)):
        return []
    total = raw[0] if isinstance(raw[0], int) else int(raw[0])
    if total == 0:
        return []
    results = []
    i = 1
    while i < len(raw) - 1:
        doc_id = raw[i]
        if isinstance(doc_id, bytes):
            doc_id = doc_id.decode("utf-8")
        fields_raw = raw[i + 1]
        fields = _pairs_to_dict(fields_raw)
        fields["_id"] = doc_id
        results.append(fields)
        i += 2
    return results


def _pairs_to_dict(flat_list) -> Dict[str, Any]:
    """Convert a flat [key, value, key, value, ...] list to a dict."""
    result: Dict[str, Any] = {}
    if not flat_list:
        return result
    for idx in range(0, len(flat_list) - 1, 2):
        key = flat_list[idx]
        val = flat_list[idx + 1]
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        if isinstance(val, bytes):
            val = val.decode("utf-8")
        result[key] = val
    return result


def _parse_ft_info(raw) -> Dict[str, Any]:
    """Parse FT.INFO flat list response into a readable dict."""
    return _pairs_to_dict(raw)
