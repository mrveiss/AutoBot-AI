# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Management Middleware

Middleware components for authentication and authorization.
"""

from backend.user_management.middleware.rbac_middleware import (
    RBACMiddleware,
    require_all_permissions,
    require_any_permission,
    require_permission,
)

__all__ = [
    "RBACMiddleware",
    "require_permission",
    "require_any_permission",
    "require_all_permissions",
]
