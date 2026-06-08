# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Multi-tier Alert Cooldown System (Issue #1948)
==============================================

Prevents notification fatigue through three complementary mechanisms:

1. **Tier-based rate limiting** — each tier has a per-hour send budget.
2. **Per-alert cooldown** — a successfully sent alert cannot re-fire until
   its tier-specific cooldown window expires.
3. **Progressive suppression** — recurring alerts (same semantic fingerprint)
   experience an exponentially increasing cooldown: 0 h → 6 h → 12 h → 24 h.

Tier overview
-------------
- FLASH    (critical)  — 6 sends / hour,  5-minute base cooldown
- PRIORITY (warning)   — 4 sends / hour, 30-minute base cooldown
- ROUTINE  (info)      — 2 sends / hour, 60-minute base cooldown

Semantic deduplication
----------------------
Alert text is normalised before fingerprinting:
  - leading/trailing whitespace stripped
  - numeric tokens replaced with ``<N>``
  - ISO-8601-like timestamps removed
  - whitespace collapsed to single space

The resulting string is SHA-256 hashed.  Two alerts that differ only in
a counter or timestamp therefore share the same fingerprint and are
treated as identical for cooldown / suppression purposes.

Redis key layout
----------------
- ``alerts:cooldown:{tier}:{hash}``  — TTL set to the active cooldown window;
  value is the recurrence count (used for progressive suppression).
- ``alerts:rate:{tier}:{window_ts}`` — integer counter for the current
  one-hour window; expires automatically when the window rolls over.

Usage
-----
    from autobot_shared.alert_cooldown import AlertCooldownManager, AlertTier

    mgr = AlertCooldownManager()

    if mgr.should_send("Disk usage at 95% on node-3", AlertTier.FLASH):
        send_alert(...)
        mgr.record_sent("Disk usage at 95% on node-3", AlertTier.FLASH)
