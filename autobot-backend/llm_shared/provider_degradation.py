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

Selection (#15022): ``needs_reauth(provider, model)`` is the credential-scoped
question the registry asks. A provider-level ``NEEDS_REAUTH`` mark implies every
model of that provider (one credential authenticates them all); a provider-level
TRANSIENT mark still does not. When every candidate is dead the registry raises
:class:`AllCredentialsNeedReauthError` rather than returning ``None``.

``is_degraded()`` keeps its existing signature and semantics for existing
callers (still just "is this key currently marked") — the cause is additive
and does not change what counts as degraded.

Graceful fallback: when Redis is unavailable the store switches to an
in-process dict with expiry timestamps, preserving today's behavior.
``needs_reauth`` survives the outage both ways: it is mirrored locally while
Redis is up, and a mark or clear made during the outage is replayed into Redis
when it returns (otherwise a dead credential would silently re-enter the pool,
or a revived one stay parked, with no TTL to heal either).

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

import hashlib
import time
from enum import Enum
from typing import Dict, Optional, Tuple

from autobot_shared.alert_cooldown import AlertCooldownManager, AlertTier
from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

from .provider_auth import ProviderAuthError

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


class AllCredentialsNeedReauthError(ProviderAuthError):
    """Every selectable candidate holds a known-dead credential (#15022).

    Raised by ``ProviderRegistry.get_provider_for_request`` instead of a bare
    ``None`` so a caller can tell "all credentials need re-auth" (an operator
    action) from "no capacity" (wait or fall back). ``providers`` names the
    candidates, so a caller can show the operator which credentials to renew.
    """

    def __init__(self, providers: list[str]) -> None:
        self.providers = list(providers)
        super().__init__("all credentials need re-auth: " + ", ".join(self.providers))


def _parse_cause(raw) -> Optional[DegradationCause]:
    """Decode a stored value; ``None`` means unmarked, unknown values read as transient."""
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        return DegradationCause(raw.split("@", 1)[0])  # "needs_reauth@<mark id>" carries an id
    except ValueError:
        return DegradationCause.TRANSIENT


class ProviderDegradationStore:
    """
    Redis-backed degradation store shared across all uvicorn workers.

    Falls back to an in-process dict when Redis is unavailable, ensuring
    a Redis outage never hard-blocks LLM calls. ``needs_reauth`` survives
    the outage in both directions (#15022 AC7): a mark is mirrored locally
    while Redis is up, and a mark/clear made while it is down is replayed
    into Redis once it returns.
    """

    def __init__(self) -> None:
        self._local: Dict[str, _LocalEntry] = {}
        # Keys whose needs_reauth mark / clear never reached Redis.
        self._pending_reauth: set[str] = set()
        # key -> the mark value the clearing worker saw; replay deletes only that exact mark.
        self._pending_clear: Dict[str, Optional[str]] = {}
        self._seen: Dict[str, str] = {}  # key -> value of the last needs_reauth mark this worker wrote/read

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def mark_degraded(
        self,
        provider: str,
        model: Optional[str] = None,
        *,
        cause: DegradationCause = DegradationCause.TRANSIENT,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Mark *provider* (optionally *model*) degraded.

        ``cause=TRANSIENT`` (default) expires after the configured TTL and
        is retried — today's exact behaviour, unchanged. ``cause=NEEDS_REAUTH``
        never expires on its own; only :meth:`clear` removes it (#15022).
        ``ttl_seconds`` replaces the transient window for a quota hold that lasts
        until the provider's reset (#19753); it never applies to ``NEEDS_REAUTH``.
        """
        key = _make_key(provider, model)
        reauth = cause is DegradationCause.NEEDS_REAUTH
        ttl = None if reauth else (ttl_seconds or _DEGRADATION_TTL_SECONDS)
        value = f"{cause.value}@{time.time_ns()}" if reauth else cause.value  # id: see _delete_if_equal
        if reauth:
            self._seen[key] = value
        try:
            redis = await self._get_redis()
            await redis.set(key, value, ex=ttl)
            logger.info("degradation: marked %r degraded (cause=%s ttl=%s key=%s)", key, cause.value, ttl, key)
            confirmed = True
        except Exception:
            logger.debug("degradation: Redis unavailable — using in-process fallback for %s", key, exc_info=True)
            confirmed = False
        self._remember(key, cause, redis_confirmed=confirmed, ttl=ttl)

        if reauth:
            self._alert_needs_reauth(provider, model)

    async def is_degraded(self, provider: str, model: Optional[str] = None) -> bool:
        """Return True if *provider* (or *provider*:*model*) is currently degraded."""
        return await self._cause_of(_make_key(provider, model)) is not None

    async def needs_reauth(self, provider: str, model: Optional[str] = None) -> bool:
        """Return True if the credential behind *provider* (or *provider*:*model*) is dead.

        Unlike :meth:`is_degraded` this is credential-scoped: one credential
        authenticates every model of its provider, so a provider-level
        ``NEEDS_REAUTH`` mark implies all of that provider's models. A
        provider-level TRANSIENT mark still does not (the #11519 invariant).
        """
        keys = [_make_key(provider, None)]
        if model:
            keys.append(_make_key(provider, model))
        for key in keys:
            if await self._cause_of(key) is DegradationCause.NEEDS_REAUTH:
                return True
        return False

    async def clear(self, provider: str, model: Optional[str] = None) -> None:
        """Explicitly remove a degradation mark (#15022).

        A ``NEEDS_REAUTH`` mark does not expire on its own — this is its
        only exit besides an operator action. Safe to call on a key that
        was never marked (no-op). If Redis is down the clear is replayed
        when it returns, so a revived credential does not stay parked.
        """
        key = _make_key(provider, model)
        self._local.pop(key, None)
        self._pending_reauth.discard(key)
        seen = self._seen.pop(key, None)
        try:
            redis = await self._get_redis()
            await redis.delete(key)
            self._pending_clear.pop(key, None)
        except Exception:
            logger.debug("degradation: Redis unavailable — clear of %s deferred", key, exc_info=True)
            self._pending_clear[key] = seen

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
                cause = _parse_cause(await redis.get(key)) or DegradationCause.TRANSIENT
                entries.append({"key": key, "cause": cause.value})
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

    def _remember(self, key: str, cause: DegradationCause, *, redis_confirmed: bool, ttl: Optional[int]) -> None:
        """Keep the in-process copy of a mark: the outage answer, and the replay source if Redis missed it."""
        reauth = cause is DegradationCause.NEEDS_REAUTH
        if redis_confirmed and not reauth:
            return  # a confirmed transient mark needs no local copy
        self._local[key] = (cause, None if reauth else time.monotonic() + (ttl or _DEGRADATION_TTL_SECONDS))
        if reauth:
            self._pending_clear.pop(key, None)
            if not redis_confirmed:
                self._pending_reauth.add(key)

    async def _cause_of(self, key: str) -> Optional[DegradationCause]:
        """Current cause for *key* (``None`` = unmarked): Redis first, local dict if it is down."""
        try:
            redis = await self._get_redis()
            await self._flush_pending(redis)
            raw = await redis.get(key)
            raw = raw.decode() if isinstance(raw, bytes) else raw
            cause = _parse_cause(raw)
            if cause is DegradationCause.NEEDS_REAUTH and key not in self._pending_clear:
                self._seen[key] = raw
            self._mirror(key, cause)
            return cause
        except Exception:
            logger.debug("degradation: Redis unavailable — checking in-process fallback")
            return self._local_cause(key)

    def _local_cause(self, key: str) -> Optional[DegradationCause]:
        entry = self._local.get(key)
        if entry is None:
            return None
        cause, expires_at = entry
        if expires_at is None or time.monotonic() < expires_at:
            return cause
        del self._local[key]  # Expired — clean up.
        return None

    def _mirror(self, key: str, cause: Optional[DegradationCause]) -> None:
        """Keep the local copy of a Redis-confirmed needs_reauth state current.

        The copy is what answers if Redis then goes away; a key with an
        unreplayed outage-time mark/clear is left alone until it is flushed.
        """
        if key in self._pending_reauth or key in self._pending_clear:
            return
        if cause is DegradationCause.NEEDS_REAUTH:
            self._local[key] = (cause, None)
        else:
            self._local.pop(key, None)

    async def _flush_pending(self, redis) -> None:
        """Replay outage-time needs_reauth marks and clears into the recovered Redis.

        A mark replays with NX (never overwriting a newer mark). A clear replays
        as compare-and-delete: it removes only the mark its worker saw, so a
        newer mark another worker wrote meanwhile is not erased.
        """
        for key in list(self._pending_reauth):
            await redis.set(key, self._seen.get(key, DegradationCause.NEEDS_REAUTH.value), nx=True)
            self._pending_reauth.discard(key)
        for key, seen in list(self._pending_clear.items()):
            if seen is not None:
                await self._delete_if_equal(redis, key, seen)
            self._pending_clear.pop(key, None)

    @staticmethod
    async def _delete_if_equal(redis, key: str, expected: str) -> None:
        """Delete *key* only if it still holds *expected* (WATCH/MULTI compare-and-delete)."""
        from redis.exceptions import WatchError  # noqa: PLC0415

        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                current = await pipe.get(key)
                current = current.decode() if isinstance(current, bytes) else current
                if current != expected:
                    await pipe.unwatch()
                    return
                pipe.multi()
                pipe.delete(key)
                await pipe.execute()
            except WatchError:
                return  # changed under us: someone wrote a newer mark -- leave it

    def _alert_needs_reauth(self, provider: str, model: Optional[str]) -> None:
        """Emit an operator alert for a needs_reauth transition (#15022, #1948).

        Dedup and rate limiting are owned entirely by ``AlertCooldownManager``
        (progressive per-fingerprint cooldown, #1948) — this keeps no
        separate de-dup state of its own, so "exactly one alert per
        cooldown tier" is enforced there, not here.
        """
        target = provider if not model else f"{provider}:{model}"
        message = _reauth_alert_text(target)
        try:
            cooldown = _get_alert_cooldown()
            if cooldown.should_send(message, _NEEDS_REAUTH_ALERT_TIER):
                logger.warning("degradation: %s", message)
                cooldown.record_sent(message, _NEEDS_REAUTH_ALERT_TIER)
        except Exception:
            logger.debug("degradation: alert_cooldown unavailable for %s", target, exc_info=True)


def _reauth_alert_text(target: str) -> str:
    """Alert text whose cooldown fingerprint is unique per credential.

    ``alert_cooldown`` fingerprints the text with every standalone number
    replaced by ``<N>``, so ``acct-1`` and ``acct-2`` (or ``claude-3`` /
    ``claude-4``) would share one cooldown and the second dead credential
    would never be reported. The ``ref`` token starts with a letter, so the
    normaliser leaves it intact, and it is a digest of the exact target.
    """
    ref = hashlib.sha256(target.encode("utf-8")).hexdigest()[:12]
    return f"LLM provider credential needs re-auth: {target} (ref k{ref})"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

get_degradation_store = lazy_singleton(ProviderDegradationStore)

__all__ = [
    "AllCredentialsNeedReauthError",
    "DegradationCause",
    "ProviderDegradationStore",
    "get_degradation_store",
]
