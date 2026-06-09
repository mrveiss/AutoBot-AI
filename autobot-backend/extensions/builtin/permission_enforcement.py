# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backwards-compat shim — canonical implementation is in middleware/builtin/.

The ``extensions`` package was renamed to ``middleware`` (#7426); the builtin
extensions live under ``middleware/builtin/``. This module re-exports the public
API so the legacy ``extensions.builtin.permission_enforcement`` import keeps
working, and removes a full-file duplicate that had drifted only by its base
import (#9779). Remove together with the rest of the extensions→middleware shim.
"""

from middleware.builtin.permission_enforcement import (
    PermissionEnforcementExtension,
    _role_satisfies,
)

__all__ = ["PermissionEnforcementExtension", "_role_satisfies"]
