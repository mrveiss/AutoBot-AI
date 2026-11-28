# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: agent capability-manifest consistency audit (#22271).

Endpoint (admin only, mounted under ``/capability-audit``):
    GET  /capability-audit   run the audit now and return the report
"""

import asyncio

from fastapi import APIRouter, Depends

from auth_middleware import check_admin_permission
from orchestration.capability_audit import run_capability_audit

router = APIRouter(dependencies=[Depends(check_admin_permission)])


@router.get("")
async def get_capability_audit() -> dict:
    """Return the manifest audit report: agent count, error/warning counts and findings."""
    return await asyncio.to_thread(run_capability_audit)
