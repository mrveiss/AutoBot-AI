# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Integration Rate Limiter (Issue #4162)

Async-native rate limiter for external API integrations. Tracks rate limit
state per service key and supports header-based quota updates
(X-RateLimit-*, Retry-After) from GitHub and Slack API responses.

What is distinct, and what is not (#18087, #7271):

* Distinct: the provider-header state (``RateLimitState``, ``apply_response_headers``).
  The provider's own ``X-RateLimit-*`` / ``Retry-After`` response headers
  correct the local view, a feedback loop the canonical limiter does not have.
* Not distinct: the request-count windows. The per-minute and per-hour windows
  are NOT implemented here; they are two ``LocalWindowCounter`` windows from
  ``autobot_shared.rate_limiter_window`` -- the per-process engine behind
  ``WindowFailurePolicy.LOCAL`` of the canonical ``RateLimiter``. Redis is
  never consulted because the keys are API tokens, which must not become Redis
  key names. Only the module-level ``integration_rate_limiter`` below is a
  Redis-backed canonical ``RateLimiter`` instance.

See ``repo_tests/one_rate_limiter_18087_test.py``.
"""

import asyncio
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.rate_limiter import RateLimiter as _SharedRateLimiter
from autobot_shared.rate_limiter_window import LocalWindowCounter

logger = get_logger(__name__)

# GitHub: 5000 req/hr per authenticated token; 60 req/hr unauthenticated
GITHUB_REQUESTS_PER_HOUR = 5000
GITHUB_REQUESTS_PER_MINUTE = 90  # conservative local window

_MINUTE = 60.0
_HOUR = 3600.0

# Slack: variable per method; ~1 req/s for most Tier 1 methods
SLACK_REQUESTS_PER_MINUTE = 50
SLACK_REQUESTS_PER_HOUR = 2000


@dataclass
class RateLimitState:
    """Provider-enforced pause for a single service/token pair.

    Holds only what the provider told us (``Retry-After`` / ``X-RateLimit-*``).
    Request-count windows live in ``IntegrationRateLimiter`` on the canonical
    ``LocalWindowCounter``.
    """

    # Absolute monotonic time before which no new requests should be sent
    retry_after_until: float = 0.0

    def pending_wait(self, now: float) -> float:
        """Return the seconds left on a provider-enforced pause (0.0 when none)."""
        return max(self.retry_after_until - now, 0.0)

    def apply_retry_after(self, retry_after_seconds: float, now: float) -> None:
        """Set a hard pause based on a Retry-After response header (never shortens a longer one)."""
        self.retry_after_until = max(self.retry_after_until, now + retry_after_seconds)
        logger.warning("Rate limit enforced: pausing requests for %.1fs", retry_after_seconds)

    def apply_github_headers(self, headers: Dict[str, str], now: float, wall_now: float) -> None:
        """Update quota state from GitHub X-RateLimit-* response headers.

        GitHub provides: X-RateLimit-Remaining, X-RateLimit-Reset (epoch),
        X-RateLimit-Limit. *now* is the monotonic clock the pause deadline is
        stored on; *wall_now* is ``time.time()``, the clock ``X-RateLimit-Reset``
        is an epoch on. The wait is measured on the wall clock and only then
        added to the monotonic *now*; never subtract one clock from the other.
        """
        remaining = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
        reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")

        try:
            remaining_n = int(remaining) if remaining is not None else None
            reset_epoch = float(reset) if reset is not None else None
        except ValueError:
            logger.warning("Ignoring malformed GitHub rate-limit headers")
            return
        if remaining_n == 0 and reset_epoch is not None:
            self.apply_retry_after(max(reset_epoch - wall_now, 1.0), now)
        elif remaining_n is not None and remaining_n < 10:
            logger.warning("GitHub rate limit quota nearly exhausted: %s remaining", remaining)


def _retry_after_seconds(value: str, wall_now: float) -> float | None:
    """Parse a ``Retry-After`` value: delta-seconds, or an HTTP-date (wall clock)."""
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        return max(parsedate_to_datetime(value).timestamp() - wall_now, 0.0)
    except (TypeError, ValueError):
        return None


class IntegrationRateLimiter:
    """Per-key async rate limiter for external integrations.

    One instance is shared per integration class. Keys are typically the
    API token or a service identifier so multi-tenant deployments track
    quotas independently.

    Usage::

        limiter = IntegrationRateLimiter(
            requests_per_minute=50,
            requests_per_hour=2000,
        )
        can, wait = limiter.check("my-token")
        if not can:
            await asyncio.sleep(wait)
        limiter.record("my-token")
        # … make HTTP call …
        limiter.apply_response_headers("my-token", response_headers)
    """

    def __init__(
        self,
        requests_per_minute: int,
        requests_per_hour: int,
    ) -> None:
        self._rpm = requests_per_minute
        self._rph = requests_per_hour
        self._states: Dict[str, RateLimitState] = {}
        # One counter per window: its stale-key eviction is keyed to a single window size.
        self._minute = LocalWindowCounter()
        self._hour = LocalWindowCounter()
        # Lock is created lazily in acquire() so it always belongs to the
        # running event loop (avoids "lock created in different loop" hangs
        # in tests that create a new loop per test).
        self._lock: asyncio.Lock | None = None

    def _get_state(self, key: str) -> RateLimitState:
        if key not in self._states:
            self._states[key] = RateLimitState()
        return self._states[key]

    def _windows(self) -> tuple[tuple[LocalWindowCounter, int, float], ...]:
        """(counter, limit, window seconds) for the minute then the hour window."""
        return ((self._minute, self._rpm, _MINUTE), (self._hour, self._rph, _HOUR))

    def check(self, key: str) -> tuple[bool, float]:
        """Check whether a request for *key* may proceed right now.

        Returns (can_proceed, seconds_to_wait).  Non-blocking.  Waits on a
        provider pause first, then on the minute window, then on the hour window.
        """
        wait = self._get_state(key).pending_wait(time.monotonic())
        if wait > 0.0:
            return False, wait
        for counter, limit, seconds in self._windows():
            used, reset_in = counter.usage(key, seconds)
            if used >= limit:
                return False, reset_in
        return True, 0.0

    def record(self, key: str) -> None:
        """Record that a request for *key* was dispatched."""
        for counter, _limit, seconds in self._windows():
            counter.record(key, seconds)

    def apply_response_headers(self, key: str, headers: Dict[str, str], service: str = "generic") -> None:
        """Update rate limit state from HTTP response headers.

        Supports GitHub X-RateLimit-* headers and the standard Retry-After
        header used by Slack (HTTP 429), as delta-seconds or an HTTP-date.
        """
        now = time.monotonic()
        wall_now = time.time()
        state = self._get_state(key)

        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after is not None:
            seconds = _retry_after_seconds(retry_after, wall_now)
            if seconds is not None:
                state.apply_retry_after(seconds, now)

        if service == "github":
            state.apply_github_headers(headers, now, wall_now)

    async def acquire(self, key: str, max_wait: float = 120.0) -> None:
        """Async acquire: waits until the rate limit allows a request.

        Raises ``asyncio.TimeoutError`` if *max_wait* seconds elapse without
        a slot becoming available.  Records the slot immediately on success.
        """
        # Create the lock lazily so it always belongs to the current event loop.
        if self._lock is None:
            self._lock = asyncio.Lock()
        deadline = time.monotonic() + max_wait
        async with self._lock:
            while True:
                can, wait = self.check(key)
                if can:
                    self.record(key)
                    return
                if time.monotonic() + wait > deadline:
                    raise asyncio.TimeoutError(f"Rate limit wait for '{key}' would exceed {max_wait}s")
                logger.info("Rate limited for key '%s': waiting %.1fs before retry", key, wait)
                # Release lock while sleeping so other coroutines can check
                self._lock.release()
                try:
                    await asyncio.sleep(min(wait, 5.0))
                finally:
                    await self._lock.acquire()


# ---------------------------------------------------------------------------
# Shared delegate (Issue #4460)
# ---------------------------------------------------------------------------
# A pre-configured instance of the shared RateLimiter scoped to integrations.
# Callers that need only a simple allow/record check can use this directly
# instead of importing the full IntegrationRateLimiter.
integration_rate_limiter = _SharedRateLimiter(
    scope_prefix="integration",
    default_tier="privileged",
    requests_per_minute=GITHUB_REQUESTS_PER_MINUTE,
    requests_per_hour=GITHUB_REQUESTS_PER_HOUR,
)
