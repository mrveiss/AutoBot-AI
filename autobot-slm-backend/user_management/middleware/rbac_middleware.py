# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RBAC middleware — re-export of the one shared implementation (#18088).

This module held a 594-line copy. Its twin in the other service was byte-identical apart
from two comments describing the same audit-swallowing bug under different issue numbers,
which is #6511's warning in practice: "divergent permission logic across two services
that interoperate is a security drift risk."

The implementation now lives in `autobot_shared.user_management.middleware.rbac_middleware`.
This file stays as the import path every call site already uses, matching the shim pattern
already used for `base_service`, `organization_service` and `team_service`.

`rbac_middleware` and `_permission_cache` are re-exported deliberately: call sites import
both (`api/secrets.py`, `api/envelope_secrets.py`, `user_management/services/user_service.py`),
and `_permission_cache` crosses the module boundary despite the underscore. Re-exporting the
singleton keeps one instance per process, which is what the cache invalidation depends on.
"""

from autobot_shared.user_management.middleware.rbac_middleware import (  # noqa: F401
    CACHE_TTL_SECONDS,
    RBACMiddleware,
    _permission_cache,
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
    "CACHE_TTL_SECONDS",
]
