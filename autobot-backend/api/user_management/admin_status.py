# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Change whether a user is a platform admin (#20670).

``is_platform_admin`` is the one source of admin: it alone decides the ``role`` a login token
carries. The role routes in ``users.py`` write ``UserRole`` permission rows and never reach it,
so this is the only route that makes someone an admin or stops them being one.

The change revokes the user's earlier tokens through the password epoch (#20443), after the
commit, so it applies on their next request; a failed revocation write is answered with 503
(the change stays committed) rather than only logged.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas_admin_status import AdminStatusRequest, AdminStatusResponse
from api.user_management.dependencies import get_user_service, require_platform_admin, user_management_route_marker
from autobot_shared.user_management.revocation_outcome import commit_or_503
from autobot_shared.user_management.user_service_errors import UserNotFoundError
from user_management.services import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.put(
    "/{user_id}/admin",
    response_model=AdminStatusResponse,
    summary="Set platform admin status",
    description=(
        "Make a user a platform admin, or remove that. This is the only route that changes admin "
        "status; the role routes change permissions only. The user's earlier tokens stop working on "
        "their next request, so they sign in again. Admin only. Issue #20670."
    ),
    dependencies=[Depends(user_management_route_marker), Depends(require_platform_admin)],
)
async def set_admin_status(
    user_id: uuid.UUID,
    body: AdminStatusRequest,
    user_service: UserService = Depends(get_user_service),
):
    """Set the user's platform admin status and revoke their earlier tokens."""
    try:
        changed = await user_service.set_platform_admin(user_id, body.is_platform_admin)
    except UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found")
    await commit_or_503(user_service.session)  # a failed revocation is answered, not only logged (#20443)
    return AdminStatusResponse(user_id=user_id, is_platform_admin=body.is_platform_admin, changed=changed)
