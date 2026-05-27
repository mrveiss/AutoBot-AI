# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RDP Credential Service (Issue #1525)

Manages RDP credentials for xrdp nodes with optional
encrypted password storage.
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Node, NodeCredential
from models.schemas import (
    RDPCredentialCreate,
    RDPCredentialResponse,
    RDPCredentialUpdate,
    RDPEndpointResponse,
)
from services.encryption import encrypt_data

logger = logging.getLogger(__name__)

RDP_DEFAULT_PORT = 3389


class RDPCredentialService:
    """Manage RDP credentials with optional encryption."""

    @staticmethod
    def _generate_credential_id() -> str:
        return secrets.token_hex(16)

    async def create_credential(
        self,
        db: AsyncSession,
        node_id: str,
        data: RDPCredentialCreate,
    ) -> NodeCredential:
        """Create a new RDP credential for a node."""
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = result.scalar_one_or_none()
        if not node:
            raise ValueError(f"Node not found: {node_id}")

        encrypted_password = encrypt_data(data.password) if data.password else None

        # Store auth_method in vnc_type column (generic string field)
        credential = NodeCredential(
            credential_id=self._generate_credential_id(),
            node_id=node_id,
            credential_type="rdp",
            name=data.name,
            encrypted_password=encrypted_password,
            port=data.port,
            vnc_type=data.auth_method,
            websockify_enabled=False,
            is_active=True,
        )

        db.add(credential)
        await db.commit()
        await db.refresh(credential)

        logger.info("Created RDP credential %s for node %s", credential.credential_id, node_id)
        return credential

    async def get_credential(
        self,
        db: AsyncSession,
        credential_id: str,
    ) -> NodeCredential | None:
        """Get an RDP credential by ID."""
        result = await db.execute(
            select(NodeCredential).where(
                NodeCredential.credential_id == credential_id,
                NodeCredential.credential_type == "rdp",
            )
        )
        return result.scalar_one_or_none()

    async def get_node_credentials(
        self,
        db: AsyncSession,
        node_id: str,
        active_only: bool = True,
    ) -> List[NodeCredential]:
        """Get all RDP credentials for a node."""
        query = select(NodeCredential).where(
            NodeCredential.node_id == node_id,
            NodeCredential.credential_type == "rdp",
        )
        if active_only:
            query = query.where(NodeCredential.is_active == True)  # noqa: E712

        result = await db.execute(query)
        return list(result.scalars().all())

    async def update_credential(
        self,
        db: AsyncSession,
        credential_id: str,
        data: RDPCredentialUpdate,
    ) -> NodeCredential | None:
        """Update an RDP credential."""
        credential = await self.get_credential(db, credential_id)
        if not credential:
            return None

        if data.name is not None:
            credential.name = data.name
        if data.port is not None:
            credential.port = data.port
        if data.auth_method is not None:
            credential.vnc_type = data.auth_method
        if data.password is not None:
            credential.encrypted_password = encrypt_data(data.password)
        if data.is_active is not None:
            credential.is_active = data.is_active

        credential.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(credential)

        logger.info("Updated RDP credential %s", credential_id)
        return credential

    async def delete_credential(
        self,
        db: AsyncSession,
        credential_id: str,
    ) -> bool:
        """Delete an RDP credential."""
        credential = await self.get_credential(db, credential_id)
        if not credential:
            return False

        await db.delete(credential)
        await db.commit()

        logger.info("Deleted RDP credential %s", credential_id)
        return True

    async def get_all_rdp_endpoints(
        self,
        db: AsyncSession,
        active_only: bool = True,
    ) -> List[RDPEndpointResponse]:
        """Get all RDP endpoints across the fleet."""
        query = (
            select(NodeCredential, Node)
            .join(Node, NodeCredential.node_id == Node.node_id)
            .where(NodeCredential.credential_type == "rdp")
        )

        if active_only:
            query = query.where(NodeCredential.is_active == True)  # noqa: E712

        result = await db.execute(query)
        rows = result.all()

        return [
            RDPEndpointResponse(
                credential_id=credential.credential_id,
                node_id=credential.node_id,
                hostname=node.hostname,
                ip_address=node.ip_address,
                name=credential.name,
                port=credential.port or RDP_DEFAULT_PORT,
                auth_method=credential.vnc_type or "pam",
                is_active=credential.is_active,
            )
            for credential, node in rows
        ]

    def to_response(self, credential: NodeCredential) -> RDPCredentialResponse:
        """Convert credential to response schema."""
        return RDPCredentialResponse(
            id=credential.id,
            credential_id=credential.credential_id,
            node_id=credential.node_id,
            name=credential.name,
            port=credential.port or RDP_DEFAULT_PORT,
            auth_method=credential.vnc_type or "pam",
            is_active=credential.is_active,
            last_used=credential.last_used,
            created_at=credential.created_at,
            updated_at=credential.updated_at,
        )


# Global service instance
rdp_credential_service = RDPCredentialService()
