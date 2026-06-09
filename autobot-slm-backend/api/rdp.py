# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
RDP API Routes (Issue #1525)

Endpoints for managing RDP credentials for xrdp nodes.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Node
from models.schemas import (
    RDPCredentialCreate,
    RDPCredentialListResponse,
    RDPCredentialResponse,
    RDPCredentialUpdate,
    RDPEndpointsResponse,
)
from services.auth import get_current_user
from services.database import get_db
from services.rdp_credentials import rdp_credential_service

logger = logging.getLogger(__name__)

node_rdp_router = APIRouter(prefix="/nodes", tags=["rdp-credentials"])
rdp_router = APIRouter(prefix="/rdp", tags=["rdp"])


# =============================================================================
# Node RDP Credential Endpoints
# =============================================================================


@node_rdp_router.post(
    "/{node_id}/rdp-credentials",
    response_model=RDPCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rdp_credential(
    node_id: str,
    data: RDPCredentialCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RDPCredentialResponse:
    """Create an RDP credential for a node."""
    try:
        credential = await rdp_credential_service.create_credential(db, node_id, data)
        return rdp_credential_service.to_response(credential)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    except Exception as e:
        logger.error("Failed to create RDP credential: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create RDP credential",
        )


@node_rdp_router.get(
    "/{node_id}/rdp-credentials",
    response_model=RDPCredentialListResponse,
)
async def list_node_rdp_credentials(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    include_inactive: bool = Query(False),
) -> RDPCredentialListResponse:
    """List RDP credentials for a node."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    credentials = await rdp_credential_service.get_node_credentials(db, node_id, active_only=not include_inactive)

    return RDPCredentialListResponse(
        credentials=[rdp_credential_service.to_response(c) for c in credentials],
        total=len(credentials),
    )


# =============================================================================
# RDP Credential Management Endpoints
# =============================================================================


@rdp_router.get(
    "/credentials/{credential_id}",
    response_model=RDPCredentialResponse,
)
async def get_rdp_credential(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RDPCredentialResponse:
    """Get an RDP credential by ID."""
    credential = await rdp_credential_service.get_credential(db, credential_id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )
    return rdp_credential_service.to_response(credential)


@rdp_router.patch(
    "/credentials/{credential_id}",
    response_model=RDPCredentialResponse,
)
async def update_rdp_credential(
    credential_id: str,
    data: RDPCredentialUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RDPCredentialResponse:
    """Update an RDP credential."""
    credential = await rdp_credential_service.update_credential(db, credential_id, data)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )
    return rdp_credential_service.to_response(credential)


@rdp_router.delete(
    "/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_rdp_credential(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Delete an RDP credential."""
    deleted = await rdp_credential_service.delete_credential(db, credential_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )


# =============================================================================
# Fleet-wide RDP Endpoints
# =============================================================================


@rdp_router.get("/endpoints", response_model=RDPEndpointsResponse)
async def list_rdp_endpoints(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    include_inactive: bool = Query(False),
) -> RDPEndpointsResponse:
    """List all RDP endpoints across the fleet."""
    endpoints = await rdp_credential_service.get_all_rdp_endpoints(db, active_only=not include_inactive)
    return RDPEndpointsResponse(endpoints=endpoints, total=len(endpoints))
