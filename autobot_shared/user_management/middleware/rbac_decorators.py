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
from typing import Callable, List

from fastapi import HTTPException, Request, status

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


def require_permission(permission: str):
    """
    Decorator to require a specific permission for an endpoint.

    Issue #620: Refactored to use extracted helper functions.

    Usage:
        @router.get("/admin/users")
        @require_permission("users.read")
        async def list_users(request: Request):
            ...

    Args:
        permission: Permission name required
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            # Issue #620: Use extracted helpers
            request = _extract_request(args, request)
            user_id, org_id = _extract_user_context(request)
            _require_authentication(user_id, permission)

            # Check permission
            has_permission = await rbac_middleware.check_permission(user_id, permission, org_id)

            if not has_permission:
                _path, _ip, _ua = _request_audit_context(request)
                await _emit_permission_denied_audit(
                    user_id,
                    permission,
                    _path,
                    org_id=org_id,
                    ip_address=_ip,
                    user_agent=_ua,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission '{permission}' required",
                )

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator


def require_any_permission(permissions: List[str]):
    """
    Decorator to require any of the specified permissions.

    Issue #620: Refactored to use extracted helper functions.

    Usage:
        @router.get("/content")
        @require_any_permission(["content.read", "content.admin"])
        async def get_content(request: Request):
            ...

    Args:
        permissions: List of permission names (any one is sufficient)
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            # Issue #620: Use extracted helpers
            request = _extract_request(args, request)
            user_id, org_id = _extract_user_context(request)
            _require_authentication(user_id, str(permissions))

            has_permission = await rbac_middleware.check_any_permission(user_id, permissions, org_id)

            if not has_permission:
                _path, _ip, _ua = _request_audit_context(request)
                await _emit_permission_denied_audit(
                    user_id,
                    str(permissions),
                    _path,
                    org_id=org_id,
                    ip_address=_ip,
                    user_agent=_ua,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"One of these permissions required: {permissions}",
                )

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator


def require_all_permissions(permissions: List[str]):
    """
    Decorator to require all of the specified permissions.

    Issue #620: Refactored to use extracted helper functions.

    Usage:
        @router.delete("/admin/users/{user_id}")
        @require_all_permissions(["users.read", "users.delete"])
        async def delete_user(request: Request, user_id: str):
            ...

    Args:
        permissions: List of permission names (all are required)
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            # Issue #620: Use extracted helpers
            request = _extract_request(args, request)
            user_id, org_id = _extract_user_context(request)
            _require_authentication(user_id, str(permissions))

            has_permission = await rbac_middleware.check_all_permissions(user_id, permissions, org_id)

            if not has_permission:
                _path, _ip, _ua = _request_audit_context(request)
                await _emit_permission_denied_audit(
                    user_id,
                    str(permissions),
                    _path,
                    org_id=org_id,
                    ip_address=_ip,
                    user_agent=_ua,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"All of these permissions required: {permissions}",
                )

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator
