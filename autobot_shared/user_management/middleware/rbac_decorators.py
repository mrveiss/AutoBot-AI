# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RBAC permission decorators (#18088).

Split from `rbac_middleware` to keep each module under the file-size ceiling. These
decorators reach the one process-wide `rbac_middleware` singleton, which refuses to run
until a service has injected its dependencies (`configure_rbac`), so a decorated endpoint
can never silently allow or deny on an unconfigured middleware.
"""

import uuid
from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request, status

from autobot_shared.auth.permission_evaluator import require_permission_member
from autobot_shared.auth.permissions import Permission
from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.middleware.rbac_middleware import (
    _emit_permission_denied_audit,
    _request_audit_context,
    rbac_middleware,
)

logger = get_logger(__name__)


def _extract_request(args: tuple, request: Request | None) -> Request:
    """
    Extract Request object from function arguments.

    Issue #620: Extracted from permission decorators to reduce duplication.

    Args:
        args: Positional arguments
        request: Request from kwargs (may be None)

    Returns:
        Request object

    Raises:
        HTTPException: 500 if Request not found
    """
    if request is None:
        for arg in args:
            if isinstance(arg, Request):
                return arg

    if request is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request object not found",
        )
    return request


def _extract_user_context(
    request: Request,
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """
    Extract user_id and org_id from request state.

    Issue #620: Extracted from permission decorators to reduce duplication.

    Args:
        request: FastAPI Request object

    Returns:
        Tuple of (user_id, org_id), either may be None
    """
    user_id = None
    org_id = None

    if hasattr(request.state, "user"):
        user_data = request.state.user
        if "user_id" in user_data:
            try:
                user_id = uuid.UUID(user_data["user_id"])
            except (ValueError, TypeError):
                pass
        if "org_id" in user_data:
            try:
                org_id = uuid.UUID(user_data["org_id"])
            except (ValueError, TypeError):
                pass

    return user_id, org_id


def _require_authentication(user_id: uuid.UUID | None, permissions_desc: str) -> None:
    """
    Check that user is authenticated, raise 401 if not.

    Issue #620: Extracted from permission decorators to reduce duplication.
    Issue #744: Return 401 for unauthenticated users.

    Args:
        user_id: User UUID (None if not authenticated)
        permissions_desc: Description of required permissions for logging

    Raises:
        HTTPException: 401 if user_id is None
    """
    if user_id is None:
        logger.warning("Authentication required for permission: %s", permissions_desc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


async def _deny_all(request: Request, user_id, org_id, names: list[str]) -> None:
    """Audit and raise 403 for a failed all-permissions check."""
    _path, _ip, _ua = _request_audit_context(request)
    await _emit_permission_denied_audit(
        user_id,
        str(names),
        _path,
        org_id=org_id,
        ip_address=_ip,
        user_agent=_ua,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"All of these permissions required: {names}",
    )


async def _enforce_all(request: Request, names: list[str]) -> None:
    """Require authentication and every permission in ``names`` (401/403 otherwise)."""
    user_id, org_id = _extract_user_context(request)
    _require_authentication(user_id, str(names))
    if not await rbac_middleware.check_all_permissions(user_id, names, org_id):
        await _deny_all(request, user_id, org_id, names)


def require_all_permissions(*permissions: Permission):
    """
    Require all of the specified ``Permission`` members (#18088).

    A string raises ``TypeError`` at build time (import time for a route module). The one
    gate definition is ``autobot_shared.auth.permission_gate``.

    Usage: ``@require_all_permissions(Permission.ADMIN_USERS_READ, Permission.ADMIN_USERS_WRITE)``
    """
    if not permissions:
        raise ValueError("require_all_permissions needs at least one Permission")
    for permission in permissions:
        require_permission_member(permission)
    names = [permission.value for permission in permissions]

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            request = _extract_request(args, request)
            await _enforce_all(request, names)

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator
