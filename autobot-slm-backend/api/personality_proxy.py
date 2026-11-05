# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Personality API Proxy

Proxies personality profile requests to the main AutoBot backend.
Validates SLM admin JWT for mutating operations.

The main backend personality API lives at /api/personality/* on the main backend server.
This proxy authenticates via X-Internal-API-Key so the main backend can trust
requests originating from the SLM admin without requiring a main-backend JWT.

Related Issue: #1145
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from services.auth import get_current_user
from services.main_backend_client import forward_to_main_backend  # #20760: the one client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/personality", tags=["personality-proxy"])

_MUTATION_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


# The root "/" handler is declared FIRST: Starlette tries routes in registration order and
# "{path:path}" matches the empty string, so declared the other way round the root handler never ran (#17325).
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

    return await forward_to_main_backend(request, "personality/", "Personality")


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    # Opaque passthrough proxy (raw Response, no typed contract); excluded
    # from OpenAPI so the multi-method route does not emit duplicate
    # operationIds (invalid spec / un-typecheckable generated types). #12420
    include_in_schema=False,
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

    return await forward_to_main_backend(request, f"personality/{path}", "Personality")
