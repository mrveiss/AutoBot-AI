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
import os
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from config import settings
from services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice-proxy"])

# Main backend base URL. Reuse the identity-authority base (#10197) so the proxy
# works co-located (loopback:8001) and distributed with no extra config (#10263);
# an explicit AUTOBOT_BACKEND_URL still overrides if set.
AUTOBOT_BACKEND_URL = os.getenv("AUTOBOT_BACKEND_URL", "") or settings.authority_base_url  # noqa: ssot-fallback
AUTOBOT_INTERNAL_API_KEY = os.getenv("AUTOBOT_INTERNAL_API_KEY", "")

_TIMEOUT = 15.0
# TLS verification for proxy calls to the main backend.
# Set AUTOBOT_SKIP_TLS_VERIFY=true ONLY in dev/test with self-signed certs (#2852).
_VERIFY_TLS = os.environ.get("AUTOBOT_SKIP_TLS_VERIFY", "").lower() != "true"


async def _proxy_to_main_backend(request: Request, path: str) -> Response:
    """Forward request to the main backend voice API with internal key."""
    if not AUTOBOT_INTERNAL_API_KEY:
        logger.error("AUTOBOT_INTERNAL_API_KEY not configured" " — voice proxy unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice service not configured (missing internal API key)",
        )

    body = await request.body()
    content_type = request.headers.get("Content-Type", "application/json")
    target_url = f"{AUTOBOT_BACKEND_URL}/api/voice/{path}"

    try:
        async with httpx.AsyncClient(verify=_VERIFY_TLS, timeout=_TIMEOUT) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers={
                    "Content-Type": content_type,
                    "X-Internal-API-Key": AUTOBOT_INTERNAL_API_KEY,
                },
            )
    except httpx.ConnectError:
        logger.error("Cannot reach main backend at %s", AUTOBOT_BACKEND_URL)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Main backend unreachable",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Main backend timeout",
        )

    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
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

    return await _proxy_to_main_backend(request, path)
