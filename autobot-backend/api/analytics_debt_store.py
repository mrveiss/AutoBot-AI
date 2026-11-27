# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Source-scoped storage and inputs for the technical-debt calculator (#22198).

Every Redis key and every input read here belongs to ONE code source. The prefix comes
from ``source_scoped_prefix`` (it raises on a missing or malformed source id), so the
global ``debt:latest`` / ``debt:calculation:*`` shape cannot be built, and one source's
calculation can never be returned for another. Keys written before #22198 under the
global ``debt:`` prefix are never read.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from api.source_scope import source_scoped_prefix
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.redis_utils import decode_redis_value as _decode_redis_value
from constants.ttl_constants import TTL_30_DAYS

logger = get_logger(__name__)

# Redis key prefix; always followed by a source id (see debt_prefix)
DEBT_PREFIX = "debt:"
# Anti-pattern results are read per source as well
ANTIPATTERN_PREFIX = "antipattern:"


def get_debt_redis():
    """Get Redis client for debt data storage"""
    return get_redis_client(database="analytics")


def debt_prefix(source_id: str) -> str:
    """``debt:source_id:{source_id}:`` -- the namespace of ONE source's debt keys."""
    return source_scoped_prefix(DEBT_PREFIX, source_id)


def _extract_problem_from_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Extract problem data from metadata (Issue #315 - extracted helper)."""
    return {
        "type": meta.get("problem_type", "unknown"),
        "severity": meta.get("severity", "medium"),
        "file_path": meta.get("file_path", "unknown"),
        "line_number": (int(meta.get("line_number", 0)) if meta.get("line_number") else None),
        "description": meta.get("description", ""),
        "suggestion": meta.get("suggestion", ""),
    }


def get_problems_from_chromadb(code_collection, source_id: str) -> List[Dict[str, Any]]:
    """Get ONE source's problems from the ChromaDB collection (Issue #315, #22198)."""
    if not code_collection:
        return []
    try:
        where = {"$and": [{"type": "problem"}, {"source_id": source_id}]}
        problems_result = code_collection.get(where=where, include=["metadatas"])
        if not problems_result.get("metadatas"):
            return []
        return [_extract_problem_from_meta(meta) for meta in problems_result["metadatas"]]
    except Exception as e:
        logger.warning("ChromaDB query failed: %s", e)
        return []


async def get_antipatterns_from_redis(redis_client, source_id: str) -> List[Dict[str, Any]]:
    """Get ONE source's anti-patterns from Redis (Issue #315, #22198)."""
    if not redis_client:
        return []
    try:
        key = f"{source_scoped_prefix(ANTIPATTERN_PREFIX, source_id)}latest_results"
        # Issue #361 - avoid blocking
        ap_data = await asyncio.to_thread(redis_client.get, key)
        if not ap_data:
            return []
        if isinstance(ap_data, bytes):
            ap_data = ap_data.decode("utf-8")
        return json.loads(ap_data).get("anti_patterns", [])
    except Exception as e:
        logger.warning("Redis anti-pattern fetch failed: %s", e)
        return []


def store_debt_result(debt_result: Dict[str, Any], source_id: str) -> None:
    """Store a source's debt calculation and move that source's latest pointer."""
    debt_redis = get_debt_redis()
    if not debt_redis:
        return
    try:
        prefix = debt_prefix(source_id)
        key = f"{prefix}calculation:{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        debt_redis.set(key, json.dumps(debt_result), ex=TTL_30_DAYS)
        debt_redis.set(f"{prefix}latest", key)
    except Exception as e:
        logger.warning("Failed to store debt calculation: %s", e)


def get_latest_debt_data(source_id: str) -> Dict[str, Any] | None:
    """Get ONE source's latest debt data from Redis (Issue #315 - extracted helper)."""
    redis_client = get_debt_redis()
    if not redis_client:
        return None
    try:
        latest_key = _decode_redis_value(redis_client.get(f"{debt_prefix(source_id)}latest"))
        if not latest_key:
            return None
        debt_data = _decode_redis_value(redis_client.get(latest_key))
        if not debt_data:
            return None
        return json.loads(debt_data)
    except Exception as e:
        logger.warning("Redis fetch failed: %s", e)
        return None


def _trend_point(calc: Dict[str, Any]) -> Dict[str, Any]:
    """One trend point from a stored calculation."""
    summary = calc.get("summary", {})
    return {
        "timestamp": calc.get("timestamp"),
        "total_items": summary.get("total_items", 0),
        "total_hours": summary.get("total_hours", 0),
        "total_cost_usd": summary.get("total_cost_usd", 0),
    }


def get_debt_trend_data(source_id: str) -> List[Dict[str, Any]]:
    """Get ONE source's historical debt trend data from Redis.

    Issue #315: Extracted helper.
    Issue #561: Fixed N+1 query pattern - now uses pipeline batching.
    """
    redis_client = get_debt_redis()
    if not redis_client:
        return []
    try:
        pattern = f"{debt_prefix(source_id)}calculation:*"
        keys = [_decode_redis_value(key) for key in redis_client.scan_iter(match=pattern)]
        if not keys:
            return []
        pipe = redis_client.pipeline()
        for key_str in keys:
            pipe.get(key_str)
        return [_trend_point(json.loads(_decode_redis_value(data))) for data in pipe.execute() if data]
    except Exception as e:
        logger.warning("Redis trend fetch failed: %s", e)
        return []
