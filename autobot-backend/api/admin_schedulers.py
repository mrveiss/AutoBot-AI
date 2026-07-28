# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: background scheduler registry endpoint (GH#6594).

Endpoint:
    GET /api/admin/schedulers

Access: admin role required.
"""

from dataclasses import asdict

from fastapi import APIRouter, Depends

from auth_rbac import require_role
from services.scheduler_registry import REGISTRY

router = APIRouter(prefix="/admin")


@router.get("/schedulers")
async def list_schedulers(_admin: bool = Depends(require_role("admin", "superadmin"))) -> dict:
    """Return all registered background schedulers with their runtime metadata."""
    return {
        "count": len(REGISTRY),
        "schedulers": [asdict(job) for job in REGISTRY],
    }
