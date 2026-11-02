# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one constant-time check of the trusted internal-service API key (#17312).

Shared by autobot-backend ``auth_middleware`` (#1145) and autobot-slm-backend
``services.auth`` (#11450); both re-export ``verify_internal_api_key`` so the
name stays importable (and patchable) from each service.
"""

import secrets

from fastapi import Header, HTTPException, status

from autobot_shared import node_proxy


def verify_internal_api_key(provided: str | None) -> bool:
    """Constant-time check of the trusted internal-service API key.

    True only when the key (``node_proxy.internal_api_key()``, its one reader,
    #17856) is configured AND ``provided`` matches it exactly;
    ``secrets.compare_digest`` blocks timing inference; a missing header never
    matches.
    """
    expected = node_proxy.internal_api_key()
    if not expected or not provided:
        return False
    return secrets.compare_digest(provided, expected)


async def require_internal_api_key(x_internal_api_key: str | None = Header(None, alias="X-Internal-API-Key")) -> None:
    """FastAPI dependency: only a holder of the internal service key passes; a user token is refused (#20046)."""
    if not verify_internal_api_key(x_internal_api_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "internal service key required")
