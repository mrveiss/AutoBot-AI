# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One-time exchange codes for the SLM SSO callbacks (#18394).

The OIDC/SAML callbacks used to redirect with the session JWT in the query
string, which reaches access logs, browser history and the Referer header.
They now redirect with an opaque, short-lived, single-use code; the frontend
exchanges it by POST for the token, exactly the body the normal login returns.
The code lives server-side in Redis and is consumed atomically (GETDEL).
"""

import json
import logging
import secrets

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.redis_client import client_getdel, get_redis_client

logger = logging.getLogger(__name__)

SSO_CODE_TTL_SECONDS = env_int_clamped("SLM_SSO_CODE_TTL_SECONDS", 60, min_v=5, max_v=600)
SSO_CODE_KEY_PREFIX = "slm:sso:exchange:"


class ExchangeCodeUnavailableError(Exception):
    """Redis is unreachable; fail closed rather than fall back to a URL token."""


def _client():
    client = get_redis_client(async_client=True, database="main")
    if client is None:
        raise ExchangeCodeUnavailableError("redis unavailable")
    return client


async def issue_exchange_code(token_payload: dict) -> str:
    """Store the minted TokenResponse payload server-side and return the opaque one-time code."""
    code = secrets.token_urlsafe(32)
    payload = json.dumps(token_payload)
    try:
        await _client().set(SSO_CODE_KEY_PREFIX + code, payload, ex=SSO_CODE_TTL_SECONDS)
    except ExchangeCodeUnavailableError:
        raise
    except Exception as e:
        logger.error("SSO exchange code store failed: %s", e)
        raise ExchangeCodeUnavailableError("redis write failed") from e
    return code


async def consume_exchange_code(code: str) -> dict | None:
    """Atomically take the token payload for a code; None if unknown, used or expired."""
    try:
        raw = await client_getdel(_client(), SSO_CODE_KEY_PREFIX + code)
    except ExchangeCodeUnavailableError:
        raise
    except Exception as e:
        logger.error("SSO exchange code read failed: %s", e)
        raise ExchangeCodeUnavailableError("redis read failed") from e
    if raw is None:
        return None
    return json.loads(raw)
