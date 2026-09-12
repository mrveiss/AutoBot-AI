# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend's password-change revocation gate (#12924), failing closed (#16411).

A token minted before its subject's password changed is refused. When the
check reaches no verdict -- the epoch store cannot answer (#16411), or the
marker or the token's ``iat`` cannot be read (#16422) -- the token is refused
with the same 401: a token that may be revoked is never honoured, which is the
rule the SLM follows (#16387). The owner accepted the cost on 2026-09-12 -- a
Redis outage takes backend login down with it.
"""

from typing import Dict

from fastapi import HTTPException, status

from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.password_epoch import (
    RevocationCheckUnavailable,
    is_token_revoked_by_password_change,
)

logger = get_logger(__name__)

_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


async def reject_if_revoked_by_password_change(user_data: Dict) -> None:
    """Raise a 401 unless the password-epoch check clears *user_data*'s token."""
    try:
        revoked = await is_token_revoked_by_password_change(user_data)
    except RevocationCheckUnavailable as exc:
        # The check and the helper's fixed reason only -- never the token, its
        # claims or a stored value (#16411, #16422).
        logger.error("password-epoch revocation check reached no verdict (%s); denying the token", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token could not be verified. Please sign in again.",
            headers=_BEARER_CHALLENGE,
        ) from exc
    if revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is no longer valid — password was changed. Please sign in again.",
            headers=_BEARER_CHALLENGE,
        )
