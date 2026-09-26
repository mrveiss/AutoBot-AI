# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared state for the MCP pre-auth throttle, degrading to per-process (#17450).

The lockout used to live in an ``OrderedDict`` on a module-level singleton, so
it was per worker and per process lifetime. A restart cleared every lockout
mid-attack, and with ``uvicorn --workers N`` the effective threshold was N times
the configured one. #8170 states that principle for LLM rate limits; it was
never applied to an authentication control.

DEGRADATION IS THE OWNER'S DECISION, and the reasoning belongs here rather than
only in a commit message:

    shared store OK    -> shared lockout, survives restart, one threshold
    shared store DOWN  -> per-process lockout, exactly today's behaviour

The worst case equals what already ships, so this adds no outage mode and no new
attack. **Fail-closed** would let anyone able to degrade Redis cause a total
authentication outage. **Fail-open** would let them switch brute-force
protection off. Degrading does neither.

THE LOGGING IS LOAD-BEARING, not decoration. A silent fallback becomes
permanent: the store fails once, nobody notices, and the control reverts to the
per-worker weakness this module exists to remove. An unlogged degradation is the
same defect arriving by a different route. So every state CHANGE is logged at
warning/info, and only changes -- logging every failed call would bury it.

CLOCKS DO NOT MIX. The in-process path uses ``time.monotonic()``, which is not
comparable across processes. This store uses wall clock exclusively and owns it
internally, so a timestamp from one is never compared against the other: whether
shared or degraded, exactly one of them is authoritative at a time.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_PREFIX = "mcp:preauth"


class StoreUnavailable(RuntimeError):
    """The shared store could not answer; the caller must use its local state."""


class SharedThrottleStore:
    """Redis-backed throttle state that reports its own unavailability.

    Every method either answers from the shared store or raises
    :class:`StoreUnavailable`. It never silently substitutes a local answer --
    the caller owns the degradation, so the decision is visible at the call site
    rather than buried here.
    """

    def __init__(self, client_factory: Callable[[], Any]) -> None:
        self._client_factory = client_factory
        self._client: Optional[Any] = None
        self._degraded = False

    # -- availability ----------------------------------------------------

    def _fail(self, operation: str, exc: BaseException) -> StoreUnavailable:
        """Record a degradation and return the exception for the caller to raise."""
        if not self._degraded:
            self._degraded = True
            self._client = None
            logger.warning(
                "MCP pre-auth throttle DEGRADED to per-process state: %s failed (%s). "
                "Lockouts are now per worker and cleared by a restart until the shared "
                "store recovers (#17450).",
                operation,
                exc,
            )
        return StoreUnavailable(operation)

    def _recovered(self) -> None:
        if self._degraded:
            self._degraded = False
            logger.info(
                "MCP pre-auth throttle RECOVERED to shared state; lockouts are shared " "across workers again (#17450)."
            )

    def _redis(self) -> Any:
        if self._client is None:
            self._client = self._client_factory()
        if self._client is None:
            raise self._fail("client acquisition", RuntimeError("no client"))
        return self._client

    # -- operations mirroring the in-process containers -------------------

    def failures_in_window(self, ip: str, window_seconds: float) -> int:
        """Count of this IP's failures inside the window."""
        key = f"{_PREFIX}:fail:{ip}"
        try:
            client = self._redis()
            client.zremrangebyscore(key, 0, time.time() - window_seconds)
            count = int(client.zcard(key))
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise self._fail("failures_in_window", exc) from exc
        self._recovered()
        return count

    def add_failure(self, ip: str, window_seconds: float) -> None:
        """Record one failure, expiring the key with the window."""
        key = f"{_PREFIX}:fail:{ip}"
        now = time.time()
        try:
            client = self._redis()
            client.zadd(key, {f"{now}": now})
            client.expire(key, int(window_seconds) + 1)
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise self._fail("add_failure", exc) from exc
        self._recovered()

    def lockout_remaining(self, ip: str) -> float:
        """Seconds of lockout left for *ip*, or 0.0 when not locked."""
        key = f"{_PREFIX}:lock:{ip}"
        try:
            ttl = int(self._redis().ttl(key))
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise self._fail("lockout_remaining", exc) from exc
        self._recovered()
        return float(ttl) if ttl > 0 else 0.0

    def arm_lockout(self, ip: str, seconds: float) -> None:
        """Lock *ip* out for *seconds*, which is also the key's TTL."""
        key = f"{_PREFIX}:lock:{ip}"
        try:
            self._redis().setex(key, max(int(seconds), 1), "1")
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise self._fail("arm_lockout", exc) from exc
        self._recovered()

    def global_failures_in_window(self, window_seconds: float) -> int:
        """Endpoint-wide failure count inside the window."""
        key = f"{_PREFIX}:global"
        try:
            client = self._redis()
            client.zremrangebyscore(key, 0, time.time() - window_seconds)
            count = int(client.zcard(key))
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise self._fail("global_failures_in_window", exc) from exc
        self._recovered()
        return count

    def add_global_failure(self, window_seconds: float) -> None:
        """Record one endpoint-wide failure."""
        key = f"{_PREFIX}:global"
        now = time.time()
        try:
            client = self._redis()
            client.zadd(key, {f"{now}:{id(self)}": now})
            client.expire(key, int(window_seconds) + 1)
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise self._fail("add_global_failure", exc) from exc
        self._recovered()

    def has_recent_success(self, ip: str) -> bool:
        """Whether *ip* authenticated inside the window.

        Exempts a caller from the GLOBAL ceiling only -- never from its own
        per-IP budget. Authenticating once must not buy a licence to guess.
        """
        key = f"{_PREFIX}:ok:{ip}"
        try:
            present = bool(self._redis().exists(key))
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise self._fail("has_recent_success", exc) from exc
        self._recovered()
        return present

    def mark_success(self, ip: str, window_seconds: float) -> None:
        """Note a successful authentication and clear this IP's failure state."""
        try:
            client = self._redis()
            client.setex(f"{_PREFIX}:ok:{ip}", max(int(window_seconds), 1), "1")
            client.delete(f"{_PREFIX}:fail:{ip}", f"{_PREFIX}:lock:{ip}")
        except StoreUnavailable:
            raise
        except Exception as exc:
            raise self._fail("mark_success", exc) from exc
        self._recovered()
