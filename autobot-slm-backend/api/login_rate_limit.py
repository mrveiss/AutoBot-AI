# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rate limit for ``POST /api/auth/login`` (#20600).

The SLM is the first thing a user installs and its admin owns the first login, so the limit
must slow a guesser without becoming a way to lock the real admin out. Design:

* **Per client IP** (``anonymous`` tier, strict): charged on every attempt, so one source
  guessing many names is slowed whatever it guesses.
* **Per username** (``authenticated`` tier, looser): charged only for a *failed* password, and
  only after the password has been checked. Charging every attempt let a few addresses lock
  the real admin out of their own correct password. A username over its failed-attempt limit
  refuses only a *wrong* password (429, the same bucket Retry-After); a correct password from
  an address under its IP limit is never refused by it.
  What this leaves an attacker: the password is verified on every attempt (bcrypt, the same
  work for 401 and 429, so timing does not separate them), hence a locked name still answers
  "right" vs "wrong" -- distributed guessing is held by the per-IP bucket, not by the username
  bucket. The username bucket's job is to stop being a free oracle on audit and to make a
  sustained many-source attack visible (refusals are audited). Refused attempts are not
  recorded, so the lock lifts on its own.
* **Unknown client address** (no connection info at all -- an omitted ``X-Forwarded-For``
  never causes this, the TCP peer is always known): there is no address to key on, so these
  share one bucket in the ``privileged`` tier. The shared bucket is large
  enough that unknown clients do not lock each other out in normal use.
* **Way back in**: the shared limiter is a sliding window and refused attempts are not
  recorded, so every lock lifts by itself -- within a minute of the attack stopping, within
  the hour window at worst. ``Retry-After`` carries the exact wait. There is no admin reset
  command; clearing the ``autobot:rl:slm_login_*`` keys in Redis lifts a lock at once.
* **Redis down**: the limiter fails open (the SLM must let people in), but every such
  attempt is logged at ERROR and counted (``fail_open_count`` on each limiter).
* **Audit**: at most one ``auth.login`` row per bucket per window (plus a global cap), the
  rest only counted in the log, so a flood cannot grow the audit table without bound.

