# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Role-Based Access Control (RBAC) Permission System for AutoBot API

This module provides fine-grained permission control for API endpoints through
decorators and FastAPI dependencies. It integrates with the existing SecurityLayer
for permission checks and audit logging.

Issue #744: Phase 6 - RBAC permission decorators for API endpoints.
Issue #6511: Permission/Role/ROLE_PERMISSIONS moved to autobot_shared.auth.permissions
             for cross-service consistency.  This module re-exports them so all
             existing callers (``from auth_rbac import Permission``) continue to work.

Usage:
    from auth_rbac import require_permission, require_role, Permission
from autobot_shared.logging_manager import get_logger

    @router.get("/admin/users")
    async def list_users(
        current_user: dict = Depends(get_current_user),
        _: bool = Depends(require_permission(Permission.ADMIN_USERS_READ)),
    ):
        ...

    @router.post("/analytics/export")
    async def export_analytics(
        current_user: dict = Depends(get_current_user),
        _: bool = Depends(require_role("admin", "analyst")),
    ):
        ...
"""

from typing import Callable, List

from fastapi import Request

from auth_middleware import get_auth_middleware
from autobot_shared.auth.permissions import (  # noqa: F401 — re-exported for callers
    ROLE_PERMISSIONS,
    Permission,
    Role,
)
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from security_layer import SecurityLayer
from utils.catalog_http_exceptions import raise_auth_error

logger = get_logger(__name__)

_get_security_layer = lazy_singleton(SecurityLayer)


def _get_user_permissions(user_role: str) -> List[str]:
    """
    Get all permissions for a user role.

    Combines RBAC role permissions with SecurityLayer defaults.

    Args:
        user_role: The user's role string

    Returns:
        List of permission strings the user has
    """
    permissions = []

    # Get RBAC permissions from our mapping
    try:
        role_enum = Role(user_role.lower())
        role_perms = ROLE_PERMISSIONS.get(role_enum, [])
        permissions.extend(
            [p.value if isinstance(p, Permission) else p for p in role_perms]
        )
    except ValueError:
        # Unknown role, check if it's in SecurityLayer defaults
        pass

    # Also get permissions from SecurityLayer (for backward compatibility)
    security_perms = _get_security_layer()._get_default_role_permissions(user_role)
    permissions.extend(security_perms)

    return list(set(permissions))  # Remove duplicates


def has_permission(user_data: dict, permission: Permission | str) -> bool:
    """
    Check if a user has a specific permission.

    Args:
        user_data: User data dict with 'role' key
        permission: The permission to check (Permission enum or string)

    Returns:
        True if user has the permission, False otherwise
    """
    if not user_data:
        return False

    user_role = user_data.get("role", "")
    if not user_role:
        return False

    # Convert Permission enum to string if needed
    perm_str = permission.value if isinstance(permission, Permission) else permission

    # Check using SecurityLayer for audit logging
    return _get_security_layer().check_permission(user_role, perm_str)


def _check_single_user_bypass(permission: Permission | str) -> bool:
    """
    Check if single-user mode bypass should apply. Issue #620.

    Args:
        permission: The permission being checked

    Returns:
        True if bypass applies, False otherwise
    """
    from user_management.config import DeploymentMode, get_deployment_config

    deployment_config = get_deployment_config()
    if deployment_config.mode == DeploymentMode.SINGLE_USER:
        logger.debug(
            "Single user mode: bypassing permission check for %s",
            permission,
        )
        return True
    return False


def _deny_permission_access(user_data: dict, perm_str: str, request: Request) -> None:
    """
    Log denied access and raise auth error. Issue #620.

    Args:
        user_data: User data dict
        perm_str: Permission string
        request: FastAPI request object

    Raises:
        HTTPException via raise_auth_error
    """
    _get_security_layer().audit_log(
        action="permission_denied",
        user=user_data.get("username", "unknown"),
        outcome="denied",
        details={
            "permission_required": perm_str,
            "user_role": user_data.get("role"),
            "endpoint": str(request.url.path),
        },
    )
    raise_auth_error(
        "AUTH_0003",
        f"Permission '{perm_str}' required for this operation",
    )


def require_permission(
    permission: Permission | str,
    allow_single_user_bypass: bool = True,
) -> Callable:
    """
    FastAPI dependency that requires a specific permission.

    Usage:
        @router.get("/endpoint")
        async def endpoint(
            current_user: dict = Depends(get_current_user),
            _: bool = Depends(require_permission(Permission.ANALYTICS_VIEW)),
        ):
            ...

    Args:
        permission: The required permission
        allow_single_user_bypass: If True, bypass check in single-user mode

    Returns:
        FastAPI dependency function

    Issue #744: RBAC permission decorator for API endpoints.
    """

    def dependency(request: Request) -> bool:
        """Check permission and return True or raise error."""
        if allow_single_user_bypass and _check_single_user_bypass(permission):
            return True

        user_data = get_auth_middleware().get_user_from_request(request)
        if not user_data:
            raise_auth_error("AUTH_0002", "Authentication required")

        perm_str = (
            permission.value if isinstance(permission, Permission) else permission
        )
        if not has_permission(user_data, permission):
            _deny_permission_access(user_data, perm_str, request)

        return True

    return dependency


def _deny_role_access(
    user_data: dict, allowed_roles: List[str], user_role: str, request: Request
) -> None:
    """
    Log denied role access and raise auth error. Issue #620.

    Args:
        user_data: User data dict
        allowed_roles: List of allowed role strings
        user_role: User's actual role
        request: FastAPI request object

    Raises:
        HTTPException via raise_auth_error
    """
    _get_security_layer().audit_log(
        action="role_denied",
        user=user_data.get("username", "unknown"),
        outcome="denied",
        details={
            "roles_required": allowed_roles,
            "user_role": user_role,
            "endpoint": str(request.url.path),
        },
    )
    raise_auth_error(
        "AUTH_0003",
        f"One of roles {allowed_roles} required for this operation",
    )


def _deny_any_permission_access(
    user_data: dict, perm_strs: List[str], request: Request
) -> None:
    """
    Log denied permission access when none of required permissions match. Issue #620.

    Args:
        user_data: User data dict
        perm_strs: List of permission strings that were required
        request: FastAPI request object

    Raises:
        HTTPException via raise_auth_error
    """
    _get_security_layer().audit_log(
        action="permission_denied",
        user=user_data.get("username", "unknown"),
        outcome="denied",
        details={
            "permissions_required_any": perm_strs,
            "user_role": user_data.get("role"),
            "endpoint": str(request.url.path),
        },
    )
    raise_auth_error(
        "AUTH_0003",
        f"One of permissions {perm_strs} required for this operation",
    )


def require_role(*roles: Role | str, allow_single_user_bypass: bool = True) -> Callable:
    """
    FastAPI dependency that requires one of the specified roles.

    Usage:
        @router.get("/admin/users")
        async def list_users(
            current_user: dict = Depends(get_current_user),
            _: bool = Depends(require_role(Role.ADMIN, Role.OPERATOR)),
        ):
            ...

    Args:
        *roles: The allowed roles
        allow_single_user_bypass: If True, bypass check in single-user mode

    Returns:
        FastAPI dependency function

    Issue #744: RBAC role decorator for API endpoints.
    """

    def dependency(request: Request) -> bool:
        """Check role and return True or raise error."""
        if allow_single_user_bypass and _check_single_user_bypass("role_check"):
            return True

        user_data = get_auth_middleware().get_user_from_request(request)
        if not user_data:
            raise_auth_error("AUTH_0002", "Authentication required")

        user_role = user_data.get("role", "").lower()
        allowed_roles = [r.value if isinstance(r, Role) else r.lower() for r in roles]

        if user_role not in allowed_roles:
            _deny_role_access(user_data, allowed_roles, user_role, request)

        return True

    return dependency


def require_any_permission(
    *permissions: Permission | str,
    allow_single_user_bypass: bool = True,
) -> Callable:
    """
    FastAPI dependency that requires ANY of the specified permissions.

    Usage:
        @router.get("/endpoint")
        async def endpoint(
            current_user: dict = Depends(get_current_user),
            _: bool = Depends(require_any_permission(
                Permission.ANALYTICS_VIEW,
                Permission.ADMIN_SYSTEM
            )),
        ):
            ...

    Args:
        *permissions: The permissions (user needs at least one)
        allow_single_user_bypass: If True, bypass check in single-user mode

    Returns:
        FastAPI dependency function
    """

    def dependency(request: Request) -> bool:
        """Check at least one permission and return True or raise error."""
        if allow_single_user_bypass and _check_single_user_bypass("any_permission"):
            return True

        user_data = get_auth_middleware().get_user_from_request(request)
        if not user_data:
            raise_auth_error("AUTH_0002", "Authentication required")

        for perm in permissions:
            if has_permission(user_data, perm):
                return True

        perm_strs = [p.value if isinstance(p, Permission) else p for p in permissions]
        _deny_any_permission_access(user_data, perm_strs, request)

    return dependency


# Convenience functions for common permission checks
def check_analytics_permission(request: Request) -> bool:
    """Dependency for analytics endpoints. Issue #744."""
    return require_permission(Permission.ANALYTICS_VIEW)(request)


def check_analytics_admin_permission(request: Request) -> bool:
    """Dependency for analytics admin endpoints. Issue #744."""
    return require_permission(Permission.ANALYTICS_MANAGE)(request)


def check_knowledge_read_permission(request: Request) -> bool:
    """Dependency for knowledge read endpoints. Issue #744."""
    return require_permission(Permission.KNOWLEDGE_READ)(request)


def check_knowledge_write_permission(request: Request) -> bool:
    """Dependency for knowledge write endpoints. Issue #744."""
    return require_permission(Permission.KNOWLEDGE_WRITE)(request)


def check_agent_execute_permission(request: Request) -> bool:
    """Dependency for agent execution endpoints. Issue #744."""
    return require_permission(Permission.AGENT_EXECUTE)(request)


def check_shell_execute_permission(request: Request) -> bool:
    """Dependency for shell execution (dangerous). Issue #744."""
    return require_permission(Permission.SHELL_EXECUTE, allow_single_user_bypass=False)(
        request
    )
