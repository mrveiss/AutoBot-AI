# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What ``POST /auth/refresh`` checks before it mints a token from an old one (#827, #20443).

A refresh accepts a token up to ``REFRESH_GRACE_SECONDS`` past its ``exp`` and returns a fresh one, so
a token that stays refreshable would renew for ever. The password-epoch marker revokes it, but a
marker can be lost (store outage while writing it, eviction), so the account itself is checked
too: a deactivated or deleted user cannot refresh, whatever the marker says.
"""

import datetime
from typing import Dict

from fastapi import HTTPException

from auth_middleware import get_auth_middleware
from autobot_shared.auth.jwt_core import JWTDecodeError, _peek_alg, decode_jwt_no_verify_exp
from autobot_shared.auth.revocation_unavailable import revocation_unavailable_error
from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.login_eligibility import login_refusal
from autobot_shared.user_management.password_epoch import REFRESH_GRACE_SECONDS
from constants.error_constants import ERR_INVALID_TOKEN
from user_management.database import db_session_context
from user_management.services.user_service import UserService

logger = get_logger(__name__)


def decode_refresh_token(token: str) -> Dict:
    """Decode JWT for refresh, allowing recently expired tokens (``REFRESH_GRACE_SECONDS``).

    Helper for refresh_token (#827).
    Accepts both RS256 (new) and HS256 (legacy) tokens (#10196).
    """
    mw = get_auth_middleware()
    try:
        if _peek_alg(token) == "RS256":  # nosec B105  # JWT algorithm identifier, not a credential
            payload = decode_jwt_no_verify_exp(token, public_key=mw.jwt_public_key, algorithms=["RS256"])
        else:
            payload = decode_jwt_no_verify_exp(token, secret=mw.jwt_secret, algorithms=["HS256"])
    except JWTDecodeError as exc:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN) from exc

    exp = payload.get("exp")
    if exp:
        exp_time = datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc)
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        if now > exp_time + datetime.timedelta(seconds=REFRESH_GRACE_SECONDS):
            raise HTTPException(status_code=401, detail="Token expired beyond refresh window")
    return payload


async def reject_if_account_not_live(payload: Dict) -> None:
    """401 unless *payload*'s user exists, is active and is not deleted; 503 when that cannot be read.

    Fails closed: a token that may belong to a closed account is never renewed.
    """
    username = payload.get("username")
    if not username:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)
    try:
        async with db_session_context() as session:
            user = await UserService(session).get_user_by_username(username)
    except Exception as exc:
        logger.error("refresh could not read the account state (%s); denying", type(exc).__name__)
        raise revocation_unavailable_error() from exc
    refusal = login_refusal(user) if user is not None else "account_not_found"
    if refusal:
        logger.warning("refresh refused for subject=%s: %s", username, refusal)
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)
