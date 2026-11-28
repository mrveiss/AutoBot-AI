# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""User Management Middleware for SLM"""

from user_management.middleware.rbac_middleware import (
    RBACMiddleware,
    rbac_middleware,
    require_all_permissions,
)

__all__ = [
    "RBACMiddleware",
    "rbac_middleware",
    "require_all_permissions",
]
