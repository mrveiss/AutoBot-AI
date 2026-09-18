# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: list orphan-storage candidates across every registered detector (#17038, #17039).

Endpoints:
    GET /api/admin/orphan-storage   preview candidates -- read-only

Access: admin/superadmin (``require_role``). This is preview only, on purpose:
deletion is never exposed as a bare admin-gated route here, because the owner's
rule requires every removal to go through a human-approved review queue
(#17043) -- this module has no delete endpoint until that lands, and won't
gain one that bypasses it afterwards either.
"""

from fastapi import APIRouter, Depends

from api.codebase_analytics.orphan_clone_detector import register as register_code_source_clone_detector
from api.schemas_orphan_storage import OrphanStorageCandidateResponse, OrphanStorageListResponse
from auth_rbac import require_role
from services.orphan_storage import list_all_candidates

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin", "superadmin"))])

# Registered here, at this router's own import time (once, at app startup),
# rather than as a side effect of importing orphan_clone_detector itself --
# so a test that imports that module for its functions doesn't also mutate
# the global registry. register_detector() is idempotent regardless.
register_code_source_clone_detector()


@router.get("/orphan-storage", response_model=OrphanStorageListResponse)
async def list_orphan_storage() -> OrphanStorageListResponse:
    """Every orphan-storage candidate, across every registered detector."""
    candidates = await list_all_candidates()
    return OrphanStorageListResponse(
        candidates=[OrphanStorageCandidateResponse(**vars(c)) for c in candidates],
        total_count=len(candidates),
        total_size_bytes=sum(c.size_bytes for c in candidates),
    )
