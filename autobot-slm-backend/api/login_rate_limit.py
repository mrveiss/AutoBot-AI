# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rate limit for ``POST /api/auth/login`` (#19832, the SLM API is now on the main origin).

Two buckets, both checked on every attempt: one per client IP (a single source guessing many
names) and one per username (many sources guessing one name). They are separate keys of the
shared ``RateLimiter`` that ``api/sso_auth.py`` uses, so a bucket for one username never blocks
another and neither blocks a different IP. The limits are the shared limiter's ``anonymous``
tier, read from the SSOT config (``rate_limit_anon_rpm`` / ``rate_limit_anon_rph``) -- this
module carries no numbers of its own. A refusal is audited as a failed ``auth.login``, as a bad
password is.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.security import create_audit_log
from autobot_shared.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_ip_limiter = RateLimiter(scope_prefix="slm_login_ip", default_tier="anonymous")
_username_limiter = RateLimiter(scope_prefix="slm_login_user", default_tier="anonymous")


async def retry_after_if_refused(
    client_ip: str | None,
    username: str,
    *,
    ip_limiter: RateLimiter = _ip_limiter,
    username_limiter: RateLimiter = _username_limiter,
) -> int | None:
    """Return the seconds to wait when this attempt is over a limit, else ``None``.

    Both buckets are always charged, so an attacker cannot probe one bucket for free by
    exhausting the other first.
    """
    ip_key = f"ip:{client_ip or 'unknown'}"
    user_key = f"username:{username.strip().lower()}"
    ip_ok = await ip_limiter.acquire(ip_key)
    user_ok = await username_limiter.acquire(user_key)
    if ip_ok and user_ok:
        return None
    waits = []
    if not ip_ok:
        waits.append(await ip_limiter.get_retry_after_seconds(ip_key))
    if not user_ok:
        waits.append(await username_limiter.get_retry_after_seconds(user_key))
    return max(waits)


async def enforce_login_rate_limit(
    audit_db: AsyncSession,
    client_ip: str | None,
    username: str,
    **limiters: RateLimiter,
) -> None:
    """Raise 429 (with ``Retry-After``) and audit the refusal when the attempt is over a limit."""
    retry_after = await retry_after_if_refused(client_ip, username, **limiters)
    if retry_after is None:
        return
    logger.warning("Login rate limit exceeded", extra={"retry_after": retry_after})
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
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Please try again later.",
        headers={"Retry-After": str(retry_after)},
    )
