# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""In-process read cache for :class:`services.feature_flags.FeatureFlags` (#18998).

The enforcement posture is read on every chat/session request, and each read was
an awaited Redis GET. A write made in THIS process invalidates the entry at once;
a write from another process is seen within ``AUTOBOT_FEATURE_FLAG_CACHE_TTL_SECONDS``
(default 5, 0 disables). THREAT_MODEL section 2 requires that an undetermined
posture never degrades to ``disabled``; it sets no latency bound on a deliberate
change, so a bounded window is allowed. Only successful reads are stored, so a
Redis failure still raises/degrades instead of being remembered.
"""

import time

from autobot_shared.env_utils import env_float_clamped

FEATURE_FLAG_CACHE_TTL_SECONDS = env_float_clamped("AUTOBOT_FEATURE_FLAG_CACHE_TTL_SECONDS", 5.0, 0.0, 60.0)

# Per-endpoint keys come from route patterns, but the fallback is the raw request
# path, so the number of remembered keys is capped.
MAX_CACHED_KEYS = 1024
ENDPOINT_KEY_PREFIX = "feature_flag:access_control:endpoint:"


def _monotonic() -> float:
    """Clock for cache ageing; a seam so tests advance time without sleeping."""
    return time.monotonic()


class FeatureFlagCacheMixin:
    """TTL cache over ``self._cache`` / ``self._last_refresh`` / ``self._cache_ttl``."""

    _cache: dict
    _last_refresh: dict
    _cache_ttl: float

    def _cache_state(self) -> tuple[dict, dict, float]:
        """The cache dicts and TTL, created on first use so a bare instance (``__new__``) works too."""
        state = self.__dict__
        return (
            state.setdefault("_cache", {}),
            state.setdefault("_last_refresh", {}),
            state.setdefault("_cache_ttl", FEATURE_FLAG_CACHE_TTL_SECONDS),
        )

    def _cache_lookup(self, key: str) -> tuple[bool, object]:
        """``(True, value)`` while *key* was read within ``_cache_ttl``, else ``(False, None)``."""
        cache, stamps, ttl = self._cache_state()
        stamp = stamps.get(key)
        if stamp is not None and (_monotonic() - stamp) < ttl:
            return True, cache.get(key)
        return False, None

    def _cache_store(self, key: str, value: object) -> None:
        """Remember a SUCCESSFUL read; a failed read is never stored."""
        cache, stamps, ttl = self._cache_state()
        if key not in cache and len(cache) >= MAX_CACHED_KEYS:
            self._prune_expired(cache, stamps, ttl)
            if len(cache) >= MAX_CACHED_KEYS:
                # Still full of live entries: refuse the new key. Evicting the oldest would let
                # a flood of distinct request paths churn out the hot enforcement-mode key.
                return
        cache[key] = value
        stamps[key] = _monotonic()

    @staticmethod
    def _prune_expired(cache: dict, stamps: dict, ttl: float) -> None:
        """Drop entries older than *ttl*; an expired stamp never serves a read, so it only costs a slot."""
        now = _monotonic()
        for stale in [k for k, stamp in stamps.items() if (now - stamp) >= ttl]:
            cache.pop(stale, None)
            stamps.pop(stale, None)

    def _cache_invalidate(self, key: str | None = None) -> None:
        """Drop one key, or everything, so the next read goes to Redis."""
        cache, stamps, _ = self._cache_state()
        if key is None:
            cache.clear()
            stamps.clear()
            return
        cache.pop(key, None)
        stamps.pop(key, None)
