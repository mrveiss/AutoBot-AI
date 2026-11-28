# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin trigger: list a node's stale code-sync files and propose their removal for approval (#22033).

    GET  /code-sync/stale-files/{node_id}            read-only listing (path, size, age; kept files and why)
    POST /code-sync/stale-files/{node_id}/proposal   one proposal per old sync location in the approval queue

Mounted on the code-sync router (``api/__init__.py``). Both routes need an administrator's session: the
internal service key reaches the router's gate but carries no user, so ``get_current_user`` refuses it
(owner decision D4: an explicit admin trigger only). Nothing is removed here; a human approves in the
Approvals inbox and the backend's executor calls the SLM's internal removal route.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.schemas_stale_sync_files import (
    KeptFileOut,
    StaleFileOut,
    StaleFilesListing,
    StaleFilesProposalResponse,
    StaleFilesProposed,
)
from services.auth import get_current_user
from services.database import get_db
from services.main_backend_client import MainBackendUnavailable
from services.stale_sync_files import StaleRefused, list_stale_files, propose_cleanup

router = APIRouter(prefix="/stale-files", tags=["code-sync"])


def _actor(user: dict) -> str | None:
    value = user.get("sub") or user.get("username")
    return str(value) if value else None


@router.get("/{node_id}", response_model=StaleFilesListing)
async def get_stale_files(
    node_id: str, _: Annotated[dict, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> StaleFilesListing:
    """The node's stale files, read-only; ``error`` is set when the listing could not be trusted."""
    try:
        listing = await list_stale_files(db, node_id)
    except StaleRefused as refusal:
        raise HTTPException(refusal.status_code, refusal.reason)
    return StaleFilesListing(
        node_id=node_id,
        commit=listing.commit,
        stale=[StaleFileOut(**vars(item)) for item in listing.stale],
        kept=[KeptFileOut(**vars(item)) for item in listing.kept],
        total_stale=len(listing.stale),
        error=listing.error,
    )


@router.post("/{node_id}/proposal", response_model=StaleFilesProposalResponse)
async def propose_stale_files_removal(
    node_id: str, user: Annotated[dict, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]
) -> StaleFilesProposalResponse:
    """Propose removing the node's stale files, one proposal per old sync location; 503 when the backend is down."""
    try:
        proposals = await propose_cleanup(db, node_id, _actor(user))
    except StaleRefused as refusal:
        raise HTTPException(refusal.status_code, refusal.reason)
    except MainBackendUnavailable as unavailable:
        raise HTTPException(unavailable.status_code, unavailable.detail)
    return StaleFilesProposalResponse(node_id=node_id, proposals=[StaleFilesProposed(**item) for item in proposals])
