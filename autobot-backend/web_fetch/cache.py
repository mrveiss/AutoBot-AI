# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
web_fetch.cache — Content-hash deduplication cache backed by Redis.

Issue #7400: Foundation package for unified web search/scrape/crawl.

TTL is controlled by AUTOBOT_WEB_FETCH_CACHE_TTL env var (default 86400s = 24h).
Uses the canonical resolver pattern from chat_history/cache.py (#6743).
"""

from __future__ import annotations

import hashlib
import json

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.ttl_constants import TTL_24_HOURS

logger = get_logger(__name__)


def _resolve_web_fetch_cache_ttl() -> int:
    """Return TTL seconds for web_fetch content cache Redis keys.

    Override via AUTOBOT_WEB_FETCH_CACHE_TTL.  Falls back to 24h (86400s).
    """
    raw = config.misc.web_fetch_cache_ttl
    if raw is None:
        return TTL_24_HOURS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_WEB_FETCH_CACHE_TTL=%r is not an integer; falling back to %ds (24h)",
            raw,
            TTL_24_HOURS,
        )
        return TTL_24_HOURS
    if value <= 0:
        logger.warning(
            "AUTOBOT_WEB_FETCH_CACHE_TTL=%d must be positive; falling back to %ds (24h)",
            value,
            TTL_24_HOURS,
        )
        return TTL_24_HOURS
    return value


_WEB_FETCH_CACHE_TTL: int = _resolve_web_fetch_cache_ttl()

_MAX_BYTES_ENV = "AUTOBOT_WEB_FETCH_MAX_BYTES"
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _resolve_max_bytes() -> int:
    """Return max content size in bytes from env var (default 10 MB)."""
    raw = config.misc.web_fetch_max_bytes
    return raw if raw else _DEFAULT_MAX_BYTES


WEB_FETCH_MAX_BYTES: int = _resolve_max_bytes()


def _content_cache_key(url: str, render_mode: str) -> str:
    """Build Redis cache key: sha256(url + render_mode)."""
    raw = f"{url}|{render_mode}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"web_fetch:content:{digest}"


async def get_cached_result(url: str, render_mode: str, redis_client) -> dict | None:
    """Return cached FetchResult payload dict or None on cache miss.

    Args:
        url: The URL to look up.
        render_mode: Render mode string (e.g. ``"auto"``).
        redis_client: Async Redis client from get_async_redis_client().
    """
    if redis_client is None:
        return None
    key = _content_cache_key(url, render_mode)
    try:
        raw = await redis_client.get(key)
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except Exception as exc:
        logger.warning("web_fetch cache get failed for %s: %s", url, exc)
        return None


async def set_cached_result(url: str, render_mode: str, payload: dict, redis_client) -> None:
    """Store FetchResult payload dict in Redis with configured TTL.

    Args:
        url: The URL that was fetched.
        render_mode: Render mode string.
        payload: Serialisable dict (FetchResult fields).
        redis_client: Async Redis client from get_async_redis_client().
    """
    if redis_client is None:
        return
    key = _content_cache_key(url, render_mode)
    try:
        serialized = json.dumps(payload, ensure_ascii=False)
        await redis_client.setex(key, _WEB_FETCH_CACHE_TTL, serialized)
    except Exception as exc:
        logger.warning("web_fetch cache set failed for %s: %s", url, exc)
