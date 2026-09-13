# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response model for POST /runs/{run_id}/jwt/refresh (``api/run_jwt_router.py``).

Moved here unchanged from the router, where it was a local definition: the
no-local-schemas hook (#6056) blocks any edit of a router file that still defines
its own ``BaseModel`` (#16375).
"""

from pydantic import BaseModel


class RunJwtRefreshResponse(BaseModel):
    token: str
    expires_in: int
