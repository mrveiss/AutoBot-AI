# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Window-mode companions of the canonical ``RateLimiter`` (#18087, #7271).

``autobot_shared.rate_limiter.RateLimiter`` is the one rate limiter. This module
holds the pieces its single-window mode needs so that call sites which used to
carry their own limiter can delegate instead of re-implementing it:

* :class:`WindowFailurePolicy` -- what a window acquire does when Redis cannot
  answer. The caller picks it; the default is the house policy (fail open).
* :class:`LocalWindowCounter` -- the per-process sliding window the ``LOCAL``
  policy degrades to.
* :class:`WindowQuota` -- one named quota (key, limit, window) bound to a
  limiter, with the ``bool`` and HTTP-429 call shapes the old forks exposed.

Why the policy is a parameter and not a decision made here
----------------------------------------------------------
Three behaviours existed across the forks, and each is security- or
availability-relevant, so none is silently chosen for every caller:

    FAIL_OPEN    Redis down -> allow. Never blocks traffic, but switches the control
                 off for the outage. The default, and what every ``acquire_window``
                 caller had before this module.
    LOCAL        Redis down -> keep enforcing, per process. The limit is then
                 multiplied by the worker count, but the control never turns off.
                 What ``IPRateLimiter`` (public OpenAI/A2A endpoints) and the four
                 in-process MCP counters effectively did.
    FAIL_CLOSED  Redis down -> deny. For controls where over-admitting is worse than
                 an outage. With ``wait=True`` this blocks until Redis returns.

One further difference is NOT a parameter: ``IPRateLimiter`` recorded a request
*before* counting it, so a rejected request extended the window and a client
that kept retrying stayed locked out indefinitely. The canonical window records
only admitted requests, which is the intended sliding-window behaviour; that
defect is not preserved behind an option.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
from typing import TYPE_CHECKING, Any

from autobot_shared.env_utils import env_float, env_int
from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    from autobot_shared.rate_limiter import RateLimiter

logger = get_logger(__name__)

#: Cap on distinct keys the per-process fallback tracks; expired keys are evicted
#: first, and a new key is refused only when every tracked key is still live.
LOCAL_WINDOW_MAX_KEYS = env_int("AUTOBOT_RATE_LIMIT_LOCAL_MAX_KEYS", 10_000)

#: Minimum seconds between full-table eviction sweeps while the table is full; a new
#: key arriving in between is refused without scanning (#21907).
LOCAL_WINDOW_SWEEP_INTERVAL = env_float("AUTOBOT_RATE_LIMIT_LOCAL_SWEEP_INTERVAL", 1.0)


class WindowFailurePolicy(str, Enum):
    """What a single-window acquire does when Redis cannot answer."""

    FAIL_OPEN = "fail_open"
    LOCAL = "local"
    FAIL_CLOSED = "fail_closed"


class LocalWindowCounter:
    """Per-process sliding window; only admitted hits are recorded.

    Each key keeps the window it was last used with, so a key admitted under a
    long window is not evicted by a call that uses a short one. At most
    ``max_keys`` distinct keys are tracked: once full and nothing has expired, a
    new key is refused rather than evicting a live quota's history. The sweep that
    looks for expired keys runs at most once per ``sweep_interval`` seconds, so a
    flood of new keys on a full live table is refused without scanning (#21907).
    """

    def __init__(
        self, max_keys: int = LOCAL_WINDOW_MAX_KEYS, sweep_interval: float = LOCAL_WINDOW_SWEEP_INTERVAL
    ) -> None:
        self._max_keys = max_keys
        self._sweep_interval = sweep_interval
        self._last_sweep = float("-inf")  # monotonic; read and written under ``_lock``
        self._hits: dict[str, deque[float]] = {}
        self._windows: dict[str, float] = {}
        self._lock = threading.Lock()

    def _live(self, key: str, window_seconds: float, now: float) -> deque[float] | None:
        """Return the key's live hits (trimmed), or ``None`` when the table has no room for it."""
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= self._max_keys:
                self._sweep_if_due(now)
                if len(self._hits) >= self._max_keys:
                    return None
            hits = self._hits[key] = deque()
        self._windows[key] = max(window_seconds, self._windows.get(key, 0.0))
        while hits and hits[0] <= now - window_seconds:
            hits.popleft()
        return hits

    def try_acquire(self, key: str, max_requests: int, window_seconds: float) -> tuple[bool, float]:
        """Return ``(allowed, retry_after_seconds)``; record only on admit."""
        now = time.time()
        with self._lock:
            hits = self._live(key, window_seconds, now)
            if hits is None:
                return False, float(window_seconds)
            if len(hits) >= max_requests:
                retry_after = window_seconds - (now - hits[0]) if hits else window_seconds
                return False, max(0.0, retry_after)
            hits.append(now)
            return True, 0.0

    def record(self, key: str, window_seconds: float) -> None:
        """Record a hit unconditionally (the caller checked, or owes the count)."""
        now = time.time()
        with self._lock:
            hits = self._live(key, window_seconds, now)
            if hits is not None:
                hits.append(now)

    def usage(self, key: str, window_seconds: float) -> tuple[int, float]:
        """Return ``(hits_in_window, seconds_until_the_oldest_hit_expires)``; never creates a key."""
        now = time.time()
        with self._lock:
            hits = [h for h in self._hits.get(key, ()) if h > now - window_seconds]
            return len(hits), (max(0.0, window_seconds - (now - hits[0])) if hits else 0.0)

    def _sweep_if_due(self, now: float) -> None:
        """Run the full-table sweep at most once per interval; caller holds ``_lock``."""
        mono = time.monotonic()
        if mono - self._last_sweep < self._sweep_interval:
            return
        self._last_sweep = mono
        self._evict_stale(now)

    def _evict_stale(self, now: float) -> None:
        """Drop keys whose every hit has aged out of that key's own window."""
        for stale in [k for k, h in self._hits.items() if not h or h[-1] <= now - self._windows[k]]:
            del self._hits[stale]
            del self._windows[stale]

    def reset(self) -> None:
        """Forget every key (tests)."""
        with self._lock:
            self._hits.clear()
            self._windows.clear()


