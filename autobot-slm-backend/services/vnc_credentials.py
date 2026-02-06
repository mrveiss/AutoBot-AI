# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VNC Credential Service

Manages encrypted VNC credentials for nodes with secure
storage and connection token generation.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import Node, NodeCredential
from models.schemas import (
    VNCConnectionInfo,
    VNCCredentialCreate,
    VNCCredentialResponse,
    VNCCredentialUpdate,
    VNCEndpointResponse,
)
from services.encryption import decrypt_data, encrypt_data

logger = logging.getLogger(__name__)


# Connection token cache: {token: (credential_id, expires_at)}
_connection_tokens: Dict[str, Tuple[str, datetime]] = {}


class VNCCredentialService:
    """Manage VNC credentials with encryption."""

    @staticmethod
    def _generate_credential_id() -> str:
        """Generate a unique credential ID."""
        return secrets.token_hex(16)

    @staticmethod
    def _generate_connection_token() -> str:
        """Generate a short-lived connection token."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def _calculate_vnc_port(display_number: int) -> int:
        """Calculate VNC port from display number (5900 + display)."""
        return 5900 + display_number

    async def create_credential(
        self,
        db: AsyncSession,
        node_id: str,
        data: VNCCredentialCreate,
    ) -> NodeCredential:
        """Create a new encrypted VNC credential."""
        # Verify node exists
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = result.scalar_one_or_none()
        if not node:
            raise ValueError(f"Node not found: {node_id}")

        # Get defaults from config
        port = data.port or settings.vnc_default_port
        display_number = data.display_number or settings.vnc_default_display
        vnc_port = data.vnc_port or self._calculate_vnc_port(display_number)

        # Encrypt password
        encrypted_password = encrypt_data(data.password)

        # Encrypt extra data if provided
        encrypted_extra = None
        if data.extra_data:
            encrypted_extra = encrypt_data(data.extra_data)

        credential = NodeCredential(
            credential_id=self._generate_credential_id(),
            node_id=node_id,
            credential_type="vnc",
            name=data.name,
            encrypted_password=encrypted_password,
            encrypted_data=encrypted_extra,
            port=port,
            vnc_type=data.vnc_type,
            display_number=display_number,
            vnc_port=vnc_port,
            websockify_enabled=data.websockify_enabled,
            is_active=True,
        )

        db.add(credential)
        await db.commit()
        await db.refresh(credential)

        logger.info(
            "Created VNC credential %s for node %s",
            credential.credential_id,
            node_id,
        )
        return credential

    async def get_credential(
        self,
        db: AsyncSession,
        credential_id: str,
    ) -> Optional[NodeCredential]:
        """Get a credential by ID (without decrypting password)."""
        result = await db.execute(
            select(NodeCredential).where(
                NodeCredential.credential_id == credential_id,
                NodeCredential.credential_type == "vnc",
            )
        )
        return result.scalar_one_or_none()

    async def get_node_credentials(
        self,
        db: AsyncSession,
        node_id: str,
        active_only: bool = True,
    ) -> List[NodeCredential]:
        """Get all VNC credentials for a node."""
        query = select(NodeCredential).where(
            NodeCredential.node_id == node_id,
            NodeCredential.credential_type == "vnc",
        )
        if active_only:
            query = query.where(NodeCredential.is_active == True)  # noqa: E712

        result = await db.execute(query)
        return list(result.scalars().all())

    async def update_credential(
        self,
        db: AsyncSession,
        credential_id: str,
        data: VNCCredentialUpdate,
    ) -> Optional[NodeCredential]:
        """Update a VNC credential."""
        credential = await self.get_credential(db, credential_id)
        if not credential:
            return None

        # Update fields if provided
        if data.password is not None:
            credential.encrypted_password = encrypt_data(data.password)
        if data.port is not None:
            credential.port = data.port
        if data.display_number is not None:
            credential.display_number = data.display_number
            # Recalculate vnc_port if not explicitly set
            if data.vnc_port is None:
                credential.vnc_port = self._calculate_vnc_port(data.display_number)
        if data.vnc_port is not None:
            credential.vnc_port = data.vnc_port
        if data.websockify_enabled is not None:
            credential.websockify_enabled = data.websockify_enabled
        if data.is_active is not None:
            credential.is_active = data.is_active
        if data.extra_data is not None:
            credential.encrypted_data = encrypt_data(data.extra_data)

        credential.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(credential)

        logger.info("Updated VNC credential %s", credential_id)
        return credential

    async def delete_credential(
        self,
        db: AsyncSession,
        credential_id: str,
    ) -> bool:
        """Delete a VNC credential."""
        credential = await self.get_credential(db, credential_id)
        if not credential:
            return False

        await db.delete(credential)
        await db.commit()

        logger.info("Deleted VNC credential %s", credential_id)
        return True

    async def get_connection_info(
        self,
        db: AsyncSession,
        credential_id: str,
        generate_token: bool = True,
    ) -> Optional[VNCConnectionInfo]:
        """Get connection info with optional temporary token."""
        credential = await self.get_credential(db, credential_id)
        if not credential or not credential.is_active:
            return None

        # Get node for IP address
        result = await db.execute(
            select(Node).where(Node.node_id == credential.node_id)
        )
        node = result.scalar_one_or_none()
        if not node:
            return None

        # Build websocket URL
        websocket_url = f"ws://{node.ip_address}:{credential.port}/websockify"

        # Generate connection token if requested
        connection_token = None
        token_expires_at = None
        if generate_token:
            connection_token = self._generate_connection_token()
            token_expires_at = datetime.utcnow() + timedelta(minutes=5)
            _connection_tokens[connection_token] = (credential_id, token_expires_at)

        # Update last_used timestamp
        credential.last_used = datetime.utcnow()
        await db.commit()

        return VNCConnectionInfo(
            credential_id=credential.credential_id,
            node_id=credential.node_id,
            vnc_type=credential.vnc_type or "desktop",
            host=node.ip_address,
            port=credential.port or settings.vnc_default_port,
            display_number=credential.display_number or settings.vnc_default_display,
            websocket_url=websocket_url,
            connection_token=connection_token,
            token_expires_at=token_expires_at,
        )

    def exchange_token_for_password(self, token: str) -> Optional[str]:
        """Exchange a connection token for the encrypted password (one-time use)."""
        if token not in _connection_tokens:
            return None

        credential_id, expires_at = _connection_tokens.pop(token)

        # Check expiration
        if datetime.utcnow() > expires_at:
            logger.warning("Connection token expired for credential %s", credential_id)
            return None

        return credential_id

    async def get_password_by_token(
        self,
        db: AsyncSession,
        token: str,
    ) -> Optional[str]:
        """Get decrypted password using connection token (one-time use)."""
        credential_id = self.exchange_token_for_password(token)
        if not credential_id:
            return None

        credential = await self.get_credential(db, credential_id)
        if not credential or not credential.encrypted_password:
            return None

        try:
            return decrypt_data(credential.encrypted_password)
        except Exception as e:
            logger.error("Failed to decrypt password for %s: %s", credential_id, e)
            return None

    async def get_all_vnc_endpoints(
        self,
        db: AsyncSession,
        active_only: bool = True,
    ) -> List[VNCEndpointResponse]:
        """Get all VNC endpoints across the fleet."""
        query = (
            select(NodeCredential, Node)
            .join(Node, NodeCredential.node_id == Node.node_id)
            .where(NodeCredential.credential_type == "vnc")
        )

        if active_only:
            query = query.where(NodeCredential.is_active == True)  # noqa: E712

        result = await db.execute(query)
        rows = result.all()

        endpoints = []
        for credential, node in rows:
            port = credential.port or settings.vnc_default_port
            endpoints.append(
                VNCEndpointResponse(
                    credential_id=credential.credential_id,
                    node_id=credential.node_id,
                    hostname=node.hostname,
                    ip_address=node.ip_address,
                    vnc_type=credential.vnc_type or "desktop",
                    name=credential.name,
                    port=port,
                    websocket_url=f"ws://{node.ip_address}:{port}/websockify",
                    is_active=credential.is_active,
                )
            )

        return endpoints

    def to_response(
        self,
        credential: NodeCredential,
        node: Optional[Node] = None,
    ) -> VNCCredentialResponse:
        """Convert credential to response schema."""
        websocket_url = None
        if node and credential.port:
            websocket_url = f"ws://{node.ip_address}:{credential.port}/websockify"

        return VNCCredentialResponse(
            id=credential.id,
            credential_id=credential.credential_id,
            node_id=credential.node_id,
            vnc_type=credential.vnc_type,
            name=credential.name,
            port=credential.port,
            display_number=credential.display_number,
            vnc_port=credential.vnc_port,
            websockify_enabled=credential.websockify_enabled,
            is_active=credential.is_active,
            last_used=credential.last_used,
            created_at=credential.created_at,
            updated_at=credential.updated_at,
            websocket_url=websocket_url,
        )


# Global service instance
vnc_credential_service = VNCCredentialService()
