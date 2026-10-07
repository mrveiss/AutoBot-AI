# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim for the canonical RBAC middleware (#18088).

The implementation lives in ``autobot_shared.middleware.rbac_middleware``. Both
backends used to carry byte-identical 595-line copies of it against the same
``audit_logs`` table, which is how a permission could be enforced by one service
and not the other (#6511). This module keeps the historical import path working
while there is exactly one implementation.

PATCH TARGETS BELONG ON THE CANONICAL MODULE, NOT HERE. Patching an attribute on
a shim rebinds the shim's name; the code under test reads the canonical module's,
so the patch would silently do nothing. ``rbac_shim_identity_test.py`` pins that
both paths resolve to the same objects.
"""

from autobot_shared.middleware.rbac_middleware import (  # noqa: F401
    CACHE_TTL_SECONDS,
    RBACMiddleware,
    _permission_cache,
    get_async_redis_client,
    rbac_middleware,
    require_all_permissions,
    require_any_permission,
    require_permission,
)

__all__ = [
    "CACHE_TTL_SECONDS",
    "RBACMiddleware",
    "rbac_middleware",
    "require_all_permissions",
    "require_any_permission",
    "require_permission",
]
