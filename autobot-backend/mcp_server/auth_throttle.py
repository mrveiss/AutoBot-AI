# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pre-authentication throttle for the MCP HTTP transport (#13268).

``POST /api/mcp/tool`` has no auth layer other than the shared MCP secret
(``middleware/service_auth_enforcement.py`` lists the path in neither
``EXEMPT_PATHS`` nor ``SERVICE_ONLY_PATHS``, so it falls through to
``call_next``).  Until #13268 the only rate limiter ran *after* a successful
token check, which left two holes:

1. Guessing the secret was free — failed attempts were never counted.
2. Every failed attempt reached ``_validate_redis_token``'s Redis ``GET``
   before rejection, so an unauthenticated caller could drive Redis load at
   request rate.

This module counts *failures* before any validation work happens.

Why the counter is not keyed on the token
-----------------------------------------
The post-auth bucket keys on ``auth_token[:16]``.  That is safe only because
it runs after authentication; keying a *pre-auth* counter on caller-supplied
token bytes would let an attacker grow the map without bound.  Failures are
therefore keyed on client IP, and the map itself is capped
(``AUTOBOT_MCP_AUTH_MAX_TRACKED_IPS``) with oldest-first eviction.

Why a per-IP counter alone is not enough
----------------------------------------
``get_client_ip()`` honours ``X-Forwarded-For`` when the TCP peer is a trusted
proxy, and takes the leftmost value.  The shipped nginx templates set
``proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for``, which
*appends* the peer to whatever the client sent — so behind the proxy the
leftmost element is attacker-controlled.  A per-IP lockout is therefore
defeated by rotating one header value per request.

To close that, failures are counted twice: per IP *and* globally across all
IPs in the same window.  The global ceiling is not something a caller can
rotate away from, so brute force is bounded even when every request claims a
fresh source address.  Legitimate traffic is unaffected because a successful
authentication clears the failure record.

