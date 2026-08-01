# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — the implementation now lives in autobot_shared (#12647).

This file was byte-identical in both backends, so it moved with no
reconciliation needed — see
``autobot_shared/user_management/models/team.py``. Kept as a shim, not
deleted, so every existing ``from user_management.models.team import ...``
importer keeps working unchanged.
"""

from autobot_shared.user_management.models.team import (  # noqa: F401
    Team,
    TeamMembership,
    TeamRole,
)

__all__ = ["Team", "TeamMembership", "TeamRole"]