"""

import hashlib
import logging
import re
import time
from enum import Enum

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RATE_WINDOW_SECONDS = 3600  # 1-hour sliding window for rate limits

# Progressive suppression cooldown schedule (in seconds).
# Index = recurrence count (0-based); last entry is the cap.
_PROGRESSIVE_COOLDOWNS = [
    0,  # 0 h — first recurrence: use tier base cooldown only
    6 * 3600,  # 6 h
    12 * 3600,  # 12 h
    24 * 3600,  # 24 h — cap
]


# ---------------------------------------------------------------------------
# AlertTier enum
# ---------------------------------------------------------------------------


class AlertTier(Enum):
    """Alert severity tier with embedded rate-limit and cooldown config.

    Attributes:
        max_per_hour: Maximum number of sends allowed within a rolling hour.
        base_cooldown_seconds: Minimum quiet period after the first send.
    """

    FLASH = ("flash", 6, 5 * 60)  # critical — 6/hr, 5 min cooldown
    PRIORITY = ("priority", 4, 30 * 60)  # warning  — 4/hr, 30 min cooldown
    ROUTINE = ("routine", 2, 60 * 60)  # info     — 2/hr, 60 min cooldown

    def __init__(self, tier_name: str, max_per_hour: int, base_cooldown_seconds: int) -> None:
        self.tier_name = tier_name
        self.max_per_hour = max_per_hour
        self.base_cooldown_seconds = base_cooldown_seconds


# ---------------------------------------------------------------------------
# AlertCooldownManager
# ---------------------------------------------------------------------------


class AlertCooldownManager:
    """Manages multi-tier alert cooldown, rate limiting, and progressive suppression.

    All state is persisted in Redis so the manager is stateless across
    restarts and safe to use from multiple processes simultaneously.

    Args:
        database: Redis logical database name (default: ``"main"``).
    """

    def __init__(self, database: str = "main") -> None:
        self._database = database

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_send(self, alert_text: str, tier: AlertTier) -> bool:
        """Return True if the alert passes all cooldown and rate-limit checks.

        Checks (in order, short-circuiting):
        1. Per-tier rate limit (hourly budget).
        2. Per-alert cooldown (is the key still live in Redis?).

        Args:
            alert_text: Human-readable alert message.
            tier: The severity tier governing limits.

        Returns:
            True when the alert should be forwarded; False when suppressed.
        """
        fingerprint = _fingerprint(alert_text)
        redis_client = self._get_client()
        if redis_client is None:
            # If Redis is unavailable, allow the alert through (fail-open).
            logger.warning(
                "alert_cooldown: Redis unavailable — allowing alert through (fail-open). " "tier=%s fingerprint=%s",
                tier.tier_name,
                fingerprint,
            )
            return True

        if self._rate_limit_exceeded(redis_client, tier):
            logger.debug(
                "alert_cooldown: rate limit exceeded — suppressing. tier=%s fingerprint=%s",
                tier.tier_name,
                fingerprint,
            )
            return False

        if self._in_cooldown(redis_client, tier, fingerprint):
            logger.debug(
                "alert_cooldown: in cooldown — suppressing. tier=%s fingerprint=%s",
                tier.tier_name,
                fingerprint,
            )
            return False

        return True

    def record_sent(self, alert_text: str, tier: AlertTier) -> None:
        """Record that an alert was sent, updating rate counters and cooldown keys.

        Must be called immediately after the alert is dispatched so that
        subsequent calls to :meth:`should_send` reflect the new state.

        Args:
            alert_text: The same message passed to :meth:`should_send`.
            tier: The same tier passed to :meth:`should_send`.
        """
        fingerprint = _fingerprint(alert_text)
        redis_client = self._get_client()
        if redis_client is None:
            logger.warning(
                "alert_cooldown: Redis unavailable — cannot record sent alert. " "tier=%s fingerprint=%s",
                tier.tier_name,
                fingerprint,
            )
            return

        self._increment_rate_counter(redis_client, tier)
        self._set_cooldown(redis_client, tier, fingerprint)
        logger.debug(
            "alert_cooldown: recorded sent alert. tier=%s fingerprint=%s",
            tier.tier_name,
            fingerprint,
        )

    # ------------------------------------------------------------------
    # Internal helpers — rate limiting
    # ------------------------------------------------------------------

    def _rate_window_key(self, tier: AlertTier) -> str:
        """Redis key for the current one-hour rate window."""
        window_ts = int(time.time()) // _RATE_WINDOW_SECONDS
        return f"alerts:rate:{tier.tier_name}:{window_ts}"

    def _rate_limit_exceeded(self, redis_client, tier: AlertTier) -> bool:
        """Return True if the tier's hourly send budget is exhausted."""
        key = self._rate_window_key(tier)
        raw = redis_client.get(key)
        if raw is None:
            return False
        return int(raw) >= tier.max_per_hour

    def _increment_rate_counter(self, redis_client, tier: AlertTier) -> None:
        """Increment the hourly rate counter, setting a TTL on first write."""
        key = self._rate_window_key(tier)
        pipe = redis_client.pipeline()
        pipe.incr(key)
        # TTL slightly longer than window to handle boundary edge-cases.
        pipe.expire(key, _RATE_WINDOW_SECONDS + 60)
        pipe.execute()

    # ------------------------------------------------------------------
    # Internal helpers — cooldown
    # ------------------------------------------------------------------

    def _cooldown_key(self, tier: AlertTier, fingerprint: str) -> str:
        """Redis key for the per-alert cooldown entry."""
        return f"alerts:cooldown:{tier.tier_name}:{fingerprint}"

    def _in_cooldown(self, redis_client, tier: AlertTier, fingerprint: str) -> bool:
        """Return True if the cooldown key is still alive in Redis."""
        key = self._cooldown_key(tier, fingerprint)
        return redis_client.exists(key) == 1

    def _set_cooldown(self, redis_client, tier: AlertTier, fingerprint: str) -> None:
        """Write (or refresh) the cooldown key with the appropriate TTL.

        The TTL is the maximum of the tier's base cooldown and the
        progressive suppression schedule determined by the recurrence count.
        """
        key = self._cooldown_key(tier, fingerprint)
        recurrence = _get_and_increment_recurrence(redis_client, key)
        ttl = _resolve_cooldown_ttl(tier, recurrence)
        # Store recurrence count so future calls can escalate the suppression.
        redis_client.set(key, recurrence + 1, ex=ttl)
        logger.debug(
            "alert_cooldown: set cooldown. tier=%s fingerprint=%s recurrence=%d ttl=%ds",
            tier.tier_name,
            fingerprint,
            recurrence,
            ttl,
        )

    # ------------------------------------------------------------------
    # Redis client helper
    # ------------------------------------------------------------------

    def _get_client(self):
        """Return a synchronous Redis client, or None on failure."""
        try:
            return get_redis_client(async_client=False, database=self._database)
        except Exception as exc:
            logger.error("alert_cooldown: failed to obtain Redis client: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _normalise(text: str) -> str:
    """Normalise alert text for semantic fingerprinting.

    Strips timestamps and numeric tokens so that alerts differing only in
    a counter value or wall-clock time are treated as identical.

    Args:
        text: Raw alert message.

    Returns:
        Normalised string suitable for hashing.
    """
    # Remove ISO-8601-like timestamps (e.g. 2025-03-31T12:00:00, 2025-03-31 12:00:00)
    text = re.sub(
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?",
        "",
        text,
    )
    # Replace remaining numeric tokens with a placeholder
    text = re.sub(r"\b\d+(?:\.\d+)?\b", "<N>", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fingerprint(text: str) -> str:
    """Return the SHA-256 hex digest of the normalised alert text.

    Args:
        text: Raw alert message.

    Returns:
        64-character lowercase hex string.
    """
    normalised = _normalise(text)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _get_and_increment_recurrence(redis_client, cooldown_key: str) -> int:
    """Read the existing recurrence count from the cooldown key (0 if absent).

    The value stored in the cooldown key is the recurrence count from the
    *previous* send.  We read it here before overwriting with the new count
    in :meth:`AlertCooldownManager._set_cooldown`.

    Args:
        redis_client: Synchronous Redis client.
        cooldown_key: The full Redis key for the cooldown entry.

    Returns:
        Current recurrence count (0 for the very first send).
    """
    raw = redis_client.get(cooldown_key)
    if raw is None:
        return 0
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def _resolve_cooldown_ttl(tier: AlertTier, recurrence: int) -> int:
    """Calculate the TTL (seconds) for the cooldown key.

    Combines the tier's base cooldown with the progressive suppression
    schedule.  The result is the *maximum* of the two so that the base
    cooldown is always respected even on the first recurrence.

    Args:
        tier: The alert tier (carries base_cooldown_seconds).
        recurrence: Zero-based count of how many times this fingerprint
                    has been sent previously.

    Returns:
        TTL in seconds (always >= tier.base_cooldown_seconds).
    """
    # Clamp recurrence to the last schedule entry.
    schedule_index = min(recurrence, len(_PROGRESSIVE_COOLDOWNS) - 1)
    progressive_ttl = _PROGRESSIVE_COOLDOWNS[schedule_index]
    return max(tier.base_cooldown_seconds, progressive_ttl)
