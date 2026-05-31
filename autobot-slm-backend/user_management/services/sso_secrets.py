# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSO Secrets Management Helper

Manages secure storage of SSO credentials (client_secret, bind_password)
using the SystemSecret encrypted storage backend.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import SystemSecret
from services.encryption import decrypt_data, encrypt_data

logger = logging.getLogger(__name__)


class SSOSecretsManager:
    """
    Manages SSO provider secrets using encrypted SystemSecret storage.

    Secrets are stored with keys:
    - sso:provider:{provider_id}:client_secret
    - sso:provider:{provider_id}:bind_password
    """

    SENSITIVE_FIELDS = ["client_secret", "bind_password"]

    def __init__(self, session: AsyncSession):
        self.session = session

    def _get_secret_key(self, provider_id: uuid.UUID, field: str) -> str:
        """Generate SystemSecret key for an SSO provider field."""
        return f"sso:provider:{provider_id}:{field}"

    async def store_secrets(self, provider_id: uuid.UUID, config: dict) -> dict:
        """
        Extract sensitive fields from config, store in SystemSecret, return sanitized config.

        Args:
            provider_id: SSO provider UUID
            config: Provider configuration dictionary

        Returns:
            Sanitized config with secret references instead of plaintext values
        """
        sanitized_config = config.copy()

        for field in self.SENSITIVE_FIELDS:
            value = config.get(field)
            if value:
                secret_key = self._get_secret_key(provider_id, field)

                # Check if secret already exists
                result = await self.session.execute(select(SystemSecret).where(SystemSecret.key == secret_key))
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing secret
                    existing.encrypted_value = encrypt_data(value)
                    logger.info("Updated SSO secret: %s", secret_key)
                else:
                    # Create new secret
                    secret = SystemSecret(
                        key=secret_key,
                        encrypted_value=encrypt_data(value),
                        category="sso",
                        description=f"SSO {field} for provider {provider_id}",
                    )
                    self.session.add(secret)
                    logger.info("Created SSO secret: %s", secret_key)

                # Replace with reference in config
                sanitized_config[f"{field}_ref"] = secret_key
                del sanitized_config[field]

        return sanitized_config

    async def retrieve_secret(self, provider_id: uuid.UUID, field: str) -> str | None:
        """
        Retrieve and decrypt a secret value for an SSO provider.

        Args:
            provider_id: SSO provider UUID
            field: Secret field name (e.g., "client_secret")

        Returns:
            Decrypted secret value or None if not found
        """
        secret_key = self._get_secret_key(provider_id, field)

        result = await self.session.execute(select(SystemSecret).where(SystemSecret.key == secret_key))
        secret = result.scalar_one_or_none()

        if not secret:
            logger.warning("SSO secret not found: %s", secret_key)
            return None

        try:
            return decrypt_data(secret.encrypted_value)
        except Exception as e:
            logger.error("Failed to decrypt SSO secret %s: %s", secret_key, e)
            raise ValueError(f"Failed to decrypt secret {field}") from e

    async def delete_secrets(self, provider_id: uuid.UUID) -> None:
        """
        Delete all secrets for an SSO provider.

        Args:
            provider_id: SSO provider UUID
        """
        for field in self.SENSITIVE_FIELDS:
            secret_key = self._get_secret_key(provider_id, field)

            result = await self.session.execute(select(SystemSecret).where(SystemSecret.key == secret_key))
            secret = result.scalar_one_or_none()

            if secret:
                await self.session.delete(secret)
                logger.info("Deleted SSO secret: %s", secret_key)

    async def has_plaintext_secrets(self, config: dict) -> bool:
        """
        Check if config contains plaintext secrets (not yet migrated).

        Args:
            config: Provider configuration dictionary

        Returns:
            True if plaintext secrets found
        """
        return any(field in config for field in self.SENSITIVE_FIELDS)

    async def migrate_plaintext_to_secrets(self, provider_id: uuid.UUID, config: dict) -> dict:
        """
        Migrate plaintext secrets in config to SystemSecret storage.

        Args:
            provider_id: SSO provider UUID
            config: Provider configuration with plaintext secrets

        Returns:
            Sanitized config with secret references
        """
        if not await self.has_plaintext_secrets(config):
            return config

        logger.info("Migrating plaintext secrets to SystemSecret for provider %s", provider_id)
        return await self.store_secrets(provider_id, config)
