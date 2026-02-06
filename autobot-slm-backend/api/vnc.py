# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VNC API Routes

Endpoints for managing VNC credentials and connections.
Related to Issue #725.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Node
from models.schemas import (
    VNCConnectionInfo,
    VNCCredentialCreate,
    VNCCredentialListResponse,
    VNCCredentialResponse,
    VNCCredentialUpdate,
    VNCEndpointsResponse,
)
from services.auth import get_current_user
from services.database import get_db
from services.vnc_credentials import vnc_credential_service

logger = logging.getLogger(__name__)

# Router for VNC credential management under nodes
node_vnc_router = APIRouter(prefix="/nodes", tags=["vnc-credentials"])

# Router for VNC-specific operations
vnc_router = APIRouter(prefix="/vnc", tags=["vnc"])


# =============================================================================
# Node VNC Credential Endpoints
# =============================================================================


@node_vnc_router.post(
    "/{node_id}/vnc-credentials",
    response_model=VNCCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_vnc_credential(
    node_id: str,
    data: VNCCredentialCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> VNCCredentialResponse:
    """Create a VNC credential for a node."""
    try:
        credential = await vnc_credential_service.create_credential(db, node_id, data)

        # Get node for websocket URL
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = result.scalar_one_or_none()

        return vnc_credential_service.to_response(credential, node)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Failed to create VNC credential: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create VNC credential",
        )


@node_vnc_router.get(
    "/{node_id}/vnc-credentials",
    response_model=VNCCredentialListResponse,
)
async def list_node_vnc_credentials(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    include_inactive: bool = Query(False),
) -> VNCCredentialListResponse:
    """List VNC credentials for a node."""
    # Verify node exists
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    credentials = await vnc_credential_service.get_node_credentials(
        db, node_id, active_only=not include_inactive
    )

    return VNCCredentialListResponse(
        credentials=[vnc_credential_service.to_response(c, node) for c in credentials],
        total=len(credentials),
    )


# =============================================================================
# VNC Credential Management Endpoints
# =============================================================================


@vnc_router.get(
    "/credentials/{credential_id}",
    response_model=VNCCredentialResponse,
)
async def get_vnc_credential(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> VNCCredentialResponse:
    """Get a VNC credential by ID (excludes password)."""
    credential = await vnc_credential_service.get_credential(db, credential_id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )

    # Get node for websocket URL
    result = await db.execute(select(Node).where(Node.node_id == credential.node_id))
    node = result.scalar_one_or_none()

    return vnc_credential_service.to_response(credential, node)


@vnc_router.patch(
    "/credentials/{credential_id}",
    response_model=VNCCredentialResponse,
)
async def update_vnc_credential(
    credential_id: str,
    data: VNCCredentialUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> VNCCredentialResponse:
    """Update a VNC credential."""
    credential = await vnc_credential_service.update_credential(db, credential_id, data)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )

    # Get node for websocket URL
    result = await db.execute(select(Node).where(Node.node_id == credential.node_id))
    node = result.scalar_one_or_none()

    return vnc_credential_service.to_response(credential, node)


@vnc_router.delete(
    "/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_vnc_credential(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Delete a VNC credential."""
    deleted = await vnc_credential_service.delete_credential(db, credential_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )


# =============================================================================
# VNC Connection Endpoints
# =============================================================================


@vnc_router.post(
    "/credentials/{credential_id}/connect",
    response_model=VNCConnectionInfo,
)
async def get_vnc_connection_info(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> VNCConnectionInfo:
    """Get VNC connection info with a short-lived token for password retrieval."""
    connection_info = await vnc_credential_service.get_connection_info(
        db, credential_id, generate_token=True
    )
    if not connection_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found or inactive",
        )

    return connection_info


@vnc_router.post("/exchange-token")
async def exchange_connection_token(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Exchange a connection token for the VNC password (one-time use)."""
    password = await vnc_credential_service.get_password_by_token(db, token)
    if not password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return {"password": password}


# =============================================================================
# Fleet-wide VNC Endpoints
# =============================================================================


@vnc_router.get("/endpoints", response_model=VNCEndpointsResponse)
async def list_vnc_endpoints(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    include_inactive: bool = Query(False),
) -> VNCEndpointsResponse:
    """List all VNC endpoints across the fleet."""
    endpoints = await vnc_credential_service.get_all_vnc_endpoints(
        db, active_only=not include_inactive
    )

    return VNCEndpointsResponse(
        endpoints=endpoints,
        total=len(endpoints),
    )