Limits come from the SSOT tiers (``rate_limit_*_rpm`` / ``_rph``); this module carries none.
"""

from __future__ import annotations

import logging
import time

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.security import create_audit_log
from autobot_shared.env_utils import env_float, env_int
from autobot_shared.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

AUDIT_WINDOW_SECONDS: float = env_float("SLM_LOGIN_AUDIT_WINDOW_SECONDS", 300.0)
AUDIT_MAX_ROWS_PER_WINDOW: int = env_int("SLM_LOGIN_AUDIT_MAX_ROWS_PER_WINDOW", 100)
_AUDIT_MAX_TRACKED_BUCKETS = env_int("SLM_LOGIN_AUDIT_MAX_TRACKED_BUCKETS", 10000)

_ip_limiter = RateLimiter(scope_prefix="slm_login_ip", default_tier="anonymous")
_unknown_ip_limiter = RateLimiter(scope_prefix="slm_login_noip", default_tier="privileged")
_username_limiter = RateLimiter(scope_prefix="slm_login_user", default_tier="authenticated")

# bucket key -> (window start, refusals counted since the last audited one)
_audit_state: dict[str, tuple[float, int]] = {}
_global_window: list = [0.0, 0]  # [window start, rows written]


def _fail_open_total(*limiters: RateLimiter) -> int:
    return sum(limiter.fail_open_count for limiter in limiters)


def _user_key(username: str) -> str:
    return f"username:{username.strip().lower()}"


async def _charge_ip_bucket(client_ip: str | None, ip_limiter: RateLimiter, unknown_ip_limiter: RateLimiter):
    """Charge the per-address bucket for this attempt; ``(wait, key)`` when it is over, else ``None``."""
    limiter, key = (ip_limiter, f"ip:{client_ip}") if client_ip else (unknown_ip_limiter, "ip:unknown")
    if await limiter.acquire(key):
        return None
    return await limiter.get_retry_after_seconds(key), key


async def _username_wait(username: str, username_limiter: RateLimiter) -> int | None:
    """Peek (``is_allowed`` never records) the failed-attempt bucket; the wait when it is over."""
    key = _user_key(username)
    if await username_limiter.is_allowed(key):
        return None
    return await username_limiter.get_retry_after_seconds(key)


def _log_fail_open(before: int, limiters: tuple[RateLimiter, ...]) -> None:
    failed_open = _fail_open_total(*limiters) - before
    if failed_open:
        logger.error(
            "Login rate limiter FAILED OPEN: Redis unavailable or erroring, login allowed unthrottled "
            "(this attempt: %d, since start: %d)",
            failed_open,
            _fail_open_total(*limiters),
        )


async def enforce_login_rate_limit(
    audit_db: AsyncSession,
    client_ip: str | None,
    username: str,
    *,
    ip_limiter: RateLimiter = _ip_limiter,
    username_limiter: RateLimiter = _username_limiter,
    unknown_ip_limiter: RateLimiter = _unknown_ip_limiter,
) -> int | None:
    """Charge the address bucket and raise 429 when it is over (audited once per bucket per window).

    Returns the seconds to wait when the *username* is over its failed-attempt limit, else ``None``.
    That is not a refusal yet: the caller checks the password first and calls
    ``refuse_locked_username`` only for a wrong one, so a correct password is never turned away.
    """
    limiters = (ip_limiter, username_limiter, unknown_ip_limiter)
    before = _fail_open_total(*limiters)
    refused = await _charge_ip_bucket(client_ip, ip_limiter, unknown_ip_limiter)
    locked_wait = None if refused else await _username_wait(username, username_limiter)
    _log_fail_open(before, limiters)
    if refused:
        await _refuse(audit_db, client_ip, username, refused[0], refused[1])
    return locked_wait


async def record_failed_login(username: str, *, username_limiter: RateLimiter = _username_limiter) -> None:
    """Charge the username bucket for one wrong password (a success never calls this)."""
    before = _fail_open_total(username_limiter)
    await username_limiter.record(_user_key(username))
    _log_fail_open(before, (username_limiter,))


async def refuse_locked_username(
    audit_db: AsyncSession, client_ip: str | None, username: str, retry_after: int
) -> None:
    """Raise 429 for a wrong password on a username that is over its failed-attempt limit."""
    await _refuse(audit_db, client_ip, username, retry_after, _user_key(username))


def _audit_decision(bucket: str, now: float) -> tuple[bool, int]:
    """Return ``(write an audit row, refusals suppressed since the last row)`` for *bucket*."""
    if now - _global_window[0] >= AUDIT_WINDOW_SECONDS:
        _global_window[:] = [now, 0]
    start, suppressed = _audit_state.get(bucket, (None, 0))
    if start is not None and now - start < AUDIT_WINDOW_SECONDS:
        _audit_state[bucket] = (start, suppressed + 1)
        return False, suppressed + 1
    if len(_audit_state) >= _AUDIT_MAX_TRACKED_BUCKETS:
        for key in [k for k, (t, _) in _audit_state.items() if now - t >= AUDIT_WINDOW_SECONDS]:
            del _audit_state[key]
    if _global_window[1] >= AUDIT_MAX_ROWS_PER_WINDOW or len(_audit_state) >= _AUDIT_MAX_TRACKED_BUCKETS:
        return False, suppressed
    _audit_state[bucket] = (now, 0)
    _global_window[1] += 1
    return True, suppressed


async def _refuse(audit_db: AsyncSession, client_ip: str | None, username: str, retry_after: int, bucket: str):
    """Raise 429 (with ``Retry-After``); audit the first refusal per bucket per window."""
    write_row, suppressed = _audit_decision(bucket, time.monotonic())
    logger.warning(
        "Login rate limit exceeded (audited=%s, refusals not audited in this window=%d)",
        write_row,
        suppressed,
        extra={"retry_after": retry_after},
    )
    if write_row:
        await _audit_refusal(audit_db, client_ip, username)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Please try again later.",
        headers={"Retry-After": str(retry_after)},
    )


async def _audit_refusal(audit_db: AsyncSession, client_ip: str | None, username: str) -> None:
    await create_audit_log(
        audit_db,
        category="authentication",
        action="auth.login",
        username=username,
        ip_address=client_ip,
        resource_type="session",
        description=f"Login for '{username}' refused: rate limit exceeded",
        request_method="POST",
        request_path="/api/auth/login",
        response_status=status.HTTP_429_TOO_MANY_REQUESTS,
        success=False,
        error_message="Rate limit exceeded",
    )
    await audit_db.commit()
