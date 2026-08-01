# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared Redis helpers for the memory subsystem — Issue #12694.

``decode`` and ``redis_scan`` were duplicated verbatim across
``memory.transparency`` and ``memory.ownership_reassign``; both now import
from here instead of carrying their own copy.
"""

import logging
from typing import Any, List

logger = logging.getLogger(__name__)


def decode(v: Any) -> str:
    """Decode a Redis reply to ``str``, passing through non-bytes values."""
    return v.decode("utf-8") if isinstance(v, bytes) else str(v)


async def redis_scan(redis: Any, match: str) -> List[str]:
    """Non-blocking SCAN helper — collects every key matching *match*."""
    keys: List[str] = []
    cursor = 0
    while True:
        try:
            cursor, batch = await redis.scan(cursor, match=match, count=200)
        except Exception as exc:
            logger.warning("memory._redis_util: redis scan error: %s", exc)
            break
        for k in batch:
            keys.append(decode(k))
        if cursor == 0:
            break
    return keys


__all__ = ["decode", "redis_scan"]
