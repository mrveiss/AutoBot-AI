# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical user_management core shared by both backends (#12647).

`user_management` is forked across `autobot-backend` and `autobot-slm-backend`,
with 25 shared-but-divergent files. This package is the consolidation target:
files land here once they are identical in both forks, so each move carries no
semantic drift to reconcile.

First mover: `base_service`, which was byte-identical in both and imports
nothing backend-specific. Each fork keeps a re-export shim so existing importers
are untouched — the fork is removed, not the callers.
"""

from autobot_shared.user_management.base_service import (  # noqa: F401
    BaseService,
    TenantContext,
)

__all__ = ["BaseService", "TenantContext"]
