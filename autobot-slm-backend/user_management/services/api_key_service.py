# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
API Key Service

Handles API key creation, validation, and management.
"""

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from config import settings
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
        description: str | None = None,
        expires_days: int | None = None,
    ) -> tuple:
        """Create a new API key."""
        plaintext_key = self._generate_key()
        key_hash = self._hash_key(plaintext_key)
        key_prefix = plaintext_key[:12]

        expires_at = self._calculate_expiration(expires_days)

        api_key = self._build_api_key(user_id, key_hash, key_prefix, name, description, scopes, expires_at)

        self.session.add(api_key)
        await self.session.flush()

        return (api_key, plaintext_key)

    async def list_keys(self, user_id: uuid.UUID) -> list:
        """List all API keys for a user."""
        query = select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_key(self, key_id: uuid.UUID, user_id: uuid.UUID) -> APIKey | None:
        """Get an API key by ID (scoped to user)."""
        query = select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def validate_key(self, plaintext_key: str) -> APIKey | None:
        """Validate an API key and record usage (#2083).

        Tries HMAC-SHA256 hash first; falls back to legacy SHA-256 for
        pre-#1721 keys and re-hashes them in place so future lookups
        use the stronger algorithm.
        """
        key_hash = self._hash_key(plaintext_key)
        query = select(APIKey).where(APIKey.key_hash == key_hash)
        result = await self.session.execute(query)
        api_key = result.scalar_one_or_none()

        if api_key is None:
            api_key = await self._try_legacy_hash(plaintext_key)

        if not api_key or not api_key.is_valid:
            return None

        api_key.record_usage()
        await self.session.flush()
        return api_key

    async def _try_legacy_hash(self, plaintext_key: str) -> APIKey | None:
        """Check legacy SHA-256 hash and migrate to HMAC (#2083)."""
        legacy_hash = self._hash_key_legacy(plaintext_key)
        query = select(APIKey).where(APIKey.key_hash == legacy_hash)
        result = await self.session.execute(query)
        api_key = result.scalar_one_or_none()
        if api_key is not None:
            api_key.key_hash = self._hash_key(plaintext_key)
            await self.session.flush()
            logger.info("Migrated API key %s to HMAC-SHA256", api_key.id)
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
        name: str | None = None,
        description: str | None = None,
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
        """Hash an API key using HMAC-SHA256 (#1721, #2083, #2160).

        The signing key is read from SLM_HMAC_API_KEY_SECRET (default:
        "autobot-api-key-v1" for backward compatibility with existing hashes).
        """
        return (
            hmac.new(  # codeql[py/weak-sensitive-data-hashing] HMAC-SHA256 for API token lookup, not password storage
                key=settings.hmac_api_key_secret.encode("utf-8"),
                msg=key.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).hexdigest()
        )

    @staticmethod
    def _hash_key_legacy(key: str) -> str:
        """Hash using bare SHA-256 (pre-#1721 format, for migration)."""
        # codeql[py/weak-sensitive-data-hashing] — legacy API token lookup
        # hash retained for migration only, NOT used for password storage.
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _calculate_expiration(expires_days: int | None) -> datetime | None:
        """Calculate expiration datetime."""
        if expires_days is None:
            return None
        return datetime.now(timezone.utc) + timedelta(days=expires_days)

    @staticmethod
    def _build_api_key(
        user_id: uuid.UUID,
        key_hash: str,
        key_prefix: str,
        name: str,
        description: str | None,
        scopes: list,
        expires_at: datetime | None,
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
