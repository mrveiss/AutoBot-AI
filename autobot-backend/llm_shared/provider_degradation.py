# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Persistent cross-worker provider degradation marking (Issue #11519).

When a provider fails (rate-limit exhaustion, connection error), mark it
degraded in Redis so ALL uvicorn workers skip it during the TTL window —
mirroring the cross-worker pattern from cross_worker_rate_limiter.py (#8170).

Key naming: ``autobot:llm:deg:{provider}`` or ``autobot:llm:deg:{provider}:{model}``

TTL is read once at import time from the env var
``AUTOBOT_PROVIDER_DEGRADATION_TTL_SECONDS`` (default 300 s).  Never
hard-code the TTL inline.

Graceful fallback: when Redis is unavailable the store switches to an
in-process dict with expiry timestamps, preserving today's behavior.

Usage::

    from llm_shared.provider_degradation import get_degradation_store

    store = get_degradation_store()
    await store.mark_degraded("openai", "gpt-4o")
    if await store.is_degraded("openai", "gpt-4o"):
        ...
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional

from autobot_shared.env_utils import env_int
from autobot_shared.singleton_factory import lazy_singleton

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level TTL constant — read from env, never hard-coded in call sites.
# ---------------------------------------------------------------------------
_DEGRADATION_TTL_SECONDS: int = env_int("AUTOBOT_PROVIDER_DEGRADATION_TTL_SECONDS", 300)

_KEY_PREFIX = "autobot:llm:deg"


def _make_key(provider: str, model: Optional[str]) -> str:
    """Build a Redis key for a provider (optionally scoped to a model)."""
    if model:
        return f"{_KEY_PREFIX}:{provider}:{model}"
    return f"{_KEY_PREFIX}:{provider}"


class ProviderDegradationStore:
    """
    Redis-backed degradation store shared across all uvicorn workers.

    Falls back to an in-process dict when Redis is unavailable, ensuring
    a Redis outage never hard-blocks LLM calls.
    """

    def __init__(self) -> None:
        # {key: expires_at_monotonic} — used only when Redis is unavailable.
        self._local: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def mark_degraded(self, provider: str, model: Optional[str] = None) -> None:
        """Mark *provider* (optionally *model*) degraded for the configured TTL."""
        key = _make_key(provider, model)
        try:
            redis = await self._get_redis()
            await redis.set(key, "1", ex=_DEGRADATION_TTL_SECONDS)
            logger.info(
                "degradation: marked %r degraded (TTL=%ds key=%s)",
                provider if not model else f"{provider}:{model}",
                _DEGRADATION_TTL_SECONDS,
                key,
            )
        except Exception:
            logger.debug(
                "degradation: Redis unavailable — using in-process fallback for %s",
                key,
                exc_info=True,
            )
            self._local[key] = time.monotonic() + _DEGRADATION_TTL_SECONDS

    async def is_degraded(self, provider: str, model: Optional[str] = None) -> bool:
        """Return True if *provider* (or *provider*:*model*) is currently degraded."""
        key = _make_key(provider, model)
        try:
            redis = await self._get_redis()
            result = await redis.exists(key)
            return bool(result)
        except Exception:
            logger.debug("degradation: Redis unavailable — checking in-process fallback")
            expires_at = self._local.get(key)
            if expires_at is None:
                return False
            if time.monotonic() < expires_at:
                return True
            # Expired — clean up.
            del self._local[key]
            return False

    async def degraded_entries(self) -> list[str]:
        """Return the list of currently-degraded keys (for observability)."""
        try:
            redis = await self._get_redis()
            # SCAN is O(N) but safe because the keyspace is tiny.
            keys: list[bytes | str] = []
            async for key in redis.scan_iter(f"{_KEY_PREFIX}:*"):
                keys.append(key)
            return [k.decode() if isinstance(k, bytes) else k for k in keys]
        except Exception:
            now = time.monotonic()
            return [k for k, exp in list(self._local.items()) if exp > now]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_redis(self):
        from autobot_shared.redis_client import get_async_redis_client  # noqa: PLC0415

        return await get_async_redis_client()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

get_degradation_store = lazy_singleton(ProviderDegradationStore)

__all__ = [
    "ProviderDegradationStore",
    "get_degradation_store",
]
