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

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from autobot_shared import node_proxy
from config import settings
from services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice-proxy"])

# Main backend base URL and internal key, both resolved by the shared node client
# (#14886) so a fourth proxy inherits the same precedence instead of restating it.
# AUTOBOT_BACKEND_URL wins; otherwise the identity-authority base (#10197) keeps
# the proxy working co-located and distributed with no extra config (#10263).
AUTOBOT_BACKEND_URL = node_proxy.resolve_node_url(settings.authority_base_url)
AUTOBOT_INTERNAL_API_KEY = node_proxy.internal_api_key()


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

    # httpx.HTTPError, not ConnectError: a read error or a protocol failure used
    # to escape this proxy as an unhandled 500. The catch-all and its mapping
    # come from the shared client, so all three proxies answer alike (#14886).
    try:
        async with node_proxy.node_client() as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=node_proxy.internal_headers(content_type),
            )
    except httpx.HTTPError as exc:
        failure = node_proxy.classify_transport_error(exc)
        logger.error("Cannot reach main backend at %s (%s)", AUTOBOT_BACKEND_URL, failure.reason)
        raise HTTPException(status_code=failure.status_code, detail=failure.detail)

    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )


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

    return await _proxy_to_main_backend(request, path)
