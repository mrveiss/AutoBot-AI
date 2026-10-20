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

from typing import Dict

from fastapi import HTTPException, status

from autobot_shared.auth.revocation_unavailable import revocation_unavailable_error
from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.password_epoch import (
    MalformedTokenClaims,
    RevocationCheckUnavailable,
    is_token_revoked_by_password_change,
)

logger = get_logger(__name__)

_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


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