class WindowQuota:
    """One named window quota bound to a canonical :class:`RateLimiter`.

    ``key`` is the default subject (a fixed string for a global quota); pass a
    per-call key to ``acquire`` / ``check_or_429`` for per-client quotas.
    ``limit_env`` makes the limit re-read from that environment variable on
    every call, with ``max_requests`` as the fallback.
    """

    def __init__(
        self,
        limiter: RateLimiter,
        *,
        max_requests: int,
        window_seconds: int = 60,
        key: str = "global",
        label: str = "requests",
        limit_env: str | None = None,
    ) -> None:
        self.limiter = limiter
        self.window_seconds = window_seconds
        self.label = label
        self._key = key
        self._default_max = max_requests
        self._limit_env = limit_env

    @classmethod
    def for_scope(
        cls,
        scope: str,
        *,
        policy: WindowFailurePolicy = WindowFailurePolicy.FAIL_OPEN,
        log_rejections: bool = True,
        **quota: Any,
    ) -> WindowQuota:
        """Build a quota on its own canonical ``RateLimiter`` for *scope*.

        *quota* is the keyword set of ``__init__`` after the limiter. The
        limiter import is deferred because ``rate_limiter`` imports this module.
        ``log_rejections=False`` keeps a refusal silent (anonymous routes, where
        a flood would otherwise amplify into the log).
        """
        from autobot_shared.rate_limiter import RateLimiter  # noqa: PLC0415

        limiter = RateLimiter(scope, log_label=scope if log_rejections else None, window_failure_policy=policy)
        return cls(limiter, **quota)

    @property
    def max_requests(self) -> int:
        """The current limit (env-backed when ``limit_env`` was given)."""
        if self._limit_env is None:
            return self._default_max
        return env_int(self._limit_env, self._default_max)

    async def acquire(self, key: str | None = None) -> bool:
        """Atomically admit or refuse one request."""
        subject = key or self._key
        return await self.limiter.acquire_window(subject, self.max_requests, self.window_seconds)

    async def check_or_429(self, key: str | None = None) -> None:
        """``acquire``, raising ``HTTPException(429)`` when refused."""
        if await self.acquire(key):
            return
        from fastapi import HTTPException  # noqa: PLC0415

        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({self.max_requests} requests/{self.window_seconds}s). Try again later.",
        )

    async def status(self, key: str | None = None) -> dict[str, float | int]:
        """Return ``{"current", "max", "reset_in_seconds"}`` for the quota."""
        used, reset_in = await self.limiter.get_window_usage(key or self._key, self.window_seconds)
        return {"current": used, "max": self.max_requests, "reset_in_seconds": round(reset_in, 1)}

    def reset_local(self) -> None:
        """Drop the per-process fallback state (tests)."""
        self.limiter.reset_local_windows()


__all__ = ["LocalWindowCounter", "WindowFailurePolicy", "WindowQuota"]
