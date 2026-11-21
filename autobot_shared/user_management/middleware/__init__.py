# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared RBAC middleware — one implementation for both services (#18088)."""

from autobot_shared.user_management.middleware.rbac_decorators import (  # noqa: F401
    require_all_permissions,
    require_any_permission,
    require_permission,
)
from autobot_shared.user_management.middleware.rbac_middleware import (  # noqa: F401
    RBACDependencies,
    RBACMiddleware,
    RBACNotConfiguredError,
    configure_rbac,
)
