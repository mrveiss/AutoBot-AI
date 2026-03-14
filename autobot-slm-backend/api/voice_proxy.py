# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
from services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice-proxy"])

AUTOBOT_BACKEND_URL = os.getenv(
    "AUTOBOT_BACKEND_URL", "https://172.16.168.20:8443"  # noqa: ssot-fallback
)
AUTOBOT_INTERNAL_API_KEY = os.getenv("AUTOBOT_INTERNAL_API_KEY", "")

_TIMEOUT = 15.0


async def _proxy_to_main_backend(request: Request, path: str) -> Response:
    """Forward request to the main backend voice API with internal key."""
    if not AUTOBOT_INTERNAL_API_KEY:
        logger.error(
            "AUTOBOT_INTERNAL_API_KEY not configured" " — voice proxy unavailable"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice service not configured (missing internal API key)",
        )

    body = await request.body()
    content_type = request.headers.get("Content-Type", "application/json")
    target_url = f"{AUTOBOT_BACKEND_URL}/api/voice/{path}"

    try:
        async with httpx.AsyncClient(
            verify=False, timeout=_TIMEOUT
        ) as client:  # nosec B501 — self-signed internal cert
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
