# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — the implementation now lives in autobot_shared (#12647).

`team_service.py` was byte-identical across both backends (701 lines), so a
fix had to be applied twice or it reached only one service. It is the first
`user_management` service that could move: `Team`/`TeamMembership`, the audit
vocabulary and `BaseService`/`TenantContext` are all already shared, and it
references `User`/`Organization` only in docstrings — never as classes.

Kept as a shim, not deleted, so every existing
`from user_management.services.team_service import ...` importer keeps working
unchanged.
"""

from autobot_shared.user_management.team_service import (  # noqa: F401
    DuplicateTeamError,
    MembershipError,
    TeamNotFoundError,
    TeamService,
    TeamServiceError,
)

__all__ = [
    "TeamService",
    "TeamServiceError",
    "TeamNotFoundError",
    "DuplicateTeamError",
    "MembershipError",
]
