# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend's password-change revocation gate (#12924), failing closed (#16411).

A token minted before its subject's password changed is refused. When the
check reaches no verdict -- the epoch store cannot answer (#16411), or the
marker or the token's ``iat`` cannot be read (#16422) -- the token is refused
(fail closed): a token that may be revoked is never honoured, which is the
rule the SLM follows (#16387). The answer is a 503 + Retry-After (#18892), not a
401, so the client keeps a valid session and retries; 401 stays for a revoked token.
The owner accepted the cost on 2026-09-12 -- a Redis outage takes backend login down with it.
"""

import time
from typing import Dict

from fastapi import HTTPException, Request, status

from autobot_shared.auth.revocation_unavailable import revocation_unavailable_error
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import parse_utc_iso
from autobot_shared.user_management.password_epoch import (
    LOGIN_TOKEN_LIFETIME_SECONDS,
    MalformedTokenClaims,
    RevocationCheckUnavailable,
    is_token_revoked_by_password_change,
)

logger = get_logger(__name__)

_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}

#: Credentials the epoch can place in time: a JWT by its ``iat``, an ``X-Session-ID`` session by its creation (#20443).
_EPOCH_GATED_METHODS = ("jwt", "session")


async def reject_if_revoked_by_password_change(user_data: Dict) -> None:
    """Raise a 503 (check cannot run) or 401 (revoked) unless the password-epoch check clears *user_data*'s token."""
    try:
        revoked = await is_token_revoked_by_password_change(user_data)
    except MalformedTokenClaims as exc:
        # #18892: the token's own claim is unreadable -- a bad credential; retrying cannot fix it.
        logger.warning("password-epoch check refused a token with unreadable claims (%s)", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers=_BEARER_CHALLENGE,
        ) from exc
    except RevocationCheckUnavailable as exc:
        # The check and the helper's fixed reason only -- never the token, its
        # claims or a stored value (#16411, #16422).
        logger.error("password-epoch revocation check reached no verdict (%s); denying the token", exc)
        raise revocation_unavailable_error() from exc
    if revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is no longer valid — password was changed. Please sign in again.",
            headers=_BEARER_CHALLENGE,
        )


async def revoked_by_password_change_for_introspection(claims: Dict) -> bool:
    """Whether *claims* (a token being inspected, not the caller) predate its subject's password change.

    Introspection reports the verdict instead of refusing the request: revoked and unreadable
    claims are ``True``; a check that cannot run is the same 503 as every other gate (#18688).
    """
    try:
        return await is_token_revoked_by_password_change(claims)
    except MalformedTokenClaims:
        return True
    except RevocationCheckUnavailable as exc:
        logger.error("password-epoch introspection reached no verdict (%s); denying", exc)
        raise revocation_unavailable_error() from exc


async def token_passes_revocation(token_data: Dict) -> bool:
    """False when the password-epoch check refuses the token or cannot run (fail closed); for non-HTTP callers."""
    try:
        await reject_if_revoked_by_password_change(token_data)
    except HTTPException:
        return False
    return True


async def resolve_human_user_via(middleware, request: Request) -> Dict | None:
    """The human *middleware* (its own signing key) resolves from *request*, or None (#18688, #19061).

    A device JWT is a 403 (GH#9493); a pre-password-change JWT is 401 and an epoch store that cannot answer
    is 503. ``auth_middleware.resolve_human_user`` binds this to the singleton for existing callers.
    """
    user_data = middleware.get_user_from_request(request)
    if not user_data:
        return None
    if user_data.get("auth_method") == "device_jwt":  # device JWTs: see get_current_user (GH#9493)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device tokens not permitted on this endpoint. Use mobile-specific API.",
        )
    if user_data.get("auth_method") in _EPOCH_GATED_METHODS:  # #12924, #16411: minted before a password change: void
        await reject_if_revoked_by_password_change(user_data)
    return user_data


def with_session_issue_time(user_data: Dict, session: Dict) -> Dict | None:
    """*user_data* with the session's creation time as ``iat``, so the password-epoch gate covers it (#20443).

    A session whose creation time cannot be read cannot be placed against an epoch: None, refused.
    So is one older than a login token's lifetime: ``get_session`` extends the TTL on every use, so
    polling would otherwise keep a session alive past the epoch marker, which is kept for a token's
    lifetime plus a margin, and the voided session would be admitted again once the marker expired.
    """
    try:
        user_data["iat"] = int(parse_utc_iso(session["created_at"]).timestamp())
    except (KeyError, TypeError, ValueError):
        logger.warning("Session refused: its creation time is unreadable")
        return None
    if time.time() - user_data["iat"] > LOGIN_TOKEN_LIFETIME_SECONDS:
        logger.info("Session refused: it is older than a login's lifetime")
        return None
    user_data["sub"] = user_data.get("sub") or user_data.get("username")
    return user_data
