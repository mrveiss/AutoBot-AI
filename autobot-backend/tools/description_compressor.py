# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tool description compressor.

Compresses tool descriptions via Ollama to reduce per-call LLM token spend.
Compressed descriptions are cached in Redis with a 30-day TTL so the
compression LLM call is paid once per unique tool spec.
"""

import hashlib
import json

import aiohttp

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientLockedMixin
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

CACHE_TTL = 2592000  # 30 days


class _RedisHelper(AsyncRedisClientLockedMixin):
    _redis_database = "main"


_get_redis_helper = lazy_singleton(_RedisHelper)


def _cache_key(tool_name: str, tool_spec: dict) -> str:
    """Return a stable Redis cache key for the given tool spec."""
    spec_json = json.dumps(tool_spec, sort_keys=True, ensure_ascii=False)
    spec_hash = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()[:16]
    return f"tool_desc:{tool_name}:{spec_hash}"


def _fallback_description(tool_spec: dict) -> str:
    """Extract the raw description from a tool spec dict."""
    return (
        tool_spec.get("description")
        or tool_spec.get("function", {}).get("description")
        or json.dumps(tool_spec, ensure_ascii=False)
    )


async def _fetch_from_cache(key: str) -> str | None:
    """Return cached compressed description or None on cache miss / Redis unavailable."""
    redis = await _get_redis_helper()._get_redis()
    if redis is None:
        return None
    try:
        value = await redis.get(key)
        return value.decode("utf-8") if isinstance(value, bytes) else value
    except Exception:
        logger.warning("Redis get failed for key %s", key)
        return None


async def _store_in_cache(key: str, value: str) -> None:
    """Persist compressed description to Redis; silently skips on failure."""
    redis = await _get_redis_helper()._get_redis()
    if redis is None:
        return
    try:
        await redis.set(key, value.encode("utf-8"), ex=CACHE_TTL)
    except Exception:
        logger.warning("Redis set failed for key %s", key)


async def _compress_via_ollama(description: str) -> str | None:
    """Call Ollama to compress *description*; returns compressed text or None on error."""
    prompt = (
        "Compress this tool description to under 50 words while preserving "
        f"all parameter names and types:\n{description}"
    )
    model = config.llm.system_model
    url = f"{config.ollama_url}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(connect=5, total=30)) as resp:
                if resp.status != 200:
                    logger.warning("Ollama returned HTTP %d for compression request", resp.status)
                    return None
                data = await resp.json(content_type=None)
                return (data.get("response") or "").strip() or None
    except Exception as exc:
        logger.warning("Ollama compression call failed: %s", exc)
        return None


async def compress_description(tool_name: str, tool_spec: dict) -> str:
    """Return a compressed description for *tool_spec*, using Redis cache.

    Falls back to the original description string if Ollama or Redis is
    unavailable, so callers always receive a valid non-empty string.
    """
    fallback = _fallback_description(tool_spec)
    key = _cache_key(tool_name, tool_spec)

    cached = await _fetch_from_cache(key)
    if cached:
        return cached

    compressed = await _compress_via_ollama(fallback)
    if not compressed:
        return fallback

    await _store_in_cache(key, compressed)
    return compressed
