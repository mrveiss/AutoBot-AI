# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Voice API Proxy

Proxies voice-related requests to the main AutoBot backend.
The main backend voice API requires admin auth (check_admin_permission),
so this proxy authenticates via X-Internal-API-Key — same pattern as
personality_proxy.py.

Related Issue: #1145
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from services.auth import get_current_user
from services.main_backend_client import forward_to_main_backend  # #20760: the one client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice-proxy"])


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    # Opaque passthrough proxy (raw Response, no typed contract); excluded
    # from OpenAPI so the multi-method route does not emit duplicate
    # operationIds (invalid spec / un-typecheckable generated types). #12420
    include_in_schema=False,
)
async def voice_proxy(
    path: str,
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> Response:
    """Proxy voice API calls to the main backend.

    Requires SLM admin authentication. Read-only for non-admin users.
    """
    if request.method != "GET" and not current_user.get("admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privilege required",
        )

    return await forward_to_main_backend(request, f"voice/{path}", "Voice")
