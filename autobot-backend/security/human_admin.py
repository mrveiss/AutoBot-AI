# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Destructive admin routes are for human admins only (owner decision 2026-10-18, #18688).

The canonical admin gate (``auth_middleware.check_admin_permission``) admits the internal
service key as an admin, which is right for the routes the SLM reads. Stopping the shared
Redis or deleting audit evidence is an operator action, so those routes refuse the key
before the admin gate runs; a human admin's own credentials still pass.
"""

from fastapi import Depends, HTTPException, Request, status

import auth_middleware
from autobot_shared.auth.permissions import Role, is_admin_role
from autobot_shared.node_proxy import INTERNAL_KEY_HEADER
from utils.catalog_http_exceptions import raise_auth_error

SERVICE_PRINCIPAL_REFUSED = "Service credentials cannot perform this destructive operation"


def refuse_service_principal(request: Request) -> None:
    """403 when the request authenticates with the internal service key."""
    # Looked up on the module at call time, so it is the same check the admin gate makes.
    if auth_middleware.verify_internal_api_key(request.headers.get(INTERNAL_KEY_HEADER)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=SERVICE_PRINCIPAL_REFUSED)


#: Human-admin-only routes: the service key is refused before the admin check (#18688).
#: The one definition; route modules import it rather than rebuilding the pair.
HUMAN_ADMIN_DEPENDENCIES = [Depends(refuse_service_principal), Depends(auth_middleware.check_admin_permission)]


async def require_human_operator(request: Request) -> dict:
    """The human operator or admin behind a destructive route; the service key is refused (#18688).

    Built on ``resolve_human_user``, so a JWT minted before a password change is 401 and an
    epoch store that cannot answer is 503. Returns the resolved user for the audit trail.
    """
    refuse_service_principal(request)
    user_data = await auth_middleware.resolve_human_user(request)
    if not user_data:
        raise_auth_error("AUTH_0002")
    role = user_data.get("role")
    if not role:
        raise_auth_error("AUTH_0002", "User role not assigned - access denied")
    if not (is_admin_role(role) or str(role).lower() == Role.OPERATOR.value):
        raise_auth_error("AUTH_0003", "Admin or operator role required for this operation")
    return user_data
