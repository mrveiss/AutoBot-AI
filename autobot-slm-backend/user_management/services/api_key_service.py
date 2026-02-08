# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
API Key Service

Handles API key creation, validation, and management.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from user_management.models.api_key import APIKey
from user_management.services.base_service import BaseService

logger = logging.getLogger(__name__)


class APIKeyServiceError(Exception):
    """Base exception for API key service errors."""


class APIKeyNotFoundError(APIKeyServiceError):
    """Raised when API key is not found."""


class APIKeyService(BaseService):
    """Service for managing API keys."""

    async def create_key(
        self,
        user_id: uuid.UUID,
        name: str,
        scopes: list,
        description: Optional[str] = None,
        expires_days: Optional[int] = None,
    ) -> tuple:
        """Create a new API key."""
        plaintext_key = self._generate_key()
        key_hash = self._hash_key(plaintext_key)
        key_prefix = plaintext_key[:12]

        expires_at = self._calculate_expiration(expires_days)

        api_key = self._build_api_key(
            user_id, key_hash, key_prefix, name, description, scopes, expires_at
        )

        self.session.add(api_key)
        await self.session.flush()

        return (api_key, plaintext_key)

    async def list_keys(self, user_id: uuid.UUID) -> list:
        """List all API keys for a user."""
        query = (
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_key(self, key_id: uuid.UUID, user_id: uuid.UUID) -> Optional[APIKey]:
        """Get an API key by ID (scoped to user)."""
        query = select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def validate_key(self, plaintext_key: str) -> Optional[APIKey]:
        """Validate an API key and record usage."""
        key_hash = self._hash_key(plaintext_key)

        query = select(APIKey).where(APIKey.key_hash == key_hash)
        result = await self.session.execute(query)
        api_key = result.scalar_one_or_none()

        if not api_key or not api_key.is_valid:
            return None

        api_key.record_usage()
        await self.session.flush()

        return api_key

    async def revoke_key(self, key_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Revoke an API key."""
        api_key = await self.get_key(key_id, user_id)
        if not api_key:
            raise APIKeyNotFoundError("API key not found")

        api_key.revoke(user_id)
        await self.session.flush()
        return True

    async def update_key(
        self,
        key_id: uuid.UUID,
        user_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> APIKey:
        """Update API key metadata."""
        api_key = await self.get_key(key_id, user_id)
        if not api_key:
            raise APIKeyNotFoundError("API key not found")

        if name is not None:
            api_key.name = name
        if description is not None:
            api_key.description = description

        await self.session.flush()
        return api_key

    @staticmethod
    def _generate_key() -> str:
        """Generate a new API key."""
        return "abot_" + secrets.token_hex(20)

    @staticmethod
    def _hash_key(key: str) -> str:
        """Hash an API key using SHA256."""
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _calculate_expiration(expires_days: Optional[int]) -> Optional[datetime]:
        """Calculate expiration datetime."""
        if expires_days is None:
            return None
        return datetime.utcnow() + timedelta(days=expires_days)

    @staticmethod
    def _build_api_key(
        user_id: uuid.UUID,
        key_hash: str,
        key_prefix: str,
        name: str,
        description: Optional[str],
        scopes: list,
        expires_at: Optional[datetime],
    ) -> APIKey:
        """Build APIKey instance."""
        return APIKey(
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            description=description,
            scopes=scopes,
            expires_at=expires_at,
        )
