# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Cross-worker LLM provider quota headroom store (Issue #15026).

Providers return rate-limit headroom on almost every response —
``x-ratelimit-remaining-*``, ``x-ratelimit-reset-*``, ``anthropic-ratelimit-*``,
``retry-after`` — and until this module existed AutoBot never recorded any of
it: ``llm_shared/rate_limit_backoff.py`` parsed a subset of this only after a
429, only to compute one sleep duration, then discarded it.

This is the "quota monitor" ``llc/api/costs.py``'s ``/quota-windows`` route
already refers to and that did not exist (phase 3 of #15021's umbrella).

Mirrors the pattern in ``provider_degradation.py`` (#11519) and
``cross_worker_rate_limiter.py`` (#8170): Redis-backed so every uvicorn
worker sees the same observed headroom, with a graceful in-process fallback
when Redis is unavailable — a Redis outage degrades harvesting silently, it
never raises into a caller's response path.

Key shape: ``autobot:llm:headroom:{provider}:{account_id}:{window}`` →
``{utilization, limit, remaining, resets_at, observed_at, source}``

``account_id`` defaults to ``"default"`` — the current single-credential
subject — so #15029's multi-account pool can extend this without a schema
change. ``window`` is a free-form provider-defined string (``rpm``, ``tpm``,
``5h_output_tokens``, ``7d_output_tokens``, ``daily_tokens``) matching the
vocabulary already in ``llc/api/costs.py``'s ``_PROVIDER_QUOTA_STRUCTURE``.

A provider/window with no recorded entry means "no headroom signal received
yet" — distinguishable from "zero remaining", which is a real entry with
``remaining=0``. Never fabricate one to fill the gap.

Usage::

    from llm_shared.quota_headroom import get_quota_headroom_store

    store = get_quota_headroom_store()
    await store.record(
        provider="openai", window="rpm",
        limit=500, remaining=42, resets_at=time.time() + 60,
        source="x-ratelimit-remaining-requests",
    )
    entry = await store.get("openai", "rpm")
    if entry is not None and entry.remaining == 0:
        ...
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Dict, Optional

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)

# Only Redis being unreachable falls back to the in-process store — matching
# conversation_file_manager.py's convention for the same client. Any other
# exception (a programming error, a bad call) must still surface.
_REDIS_UNAVAILABLE = (RedisConnectionError, RedisTimeoutError)

# ---------------------------------------------------------------------------
# Module-level TTL constant — read from env, never hard-coded at call sites.
# ---------------------------------------------------------------------------
_HEADROOM_TTL_SECONDS: int = env_int("AUTOBOT_LLM_QUOTA_HEADROOM_TTL_SECONDS", 3600)

_KEY_PREFIX = "autobot:llm:headroom"
_DEFAULT_ACCOUNT_ID = "default"


def _make_key(provider: str, window: str, account_id: str) -> str:
    """Build the Redis key for one (provider, account_id, window) entry."""
    return f"{_KEY_PREFIX}:{provider}:{account_id}:{window}"


@dataclass(frozen=True)
class QuotaHeadroomEntry:
    """One observed headroom reading for a (provider, account_id, window)."""

    provider: str
    window: str
    account_id: str
    limit: Optional[float]
    remaining: Optional[float]
    resets_at: Optional[float]
    observed_at: float
    source: str

    @property
    def utilization(self) -> Optional[float]:
        """Fraction of quota consumed (0.0-1.0), or None when limit is unknown."""
        if self.limit is None or self.limit <= 0 or self.remaining is None:
            return None
        return max(0.0, min(1.0, 1.0 - (self.remaining / self.limit)))


def _decode_entry(raw: str, key: str) -> Optional[QuotaHeadroomEntry]:
    """Parse one stored payload, or None (logged) if it is corrupt.

    A single bad row must not take the rest of the store down with it --
    the caller skips this key and keeps going.
    """
    try:
        return QuotaHeadroomEntry(**json.loads(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("quota_headroom: corrupt entry for %s, skipping", key, exc_info=True)
        return None


class QuotaHeadroomStore:
    """
    Redis-backed provider quota headroom store shared across all uvicorn workers.

    Falls back to an in-process dict when Redis is unavailable, so a Redis
    outage silently stops harvesting rather than raising into a request path.
    """

    def __init__(self) -> None:
        self._local: Dict[str, tuple[QuotaHeadroomEntry, float]] = {}  # key -> (entry, expires_at_monotonic)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def record(
        self,
        provider: str,
        window: str,
        *,
        account_id: str = _DEFAULT_ACCOUNT_ID,
        limit: Optional[float] = None,
        remaining: Optional[float] = None,
        resets_at: Optional[float] = None,
        source: str = "",
    ) -> None:
        """Record an observed headroom reading, overwriting any prior entry for this key.

        ``limit``/``remaining``/``resets_at`` are each independently optional
        — a provider that only sends ``retry-after`` still yields a usable
        entry with ``resets_at`` set and the others ``None``.
        """
        entry = QuotaHeadroomEntry(
            provider=provider,
            window=window,
            account_id=account_id,
            limit=limit,
            remaining=remaining,
            resets_at=resets_at,
            observed_at=time.time(),
            source=source,
        )
        key = _make_key(provider, window, account_id)
        payload = json.dumps(asdict(entry), ensure_ascii=False)
        try:
            redis = await self._get_redis()
            await redis.set(key, payload, ex=_HEADROOM_TTL_SECONDS)
        except _REDIS_UNAVAILABLE:
            logger.debug("quota_headroom: Redis unavailable — using in-process fallback for %s", key, exc_info=True)
            self._local[key] = (entry, time.monotonic() + _HEADROOM_TTL_SECONDS)

    async def get(
        self, provider: str, window: str, *, account_id: str = _DEFAULT_ACCOUNT_ID
    ) -> Optional[QuotaHeadroomEntry]:
        """Return the last observed entry for (provider, account_id, window), or None.

        None means "no headroom signal ever recorded (or it expired)" — a
        first-class state, never treated as "zero remaining".
        """
        key = _make_key(provider, window, account_id)
        try:
            redis = await self._get_redis()
            raw = await redis.get(key)
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return _decode_entry(raw, key)
        except _REDIS_UNAVAILABLE:
            logger.debug("quota_headroom: Redis unavailable — checking in-process fallback for %s", key)
            cached = self._local.get(key)
            if cached is None:
                return None
            entry, expires_at = cached
            if time.monotonic() >= expires_at:
                del self._local[key]
                return None
            return entry

    async def all_entries(self, provider: Optional[str] = None) -> list[QuotaHeadroomEntry]:
        """Return every currently-recorded entry, optionally filtered to one provider."""
        prefix = f"{_KEY_PREFIX}:{provider}:" if provider else f"{_KEY_PREFIX}:"
        try:
            redis = await self._get_redis()
            entries: list[QuotaHeadroomEntry] = []
            async for raw_key in redis.scan_iter(f"{prefix}*"):
                raw_val = await redis.get(raw_key)
                if raw_val is None:
                    continue
                if isinstance(raw_val, bytes):
                    raw_val = raw_val.decode("utf-8")
                entry = _decode_entry(raw_val, raw_key)
                if entry is not None:
                    entries.append(entry)
            return entries
        except _REDIS_UNAVAILABLE:
            logger.debug("quota_headroom: Redis unavailable — listing the in-process fallback for prefix %s", prefix)
            now = time.monotonic()
            return [
                entry
                for key, (entry, expires_at) in list(self._local.items())
                if expires_at > now and key.startswith(prefix)
            ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_redis(self):
        from autobot_shared.redis_client import get_async_redis_client  # noqa: PLC0415

        return await get_async_redis_client()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

get_quota_headroom_store = lazy_singleton(QuotaHeadroomStore)

__all__ = [
    "QuotaHeadroomEntry",
    "QuotaHeadroomStore",
    "get_quota_headroom_store",
]
