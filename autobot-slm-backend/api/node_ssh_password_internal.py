# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Internal route: delete one node's stored SSH password once the backend's approval queue approved it (#20046).

Only the backend calls this, with ``X-Internal-API-Key``, after a human approved the proposal (#17038).
It takes a node id and an approval id, removes only that node's stored SSH password fields, and refuses
unless the backend confirms the approval is a human's, for this node, and unused (the key alone proves a
service, not a decision).
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.auth.internal_api_key import require_internal_api_key
from models.schemas_node_ssh_password import NodeSshPasswordDeleteResponse
from services.database import get_db
from services.node_ssh_password import DeletionRefused, delete_stored_password

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/internal/nodes", tags=["internal"], dependencies=[Depends(require_internal_api_key)])


@router.delete("/{node_id}/ssh-password", response_model=NodeSshPasswordDeleteResponse)
async def delete_node_ssh_password(
    node_id: str, approval_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> NodeSshPasswordDeleteResponse:
    """Delete the node's stored SSH password under a human's approval; ``deleted`` is False when it held none."""
    try:
        deleted = await delete_stored_password(db, node_id, approval_id)
    except DeletionRefused as refusal:
        logger.warning("Stored SSH password deletion for node %s refused: %s", node_id, refusal.reason)
        raise HTTPException(refusal.status_code, refusal.reason)
    return NodeSshPasswordDeleteResponse(node_id=node_id, deleted=deleted)
