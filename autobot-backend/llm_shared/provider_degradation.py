# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Persistent cross-worker provider degradation marking (Issue #11519, #15022).

When a provider fails (rate-limit exhaustion, connection error), mark it
degraded in Redis so ALL uvicorn workers skip it during the TTL window —
mirroring the cross-worker pattern from cross_worker_rate_limiter.py (#8170).

Key naming: ``autobot:llm:deg:{provider}`` or ``autobot:llm:deg:{provider}:{model}``

TTL is read once at import time from the env var
``AUTOBOT_PROVIDER_DEGRADATION_TTL_SECONDS`` (default 300 s).  Never
hard-code the TTL inline.

Cause (#15022)
---------------
A mark carries a :class:`DegradationCause`:

- ``TRANSIENT`` (default) — today's exact behaviour, unchanged: expires
  after the TTL and is retried automatically.
- ``NEEDS_REAUTH`` — a credential is known-dead (``TokenExpiredError`` from
  an auth strategy in ``provider_auth.py``), not merely slow or unlucky.
  This mark is **non-expiring**: retrying a dead credential every TTL wastes
  a round-trip forever and tells no one. It is cleared only explicitly, via
  :meth:`ProviderDegradationStore.clear`, by a successful subsequent auth.

``is_degraded()`` keeps its existing signature and semantics for existing
callers (still just "is this key currently marked") — the cause is additive
and does not change what counts as degraded.

Graceful fallback: when Redis is unavailable the store switches to an
in-process dict with expiry timestamps, preserving today's behavior.

Usage::

    from llm_shared.provider_degradation import DegradationCause, get_degradation_store

    store = get_degradation_store()
    await store.mark_degraded("openai", "gpt-4o")
    if await store.is_degraded("openai", "gpt-4o"):
        ...

    # A dead credential — non-expiring until an explicit clear():
    await store.mark_degraded("openai", cause=DegradationCause.NEEDS_REAUTH)
    await store.clear("openai")
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Dict, Optional, Tuple

from autobot_shared.alert_cooldown import AlertCooldownManager, AlertTier
from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level TTL constant — read from env, never hard-coded in call sites.
# ---------------------------------------------------------------------------
_DEGRADATION_TTL_SECONDS: int = env_int("AUTOBOT_PROVIDER_DEGRADATION_TTL_SECONDS", 300)

_KEY_PREFIX = "autobot:llm:deg"

# Alert tier for a needs_reauth transition (#15022, #1948). PRIORITY: a dead
# credential degrades the provider (other providers/models still serve
# traffic) rather than causing an outage, so it is a warning, not FLASH.
_NEEDS_REAUTH_ALERT_TIER = AlertTier.PRIORITY

_get_alert_cooldown = lazy_singleton(AlertCooldownManager)


class DegradationCause(str, Enum):
    """Why a provider/model entry is marked degraded (#15022)."""

    TRANSIENT = "transient"
    NEEDS_REAUTH = "needs_reauth"


# {key: (cause, expires_at_monotonic)} — used only when Redis is unavailable.
# ``expires_at`` of None means "does not expire on its own" (NEEDS_REAUTH).
_LocalEntry = Tuple[DegradationCause, Optional[float]]


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
        self._local: Dict[str, _LocalEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def mark_degraded(
        self,
        provider: str,
        model: Optional[str] = None,
        *,
        cause: DegradationCause = DegradationCause.TRANSIENT,
    ) -> None:
        """Mark *provider* (optionally *model*) degraded.

        ``cause=TRANSIENT`` (default) expires after the configured TTL and
        is retried — today's exact behaviour, unchanged. ``cause=NEEDS_REAUTH``
        never expires on its own; only :meth:`clear` removes it (#15022).
        """
        key = _make_key(provider, model)
        ttl = None if cause is DegradationCause.NEEDS_REAUTH else _DEGRADATION_TTL_SECONDS
        try:
            redis = await self._get_redis()
            await redis.set(key, cause.value, ex=ttl)
            logger.info(
                "degradation: marked %r degraded (cause=%s ttl=%s key=%s)",
                provider if not model else f"{provider}:{model}",
                cause.value,
                ttl,
                key,
            )
        except Exception:
            logger.debug(
                "degradation: Redis unavailable — using in-process fallback for %s",
                key,
                exc_info=True,
            )
            expires_at = None if cause is DegradationCause.NEEDS_REAUTH else time.monotonic() + _DEGRADATION_TTL_SECONDS
            self._local[key] = (cause, expires_at)

        if cause is DegradationCause.NEEDS_REAUTH:
            self._alert_needs_reauth(provider, model)

    async def is_degraded(self, provider: str, model: Optional[str] = None) -> bool:
        """Return True if *provider* (or *provider*:*model*) is currently degraded."""
        key = _make_key(provider, model)
        try:
            redis = await self._get_redis()
            result = await redis.exists(key)
            return bool(result)
        except Exception:
            logger.debug("degradation: Redis unavailable — checking in-process fallback")
            entry = self._local.get(key)
            if entry is None:
                return False
            _cause, expires_at = entry
            if expires_at is None or time.monotonic() < expires_at:
                return True
            # Expired — clean up.
            del self._local[key]
            return False

    async def clear(self, provider: str, model: Optional[str] = None) -> None:
        """Explicitly remove a degradation mark (#15022).

        A ``NEEDS_REAUTH`` mark does not expire on its own — this is its
        only exit besides an operator action. Safe to call on a key that
        was never marked (no-op).
        """
        key = _make_key(provider, model)
        try:
            redis = await self._get_redis()
            await redis.delete(key)
        except Exception:
            logger.debug("degradation: Redis unavailable — clearing in-process fallback for %s", key, exc_info=True)
        self._local.pop(key, None)

    async def degraded_entries(self) -> list[dict[str, str]]:
        """Return currently-degraded entries with their cause (for observability).

        Each entry is ``{"key": ..., "cause": ...}`` — the cause lets the
        observability path show *why* a provider is degraded (#15022).
        """
        try:
            redis = await self._get_redis()
            # SCAN is O(N) but safe because the keyspace is tiny.
            entries: list[dict[str, str]] = []
            async for raw_key in redis.scan_iter(f"{_KEY_PREFIX}:*"):
                key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
                raw_cause = await redis.get(key)
                if isinstance(raw_cause, bytes):
                    raw_cause = raw_cause.decode()
                entries.append({"key": key, "cause": raw_cause or DegradationCause.TRANSIENT.value})
            return entries
        except Exception:
            now = time.monotonic()
            return [
                {"key": k, "cause": cause.value}
                for k, (cause, expires_at) in list(self._local.items())
                if expires_at is None or expires_at > now
            ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_redis(self):
        from autobot_shared.redis_client import get_async_redis_client  # noqa: PLC0415

        return await get_async_redis_client()

    def _alert_needs_reauth(self, provider: str, model: Optional[str]) -> None:
        """Emit an operator alert for a needs_reauth transition (#15022, #1948).

        Dedup and rate limiting are owned entirely by ``AlertCooldownManager``
        (progressive per-fingerprint cooldown, #1948) — this keeps no
        separate de-dup state of its own, so "exactly one alert per
        cooldown tier" is enforced there, not here.
        """
        target = provider if not model else f"{provider}:{model}"
        message = f"LLM provider credential needs re-auth: {target}"
        try:
            cooldown = _get_alert_cooldown()
            if cooldown.should_send(message, _NEEDS_REAUTH_ALERT_TIER):
                logger.warning("degradation: %s", message)
                cooldown.record_sent(message, _NEEDS_REAUTH_ALERT_TIER)
        except Exception:
            logger.debug("degradation: alert_cooldown unavailable for %s", target, exc_info=True)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

get_degradation_store = lazy_singleton(ProviderDegradationStore)

__all__ = [
    "DegradationCause",
    "ProviderDegradationStore",
    "get_degradation_store",
]
