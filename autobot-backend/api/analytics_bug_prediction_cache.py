# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis cache of one source's bug-prediction result (#1341, #18030).

Extracted from ``analytics_bug_prediction`` so that module does not grow when its cache key gains
the source it belongs to.
"""

from __future__ import annotations

import hashlib
import json

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from constants.ttl_constants import TTL_5_MINUTES

logger = get_logger(__name__)

# Issue #1341: Cache configuration for bug prediction
BUG_PREDICTION_CACHE_PREFIX = "codebase:bug_prediction:cache"
BUG_PREDICTION_CACHE_TTL = TTL_5_MINUTES


def cache_key_for(source_id: str, include_pattern: str, limit: int) -> str:
    """
    Generate parameter-specific cache key for bug prediction.

    Issue #1341: Include path, pattern, and limit in cache key
    to prevent stale data across different query parameters.
    """
    raw = f"{source_id}:{include_pattern}:{limit}"
    param_hash = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"{BUG_PREDICTION_CACHE_PREFIX}:{param_hash}"


async def get_cached_prediction(source_id: str, include_pattern: str, limit: int) -> dict | None:
    """
    Get cached bug prediction from Redis.

    Issue #1341: Cache for 5 minutes to prevent re-running
    expensive git subprocesses and complexity analysis.
    """
    try:
        cache_key = cache_key_for(source_id, include_pattern, limit)
        redis_client = get_redis_client(async_client=False, database="cache")
        cached = redis_client.get(cache_key)
        if cached:
            logger.debug("Bug prediction cache hit for source: %s", source_id)
            return json.loads(cached)
    except Exception as e:
        logger.debug("Cache read error (non-critical): %s", e)
    return None


async def set_cached_prediction(
    source_id: str,
    include_pattern: str,
    limit: int,
    data: dict,
) -> None:
    """
    Cache bug prediction results in Redis.

    Issue #1341: Cache for 5 minutes (300 seconds).
    """
    try:
        cache_key = cache_key_for(source_id, include_pattern, limit)
        redis_client = get_redis_client(async_client=False, database="cache")
        redis_client.setex(
            cache_key,
            BUG_PREDICTION_CACHE_TTL,
            json.dumps(data, default=str),
        )
        logger.debug(
            "Bug prediction cached for %d seconds (source: %s)",
            BUG_PREDICTION_CACHE_TTL,
            source_id,
        )
    except Exception as e:
        logger.debug("Cache write error (non-critical): %s", e)
