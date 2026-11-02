# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Internal route: delete one node's stored SSH password once the backend's approval queue approved it (#20046).

Only the backend calls this, with ``X-Internal-API-Key``, after a human approved the proposal (#17038).
It takes a node id and nothing else, and removes only that node's stored SSH password fields.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.auth.internal_api_key import verify_internal_api_key
from models.schemas_node_ssh_password import NodeSshPasswordDeleteResponse
from services.database import get_db
from services.node_ssh_password import delete_stored_password

logger = logging.getLogger(__name__)


async def require_internal_key(
    x_internal_api_key: Annotated[str | None, Header(alias="X-Internal-API-Key")] = None,
) -> None:
    """Refuse every caller without the internal key; a user token is not enough."""
    if not verify_internal_api_key(x_internal_api_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "internal service key required")


router = APIRouter(prefix="/internal/nodes", tags=["internal"], dependencies=[Depends(require_internal_key)])


@router.delete("/{node_id}/ssh-password", response_model=NodeSshPasswordDeleteResponse)
async def delete_node_ssh_password(
    node_id: str, db: Annotated[AsyncSession, Depends(get_db)]
) -> NodeSshPasswordDeleteResponse:
    """Delete the node's stored SSH password; ``deleted`` is False when it held none."""
    deleted = await delete_stored_password(db, node_id)
    if deleted is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Node not found")
    return NodeSshPasswordDeleteResponse(node_id=node_id, deleted=deleted)
