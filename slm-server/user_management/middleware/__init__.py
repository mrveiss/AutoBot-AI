# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""User Management Middleware for SLM"""

from user_management.middleware.rbac_middleware import (
    RBACMiddleware,
    rbac_middleware,
    require_all_permissions,
    require_any_permission,
    require_permission,
)

__all__ = [
    "RBACMiddleware",
    "rbac_middleware",
    "require_permission",
    "require_any_permission",
    "require_all_permissions",
]