All thresholds come from ``autobot_shared.ssot_config`` (env-fed); nothing is
hardcoded at a call site.
"""

from __future__ import annotations

import time
from collections import OrderedDict, deque
from typing import Deque, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

#: Sentinel used when the transport cannot determine a peer address.
UNKNOWN_IP = "unknown"


def _max_failures() -> int:
    """Failed attempts per IP within the window before that IP is locked out."""
    return int(config.mcp_auth_max_failures)


def _window_seconds() -> float:
    """Sliding window over which failures accumulate."""
    return float(config.mcp_auth_window_seconds)


def _lockout_seconds() -> float:
    """How long a tripped IP stays blocked after its last failure."""
    return float(config.mcp_auth_lockout_seconds)


def _global_max_failures() -> int:
    """Failures across all IPs in one window before the endpoint sheds load."""
    return int(config.mcp_auth_global_max_failures)


def _max_tracked_ips() -> int:
    """Upper bound on tracked IPs; oldest entries are evicted past this."""
    return int(config.mcp_auth_max_tracked_ips)


class _IpRecord:
    """Failure timestamps and lockout expiry for a single client IP."""

    __slots__ = ("failures", "locked_until")

    def __init__(self) -> None:
        self.failures: Deque[float] = deque()
        self.locked_until: float = 0.0

    def prune(self, cutoff: float) -> None:
        """Drop failure timestamps older than *cutoff*."""
        while self.failures and self.failures[0] <= cutoff:
            self.failures.popleft()


class PreAuthThrottle:
    """Counts failed MCP authentications before any validation work runs.

    Not thread-safe by design: the FastAPI route is async and single-threaded
    per event loop, matching the existing ``_TokenBucket`` in
    ``mcp/autobot_server.py``.
    """

    def __init__(self) -> None:
        """Initialise empty per-IP and global failure state."""
        self._ips: "OrderedDict[str, _IpRecord]" = OrderedDict()
        self._global_failures: Deque[float] = deque()
        # Callers that authenticated within the window. Exempt from the global
        # ceiling only (see check) so a flood of anonymous failures cannot take
        # the endpoint offline for clients that are demonstrably not the source.
        self._recent_success: "OrderedDict[str, float]" = OrderedDict()
        self._last_evict_log: float = 0.0

    # -- internal helpers ------------------------------------------------

    def _record_for(self, ip: str, now: float) -> _IpRecord:
        """Return the record for *ip*, creating and size-capping as needed."""
        record = self._ips.get(ip)
        if record is None:
            record = _IpRecord()
            self._ips[ip] = record
        self._ips.move_to_end(ip)
        self._evict_overflow(now)
        return record

    def _evict_overflow(self, now: float) -> None:
        """Evict least-recently-touched entries so the maps stay bounded.

        N1: eviction is oldest-first, so an attacker who rotates enough source
        addresses can push their own record out and clear their per-IP lockout.
        The per-IP tier is therefore NON-AUTHORITATIVE by construction — it exists
        to stop naive repetition cheaply. The endpoint-wide ceiling in check() is
        the control that actually bounds a rotating attacker, and it cannot be
        evicted because it is a single counter, not a keyed entry.

        N3: the eviction warning is sampled to once per window. Logging inside
        this loop would give an unauthenticated caller a log line per rotating-IP
        request — the same amplification #13268 set out to close.
        """
        limit = _max_tracked_ips()
        if limit <= 0:
            return
        evicted = 0
        while len(self._ips) > limit:
            self._ips.popitem(last=False)
            evicted += 1
        while len(self._recent_success) > limit:
            self._recent_success.popitem(last=False)
        if evicted and now - self._last_evict_log >= _window_seconds():
            self._last_evict_log = now
            logger.warning(
                "mcp_throttle: tracker at limit=%d, evicted %d least-recent entries in the last %.0fs "
                "— source addresses may be spoofed; the endpoint-wide ceiling still applies",
                limit,
                evicted,
                _window_seconds(),
            )

    def _prune_global(self, cutoff: float) -> None:
        """Drop global failure timestamps older than *cutoff*."""
        while self._global_failures and self._global_failures[0] <= cutoff:
            self._global_failures.popleft()

    # -- public API ------------------------------------------------------

    def check(self, ip: str, now: float | None = None) -> Tuple[bool, str]:
        """Return ``(blocked, reason)`` for *ip* without mutating counters.

        Called before token validation so a locked-out caller never reaches
        the Redis lookup in ``_validate_redis_token``.
        """
        now = time.monotonic() if now is None else now
        cutoff = now - _window_seconds()

        # B2: the ceiling sheds only callers that have not proven themselves.
        # Applying it unconditionally made 100 anonymous failures per window
        # enough to take the endpoint offline platform-wide for everyone,
        # including holders of a valid token — an unauthenticated DoS.
        # The anti-rotation property survives: an attacker cannot join
        # _recent_success without first authenticating.
        if not self._has_recent_success(ip, cutoff):
            self._prune_global(cutoff)
            global_ceiling = _global_max_failures()
            if global_ceiling > 0 and len(self._global_failures) >= global_ceiling:
                return True, (
                    f"endpoint-wide auth failure ceiling reached "
                    f"({len(self._global_failures)}/{global_ceiling} in {_window_seconds():.0f}s)"
                )

        # A recent success exempts a caller from the CEILING only, never from its
        # own per-IP budget below: authenticating once must not buy an unlimited
        # licence to guess afterwards.
        record = self._ips.get(ip)
        if record is None:
            return False, ""
        if record.locked_until > now:
            return True, f"client locked out for a further {record.locked_until - now:.0f}s"

        record.prune(cutoff)
        limit = _max_failures()
        if limit > 0 and len(record.failures) >= limit:
            return True, f"{len(record.failures)} failed attempts in {_window_seconds():.0f}s (limit {limit})"
        return False, ""

    def record_failure(self, ip: str, now: float | None = None) -> None:
        """Count one failed authentication from *ip* and arm lockout if tripped."""
        now = time.monotonic() if now is None else now
        cutoff = now - _window_seconds()

        record = self._record_for(ip, now)
        record.prune(cutoff)
        record.failures.append(now)

        self._prune_global(cutoff)
        self._global_failures.append(now)

        limit = _max_failures()
        if limit > 0 and len(record.failures) >= limit:
            record.locked_until = now + _lockout_seconds()
            logger.warning(
                "mcp_throttle: locking out client for %.0fs after %d failed MCP auth attempts in %.0fs",
                _lockout_seconds(),
                len(record.failures),
                _window_seconds(),
            )

    def _has_recent_success(self, ip: str, cutoff: float) -> bool:
        """Return True if *ip* authenticated within the current window."""
        ts = self._recent_success.get(ip)
        if ts is None:
            return False
        if ts <= cutoff:
            del self._recent_success[ip]
            return False
        return True

    def record_success(self, ip: str, now: float | None = None) -> None:
        """Clear *ip*'s failure record and exempt it from the ceiling for one window.

        The global counter is deliberately NOT cleared here. It is the only
        control that bounds an attacker who rotates source addresses, and behind
        an appending proxy the caller chooses the address it presents — so
        clearing it on any single success would hand that attacker a reset button
        (they need one valid credential, or one spoofed address that recently
        succeeded). Do not "fix" the ceiling by draining it on success.

        N2: for the same reason, note that a valid-credential holder can clear
        the per-IP record of an address it does not own. That tier is already
        non-authoritative (see _evict_overflow); the ceiling is not affected.
        """
        now = time.monotonic() if now is None else now
        self._ips.pop(ip, None)
        self._recent_success[ip] = now
        self._recent_success.move_to_end(ip)
        self._evict_overflow(now)

    def reset(self) -> None:
        """Drop all state. Test helper; also usable for an operator unblock."""
        self._ips.clear()
        self._global_failures.clear()
        self._recent_success.clear()
        self._last_evict_log = 0.0


_throttle: PreAuthThrottle | None = None


def get_pre_auth_throttle() -> PreAuthThrottle:
    """Return the process-wide PreAuthThrottle singleton."""
    global _throttle
    if _throttle is None:
        _throttle = PreAuthThrottle()
    return _throttle
