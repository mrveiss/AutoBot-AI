# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — the implementation now lives in autobot_shared (#12647).

This file's only diff from SLM's copy was cosmetic (an unused ``Optional``
import and ``Mapped[Optional[...]]`` vs ``Mapped["... | None"]`` style) — see
``autobot_shared/user_management/models/role.py`` for the reconciliation
note. Kept as a shim, not deleted, so every existing
``from user_management.models.role import ...`` importer keeps working
unchanged.
"""

from autobot_shared.user_management.models.role import (  # noqa: F401
    SYSTEM_PERMISSIONS,
    SYSTEM_ROLES,
    Permission,
    Role,
    RolePermission,
    UserRole,
)

__all__ = [
    "SYSTEM_PERMISSIONS",
    "SYSTEM_ROLES",
    "Permission",
    "Role",
    "RolePermission",
    "UserRole",
]
