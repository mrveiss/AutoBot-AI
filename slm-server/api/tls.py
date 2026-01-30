# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
TLS Certificate API Routes (Issue #725)

Endpoints for managing TLS certificates for mTLS authentication.
Certificates are stored encrypted and served to Ansible for deployment.
"""

import logging
from typing import Optional

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Node
from models.schemas import (
    TLSCredentialCreate,
    TLSCredentialListResponse,
    TLSCredentialResponse,
    TLSCredentialUpdate,
    TLSEndpointsResponse,
    TLSCertificateInfo,
)
from services.auth import get_current_user
from services.database import get_db
from services.tls_credentials import get_tls_credential_service

logger = logging.getLogger(__name__)

# Router for TLS credential management under nodes
node_tls_router = APIRouter(prefix="/nodes", tags=["tls-credentials"])

# Router for TLS-specific operations
tls_router = APIRouter(prefix="/tls", tags=["tls"])


def _to_response(credential, include_certs: bool = False) -> TLSCredentialResponse:
    """Convert NodeCredential to TLSCredentialResponse."""
    response = TLSCredentialResponse(
        id=credential.id,
        credential_id=credential.credential_id,
        node_id=credential.node_id,
        name=credential.name,
        common_name=credential.tls_common_name,
        expires_at=credential.tls_expires_at,
        fingerprint=credential.tls_fingerprint,
        is_active=credential.is_active,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )
    return response


# =============================================================================
# Node TLS Credential Endpoints
# =============================================================================


@node_tls_router.post(
    "/{node_id}/tls-credentials",
    response_model=TLSCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tls_credential(
    node_id: str,
    data: TLSCredentialCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> TLSCredentialResponse:
    """Create a TLS credential for a node.

    Stores CA certificate, server certificate, and private key (encrypted).
    """
    service = get_tls_credential_service()
    try:
        credential = await service.create_credential(db, node_id, data)
        return _to_response(credential)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Failed to create TLS credential: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create TLS credential",
        )


@node_tls_router.get(
    "/{node_id}/tls-credentials",
    response_model=TLSCredentialListResponse,
)
async def list_node_tls_credentials(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    include_inactive: bool = Query(False),
) -> TLSCredentialListResponse:
    """List TLS credentials for a node."""
    # Verify node exists
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    service = get_tls_credential_service()
    credentials = await service.get_node_credentials(db, node_id)

    if not include_inactive:
        credentials = [c for c in credentials if c.is_active]

    return TLSCredentialListResponse(
        credentials=[_to_response(c) for c in credentials],
        total=len(credentials),
    )


# =============================================================================
# TLS Credential Operations
# =============================================================================


@tls_router.get(
    "/credentials/{credential_id}",
    response_model=TLSCredentialResponse,
)
async def get_tls_credential(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> TLSCredentialResponse:
    """Get a TLS credential (without private key)."""
    service = get_tls_credential_service()
    credential = await service.get_credential(db, credential_id)

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    return _to_response(credential)


@tls_router.patch(
    "/credentials/{credential_id}",
    response_model=TLSCredentialResponse,
)
async def update_tls_credential(
    credential_id: str,
    data: TLSCredentialUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> TLSCredentialResponse:
    """Update a TLS credential."""
    service = get_tls_credential_service()
    credential = await service.update_credential(db, credential_id, data)

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    return _to_response(credential)


@tls_router.delete(
    "/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_tls_credential(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Delete a TLS credential."""
    service = get_tls_credential_service()
    deleted = await service.delete_credential(db, credential_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )


# =============================================================================
# Certificate Download Endpoints (for Ansible)
# =============================================================================


@tls_router.get(
    "/credentials/{credential_id}/ca-cert",
    response_class=PlainTextResponse,
)
async def get_ca_certificate(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> str:
    """Get CA certificate (PEM format) for deployment."""
    service = get_tls_credential_service()
    certs = await service.get_certificates(db, credential_id)

    if not certs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    return certs.get("ca_cert", "")


@tls_router.get(
    "/credentials/{credential_id}/server-cert",
    response_class=PlainTextResponse,
)
async def get_server_certificate(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> str:
    """Get server certificate (PEM format) for deployment."""
    service = get_tls_credential_service()
    certs = await service.get_certificates(db, credential_id)

    if not certs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    return certs.get("server_cert", "")


@tls_router.get(
    "/credentials/{credential_id}/server-key",
    response_class=PlainTextResponse,
)
async def get_server_key(
    credential_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> str:
    """Get server private key (PEM format) for deployment.

    WARNING: This endpoint returns sensitive data. Use with care.
    """
    service = get_tls_credential_service()
    certs = await service.get_certificates(db, credential_id)

    if not certs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TLS credential not found",
        )

    return certs.get("server_key", "")


# =============================================================================
# Fleet-wide TLS Endpoints
# =============================================================================


@tls_router.get(
    "/endpoints",
    response_model=TLSEndpointsResponse,
)
async def list_tls_endpoints(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    include_inactive: bool = Query(False),
) -> TLSEndpointsResponse:
    """List all TLS endpoints across the fleet."""
    service = get_tls_credential_service()
    endpoints = await service.get_all_tls_endpoints(
        db, active_only=not include_inactive
    )

    # Count certificates expiring within 30 days
    expiring_soon = sum(
        1 for e in endpoints
        if e.days_until_expiry is not None and e.days_until_expiry <= 30
    )

    return TLSEndpointsResponse(
        endpoints=endpoints,
        total=len(endpoints),
        expiring_soon=expiring_soon,
    )


@tls_router.get(
    "/expiring",
    response_model=TLSEndpointsResponse,
)
async def list_expiring_certificates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    days: int = Query(30, ge=1, le=365),
) -> TLSEndpointsResponse:
    """List certificates expiring within the specified days."""
    service = get_tls_credential_service()
    credentials = await service.get_expiring_certificates(db, days)

    # Convert to endpoint responses
    endpoints = []
    for cred in credentials:
        result = await db.execute(
            select(Node).where(Node.node_id == cred.node_id)
        )
        node = result.scalar_one_or_none()
        if node:
            from datetime import datetime
            days_until = None
            if cred.tls_expires_at:
                delta = cred.tls_expires_at - datetime.utcnow()
                days_until = delta.days

            endpoints.append(
                TLSEndpointResponse(
                    credential_id=cred.credential_id,
                    node_id=cred.node_id,
                    hostname=node.hostname,
                    ip_address=node.ip_address,
                    name=cred.name,
                    common_name=cred.tls_common_name,
                    expires_at=cred.tls_expires_at,
                    is_active=cred.is_active,
                    days_until_expiry=days_until,
                )
            )

    return TLSEndpointsResponse(
        endpoints=endpoints,
        total=len(endpoints),
        expiring_soon=len(endpoints),
    )
