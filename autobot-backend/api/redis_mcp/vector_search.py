# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Vector Search tool handlers for Redis MCP Bridge (4 tools).

Issue #2511: RediSearch vector index creation, similarity search,
hybrid search, and index info — using Redis Stack 7.4.0 FT.* commands.
"""

import logging
import struct
from typing import Any, Dict, List, Optional

from type_defs.common import Metadata

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


async def _get_client(database: str = "vectors"):
    """Get an async Redis client for vector operations."""
    return await get_redis_client(async_client=True, database=database)


def _float_list_to_bytes(vector: List[float]) -> bytes:
    """Pack a list of floats into a binary blob for RediSearch KNN queries."""
    return struct.pack(f"{len(vector)}f", *vector)


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


async def handle_redis_vector_create_index(
    index_name: str = "idx:agent_memory",
    prefix: str = "autobot:agent:memory:",
    vector_field: str = "embedding",
    dimensions: int = 1536,
    distance_metric: str = "COSINE",
    extra_fields: Optional[List[Dict[str, str]]] = None,
    database: str = "vectors",
) -> Metadata:
    """Create a RediSearch vector index using HNSW."""
    client = await _get_client(database)

    # Build the FT.CREATE command arguments
    schema_args: List[Any] = []

    # Add extra fields first (TEXT, TAG, NUMERIC)
    if extra_fields:
        for field in extra_fields:
            schema_args.extend([field["name"], field["type"]])

    # Add the vector field last
    schema_args.extend(
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
        error_msg = str(e)
        if "Index already exists" in error_msg:
            return {
                "status": "success",
                "index_name": index_name,
                "message": "Index already exists",
            }
        raise


async def handle_redis_vector_search(
    query_vector: List[float],
    index_name: str = "idx:agent_memory",
    top_k: int = 10,
    return_fields: Optional[List[str]] = None,
    database: str = "vectors",
) -> Metadata:
    """Similarity search by embedding vector."""
    client = await _get_client(database)
    blob = _float_list_to_bytes(query_vector)

    query_str = f"*=>[KNN {top_k} @embedding $BLOB AS score]"
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
    return {
        "status": "success",
        "index_name": index_name,
        "results": results,
        "count": len(results),
    }


async def handle_redis_hybrid_search(
    query_vector: List[float],
    filter_expression: str,
    index_name: str = "idx:agent_memory",
    top_k: int = 10,
    return_fields: Optional[List[str]] = None,
    database: str = "vectors",
) -> Metadata:
    """Vector + filter combined query."""
    client = await _get_client(database)
    blob = _float_list_to_bytes(query_vector)

    query_str = f"({filter_expression})=>[KNN {top_k} @embedding $BLOB AS score]"
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
    return {
        "status": "success",
        "index_name": index_name,
        "filter": filter_expression,
        "results": results,
        "count": len(results),
    }


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
