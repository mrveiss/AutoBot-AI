# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration Rate Limiter (Issue #4162)

Async-native sliding-window rate limiter for external API integrations.
Tracks rate limit state per service key and supports header-based quota
updates (X-RateLimit-*, Retry-After) from GitHub and Slack API responses.

Delegates to the shared ``autobot_shared.rate_limiter.RateLimiter`` for the
core sliding-window logic (Issue #4460).
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.rate_limiter import RateLimiter as _SharedRateLimiter

logger = get_logger(__name__)

# GitHub: 5000 req/hr per authenticated token; 60 req/hr unauthenticated
GITHUB_REQUESTS_PER_HOUR = 5000
GITHUB_REQUESTS_PER_MINUTE = 90  # conservative local window

# Slack: variable per method; ~1 req/s for most Tier 1 methods
SLACK_REQUESTS_PER_MINUTE = 50
SLACK_REQUESTS_PER_HOUR = 2000


@dataclass
class RateLimitState:
    """Sliding-window request history for a single service/token pair."""

    requests_per_minute: int
    requests_per_hour: int
    # Timestamps of recent requests (epoch seconds)
    history: deque = field(default_factory=deque)
    # Absolute epoch time before which no new requests should be sent
    retry_after_until: float = 0.0

    def _prune(self, now: float) -> None:
        """Remove history entries older than one hour."""
        cutoff = now - 3600.0
        while self.history and self.history[0] < cutoff:
            self.history.popleft()

    def is_ready(self, now: float) -> tuple[bool, float]:
        """Return (can_proceed, seconds_to_wait).

        Returns False and the wait duration when the service enforced a
        Retry-After header or when local sliding windows are exhausted.
        """
        if now < self.retry_after_until:
            return False, self.retry_after_until - now

        self._prune(now)

        minute_window = now - 60.0
        now - 3600.0
        minute_count = sum(1 for t in self.history if t > minute_window)
        hour_count = len(self.history)

        if minute_count >= self.requests_per_minute:
            oldest_in_minute = next(t for t in self.history if t > minute_window)
            wait = 60.0 - (now - oldest_in_minute)
            return False, max(wait, 0.0)

        if hour_count >= self.requests_per_hour:
            oldest_in_hour = self.history[0]
            wait = 3600.0 - (now - oldest_in_hour)
            return False, max(wait, 0.0)

        return True, 0.0

    def record(self, now: float) -> None:
        """Record that a request was dispatched at *now*."""
        self._prune(now)
        self.history.append(now)

    def apply_retry_after(self, retry_after_seconds: float, now: float) -> None:
        """Set a hard pause based on a Retry-After response header."""
        self.retry_after_until = now + retry_after_seconds
        logger.warning("Rate limit enforced: pausing requests for %.1fs", retry_after_seconds)

    def apply_github_headers(self, headers: Dict[str, str], now: float) -> None:
        """Update quota state from GitHub X-RateLimit-* response headers.

        GitHub provides: X-RateLimit-Remaining, X-RateLimit-Reset (epoch),
        X-RateLimit-Limit.
        """
        remaining = headers.get("X-RateLimit-Remaining") or headers.get("x-ratelimit-remaining")
        reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")

        if remaining is not None and int(remaining) == 0 and reset is not None:
            wait = max(float(reset) - now, 1.0)
            self.apply_retry_after(wait, now)
        elif remaining is not None and int(remaining) < 10:
            logger.warning("GitHub rate limit quota nearly exhausted: %s remaining", remaining)


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
        # Lock is created lazily in acquire() so it always belongs to the
        # running event loop (avoids "lock created in different loop" hangs
        # in tests that create a new loop per test).
        self._lock: asyncio.Lock | None = None

    def _get_state(self, key: str) -> RateLimitState:
        if key not in self._states:
            self._states[key] = RateLimitState(
                requests_per_minute=self._rpm,
                requests_per_hour=self._rph,
            )
        return self._states[key]

    def check(self, key: str) -> tuple[bool, float]:
        """Check whether a request for *key* may proceed right now.

        Returns (can_proceed, seconds_to_wait).  Non-blocking.
        """
        state = self._get_state(key)
        return state.is_ready(time.monotonic())

    def record(self, key: str) -> None:
        """Record that a request for *key* was dispatched."""
        state = self._get_state(key)
        state.record(time.monotonic())

    def apply_response_headers(self, key: str, headers: Dict[str, str], service: str = "generic") -> None:
        """Update rate limit state from HTTP response headers.

        Supports GitHub X-RateLimit-* headers and the standard Retry-After
        header used by Slack (HTTP 429).
        """
        now = time.monotonic()
        state = self._get_state(key)

        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after is not None:
            try:
                state.apply_retry_after(float(retry_after), now)
            except ValueError:
                pass

        if service == "github":
            state.apply_github_headers(headers, now)

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
