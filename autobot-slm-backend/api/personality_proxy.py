# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Personality API Proxy

Proxies personality profile requests to the main AutoBot backend.
Validates SLM admin JWT for mutating operations.

The main backend personality API lives at /api/personality/* on 172.16.168.20:8443.
This proxy authenticates via X-Internal-API-Key so the main backend can trust
requests originating from the SLM admin without requiring a main-backend JWT.

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

router = APIRouter(prefix="/personality", tags=["personality-proxy"])

AUTOBOT_BACKEND_URL = os.getenv("AUTOBOT_BACKEND_URL", "https://172.16.168.20:8443")
AUTOBOT_INTERNAL_API_KEY = os.getenv("AUTOBOT_INTERNAL_API_KEY", "")

_MUTATION_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
_TIMEOUT = 15.0


async def _proxy_to_main_backend(request: Request, path: str) -> Response:
    """Forward request to the main backend personality API with internal key."""
    if not AUTOBOT_INTERNAL_API_KEY:
        logger.error(
            "AUTOBOT_INTERNAL_API_KEY not configured — personality proxy unavailable"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Personality service not configured (missing internal API key)",
        )

    body = await request.body()
    content_type = request.headers.get("Content-Type", "application/json")
    target_url = f"{AUTOBOT_BACKEND_URL}/api/personality/{path}"

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
async def personality_proxy(
    path: str,
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> Response:
    """Proxy personality API calls to the main backend.

    Requires SLM admin for mutating methods (POST/PUT/DELETE/PATCH).
    All authenticated SLM users may call read methods (GET).
    """
    if request.method in _MUTATION_METHODS and not current_user.get("admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privilege required",
        )

    return await _proxy_to_main_backend(request, path)


@router.api_route(
    "/",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    include_in_schema=False,
)
async def personality_proxy_root(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> Response:
    """Handle root /personality/ path (e.g. /personality/toggle)."""
    if request.method in _MUTATION_METHODS and not current_user.get("admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privilege required",
        )

    return await _proxy_to_main_backend(request, "")
