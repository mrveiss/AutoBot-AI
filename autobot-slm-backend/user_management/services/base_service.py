# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — the implementation now lives in autobot_shared (#12647).

This file was byte-identical in both backends, so it was the safe first move in
#12645's user_management de-fork: no drift to reconcile, and nothing here is
backend-specific. Kept as a shim rather than deleted so the 12 existing
importers keep working unchanged; the fork is what goes, not the callers.
"""

from autobot_shared.user_management.base_service import (  # noqa: F401
    BaseService,
    TenantContext,
)

__all__ = ["BaseService", "TenantContext"]
