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

from fastapi import APIRouter, Depends, Request

from auth_middleware import get_auth_middleware
from services.scheduler_registry import REGISTRY
from utils.catalog_http_exceptions import raise_auth_error

router = APIRouter(prefix="/admin")


def _require_admin(request: Request) -> bool:
    """Dependency: reject non-admin callers."""
    user_data = get_auth_middleware().get_user_from_request(request)
    if not user_data:
        raise_auth_error("AUTH_0002", "Authentication required")
    if user_data.get("role") != "admin":
        raise_auth_error("AUTH_0003", "Admin permission required")
    return True


@router.get("/schedulers")
async def list_schedulers(_admin: bool = Depends(_require_admin)) -> dict:
    """Return all registered background schedulers with their runtime metadata."""
    return {
        "count": len(REGISTRY),
        "schedulers": [asdict(job) for job in REGISTRY],
    }
