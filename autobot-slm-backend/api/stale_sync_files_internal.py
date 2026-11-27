# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Internal route: remove a node's stale code-sync files once the backend's approval queue approved it (#22033).

Only the backend calls this, with ``X-Internal-API-Key``, after a human approved the proposal (#17038). The
body carries NO paths: the approved set comes from the claim the SLM makes with the backend, which refuses
unless the approval is a human's, for this node and action, and unused. The key alone proves a service, not
a decision, so it never removes a file by itself.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.auth.internal_api_key import require_internal_api_key
from autobot_shared.logging_manager import get_logger
from models.schemas_stale_sync_files import StaleFileResult, StaleFilesRemovalResponse
from services.database import get_db
from services.main_backend_client import MainBackendUnavailable
from services.stale_sync_files import StaleRefused, remove_approved

logger = get_logger(__name__)

router = APIRouter(prefix="/internal/nodes", tags=["internal"], dependencies=[Depends(require_internal_api_key)])


@router.post("/{node_id}/stale-sync-files/removal", response_model=StaleFilesRemovalResponse)
async def remove_node_stale_sync_files(
    node_id: str, approval_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> StaleFilesRemovalResponse:
    """Remove the approved stale files that are still byte-identical to what git tracked."""
    try:
        results = await remove_approved(db, node_id, str(approval_id))
    except StaleRefused as refusal:
        logger.warning("Stale-file removal for node %s refused: %s", node_id, refusal.reason)
        raise HTTPException(refusal.status_code, refusal.reason)
    except MainBackendUnavailable as unavailable:
        raise HTTPException(unavailable.status_code, unavailable.detail)
    return StaleFilesRemovalResponse(
        node_id=node_id,
        approval_id=str(approval_id),
        removed=sum(row["result"] == "removed" for row in results),
        results=[StaleFileResult(**row) for row in results],
    )
