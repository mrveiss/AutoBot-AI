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

from autobot_shared.env_utils import env_int_clamped
from services.api_key_pepper import (
    HMAC_PEPPER_KEY,
    SECRETS_PAGE_PATH,
    resolve_hmac_api_key_secret,
)
from services.api_key_scheme_clock import (  # noqa: F401
    APIKeyLegacyFormatExpiredError,
    cutoff_passed,
    scheme_active_since,
)
from user_management.models.api_key import APIKey
from user_management.services.base_service import BaseService

logger = logging.getLogger(__name__)


# SUNSET (#16299): this literal was the in-repo default of SLM_HMAC_API_KEY_SECRET
# and is public. It exists ONLY to verify rows hashed before the default was
# removed; it must never hash a new key. Remove once every install has set
# the pepper (secrets page) and its keys have been re-hashed on use or reissued.
_LEGACY_PUBLIC_PEPPER = "autobot-api-key-v1"

#: PBKDF2-HMAC-SHA256 rounds for a stored key digest (#20611). 20000 rounds measured a median of
#: 5.9 ms (p90 9.0 ms) per hash on the development host, inside the 5-10 ms per-verify budget.
PBKDF2_ITERATIONS = env_int_clamped("SLM_API_KEY_PBKDF2_ITERATIONS", 20000, 1000, 10_000_000)


class APIKeyServiceError(Exception):
    """Base exception for API key service errors."""


class APIKeyPepperNotConfiguredError(APIKeyServiceError):
    """The API-key pepper is unset, so a new key cannot be hashed (#19120)."""


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
        pepper = await self._require_pepper()
        plaintext_key = self._generate_key()
        key_hash = self._hash_key(plaintext_key, pepper)
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
        """Validate an API key and record usage (#2083, #16299, #20611).

        Order: PBKDF2 digest -> HMAC under the current secret -> HMAC under the legacy
        public pepper -> bare SHA-256. An old-format match is re-hashed to PBKDF2 in the
        same row when a secret is set, and refused once the cutoff has passed.
        """
        pepper = await resolve_hmac_api_key_secret()
        api_key = None
        if pepper:
            api_key = await self._find_by_hash(self._hash_key(plaintext_key, pepper))
        legacy = api_key is None
        if legacy:
            api_key = await self._find_legacy(plaintext_key, pepper)

        if not api_key or not api_key.is_valid:
            return None
        if legacy and pepper:
            await self._rehash_or_expire(api_key, plaintext_key, pepper)

        api_key.record_usage()
        await self.session.flush()
        return api_key

    async def _find_by_hash(self, key_hash: str) -> APIKey | None:
        query = select(APIKey).where(APIKey.key_hash == key_hash)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _require_pepper(self) -> str:
        """Pepper for a NEW hash, or fail closed (#16299, #19120)."""
        pepper = await resolve_hmac_api_key_secret()
        if not pepper:
            raise APIKeyPepperNotConfiguredError(
                f"API-key pepper is not configured: add the secret '{HMAC_PEPPER_KEY}' on "
                f"the SLM page {SECRETS_PAGE_PATH}. Refusing to hash with a built-in default."
            )
        await scheme_active_since()  # the PBKDF2 scheme is active from the first hash it can make
        return pepper

    async def _find_legacy(self, plaintext_key: str, pepper: str | None) -> APIKey | None:
        """Verify read-only against the old formats (#2083, #16299, #20611)."""
        digests = [self._hash_key_public_pepper(plaintext_key), self._hash_key_legacy(plaintext_key)]
        if pepper:
            digests.insert(0, self._hmac_hex(pepper, plaintext_key))
        for legacy_hash in digests:
            api_key = await self._find_by_hash(legacy_hash)
            if api_key is not None:
                return api_key
        return None

    async def _rehash_or_expire(self, api_key: APIKey, plaintext_key: str, pepper: str) -> None:
        """Re-hash an old-format key to PBKDF2, or refuse it after the cutoff (#20611)."""
        if cutoff_passed(await scheme_active_since()):
            raise APIKeyLegacyFormatExpiredError(api_key.id)
        api_key.key_hash = self._hash_key(plaintext_key, pepper)
        await self.session.flush()
        logger.info("Migrated API key %s to the PBKDF2 hash", api_key.id)

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
    def _hmac_hex(pepper: str, key: str) -> str:
        """HMAC-SHA256 of an API token under *pepper* (lookup digest, not password storage)."""
        return hmac.new(  # HMAC-SHA256 for API token lookup, not password storage
            key=pepper.encode("utf-8"),
            msg=key.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _hash_key(key: str, pepper: str) -> str:
        """Hash an API key: PBKDF2-HMAC-SHA256, the pepper as salt (#1721, #19120, #20611).

        The one place keys are hashed. Deterministic for a given key and pepper, so the
        digest stays a unique lookup value. The legacy pepper is never used here.
        """
        if not pepper:
            raise RuntimeError("API-key pepper is empty: refusing to hash")
        return hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), pepper.encode("utf-8"), PBKDF2_ITERATIONS).hex()

    @staticmethod
    def _hash_key_public_pepper(key: str) -> str:
        """READ-ONLY verifier for rows hashed under the old public pepper (#16299)."""
        return APIKeyService._hmac_hex(_LEGACY_PUBLIC_PEPPER, key)

    @staticmethod
    def _hash_key_legacy(key: str) -> str:
        """Hash using bare SHA-256 (pre-#1721 format, for migration)."""
        # — legacy API token lookup
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
