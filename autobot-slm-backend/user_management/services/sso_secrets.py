# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSO secrets management via the unified-secrets System vault (#10153).

The SLM Manager is a *client* of the autobot-backend unified-secrets API.
Secrets are stored in the **System vault** via HMAC-authenticated HTTP calls
(``unified_vault_client``), replacing the previous SLM-local ``SystemSecret``
table as the canonical store.

Backward-compatible read path
------------------------------
During rollout (before migration runs) the vault may not yet hold a secret.
``retrieve_secret`` falls back to the legacy ``SystemSecret`` table when the
vault lookup returns ``UnifiedVaultSecretNotFound``.  Once ``migrate_to_vault``
has been run the fallback never fires.

Secret naming in the vault
---------------------------
Each SSO provider field maps to a vault secret whose ``name`` is the canonical
key used by the legacy store:

    ``sso:provider:{provider_id}:{field}``

The vault ``secret_id`` (UUID) is stashed in the provider's sanitized config as
``{field}_vault_id`` so that subsequent reads and rotations can address the
secret directly without an expensive list-then-filter round-trip.

Never log secret values.  Never expose them in exception messages.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Sensitive fields extracted from provider config before persistence.
SENSITIVE_FIELDS: list[str] = ["client_secret", "bind_password"]

# Vault secret type label stored with each secret entry.
_SECRET_TYPE = "sso-credential"


def _vault_name(provider_id: uuid.UUID, field: str) -> str:
    """Canonical vault secret name — mirrors the legacy SystemSecret key."""
    return f"sso:provider:{provider_id}:{field}"


def _vault_id_config_key(field: str) -> str:
    """Config key where the vault secret UUID is cached."""
    return f"{field}_vault_id"


async def _legacy_retrieve(session: AsyncSession, provider_id: uuid.UUID, field: str) -> str | None:
    """Read from the legacy SystemSecret table (fallback during migration window)."""
    try:
        from models.database import SystemSecret
        from services.encryption import decrypt_data

        key = _vault_name(provider_id, field)
        result = await session.execute(select(SystemSecret).where(SystemSecret.key == key))
        secret = result.scalar_one_or_none()
        if secret is None:
            return None
        return decrypt_data(secret.encrypted_value)
    except Exception as exc:
        logger.warning("legacy SSO secret fallback failed for field %s: %s", field, type(exc).__name__)
        return None


async def _legacy_store(session: AsyncSession, provider_id: uuid.UUID, config: dict) -> dict:
    """Write sensitive fields to the legacy SystemSecret table (rollout window).

    Used when the unified vault is not yet configured so existing deployments
    keep working unchanged until ``SLM_SERVICE_KEY`` is provisioned.
    """
    from models.database import SystemSecret
    from services.encryption import encrypt_data

    sanitized = config.copy()
    for field in SENSITIVE_FIELDS:
        value = config.get(field)
        if not value:
            continue
        key = _vault_name(provider_id, field)
        result = await session.execute(select(SystemSecret).where(SystemSecret.key == key))
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.encrypted_value = encrypt_data(value)
        else:
            session.add(
                SystemSecret(
                    key=key,
                    encrypted_value=encrypt_data(value),
                    category="sso",
                    description=f"SSO {field} for provider {provider_id}",
                )
            )
        sanitized[f"{field}_ref"] = key
        sanitized.pop(field, None)
    return sanitized


class SSOSecretsManager:
    """Manage SSO provider secrets via the unified-secrets System vault.

    Constructed with an ``AsyncSession`` for the legacy fallback read path only.
    The primary store is the unified vault (HTTP); the session is never used
    for vault writes.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Public interface (same surface as before — sso_service.py unchanged)
    # ------------------------------------------------------------------

    async def store_secrets(self, provider_id: uuid.UUID, config: dict) -> dict:
        """Extract sensitive fields from config, write to vault, return sanitized config.

        Sanitized config gains ``{field}_vault_id`` (UUID str) and
        ``{field}_ref`` (vault name) in place of the plaintext value.
        Idempotent: updates the vault secret when ``{field}_vault_id`` is
        already present in config (or when a vault entry with that name exists).
        """
        from user_management.services.unified_vault_client import (
            UnifiedVaultClientError,
            is_configured,
            vault_create,
            vault_rotate,
        )

        # Rollout fallback: until the vault service key is provisioned, behave
        # exactly as before and write to the legacy SystemSecret store.
        if not is_configured():
            return await _legacy_store(self._session, provider_id, config)

        sanitized = config.copy()
        for field in SENSITIVE_FIELDS:
            value = config.get(field)
            if not value:
                continue
            name = _vault_name(provider_id, field)
            existing_vault_id_str = config.get(_vault_id_config_key(field))
            try:
                if existing_vault_id_str:
                    existing_id = uuid.UUID(existing_vault_id_str)
                    await vault_rotate(existing_id, value)
                    logger.info("unified-vault: updated SSO secret field=%s provider=%s", field, provider_id)
                else:
                    meta = await vault_create(name, _SECRET_TYPE, value)
                    existing_vault_id_str = str(meta["id"])
                    logger.info("unified-vault: created SSO secret field=%s provider=%s", field, provider_id)
            except UnifiedVaultClientError as exc:
                # Vault unavailable — keep plaintext out of config, propagate.
                logger.error("unified-vault: failed to store SSO secret field=%s: %s", field, type(exc).__name__)
                raise

            sanitized[_vault_id_config_key(field)] = existing_vault_id_str
            sanitized[f"{field}_ref"] = name
            sanitized.pop(field, None)

        return sanitized

    async def retrieve_secret(self, provider_id: uuid.UUID, field: str) -> str | None:
        """Retrieve and return the plaintext secret value.

        Primary: unified vault (via vault UUID cached in provider config).
        Fallback: legacy SystemSecret table (migration window only).
        """
        from user_management.services.unified_vault_client import (
            UnifiedVaultClientError,
            UnifiedVaultSecretNotFound,
            is_configured,
            vault_read,
        )

        # Rollout fallback: vault not provisioned → read straight from legacy.
        if not is_configured():
            return await _legacy_retrieve(self._session, provider_id, field)

        # Try to resolve vault_id from the provider's stored config.
        vault_id = await self._resolve_vault_id(provider_id, field)

        if vault_id is not None:
            try:
                return await vault_read(vault_id)
            except UnifiedVaultSecretNotFound:
                logger.warning(
                    "unified-vault: secret not found, falling back to legacy; field=%s provider=%s",
                    field,
                    provider_id,
                )
            except UnifiedVaultClientError as exc:
                logger.error(
                    "unified-vault: read failed field=%s: %s; falling back to legacy",
                    field,
                    type(exc).__name__,
                )
        else:
            # vault_id not in config — try finding by name in vault listing.
            vault_id = await self._find_vault_id_by_name(provider_id, field)
            if vault_id is not None:
                try:
                    return await vault_read(vault_id)
                except UnifiedVaultClientError:
                    pass

        # Legacy fallback (migration window only).
        return await _legacy_retrieve(self._session, provider_id, field)

    async def delete_secrets(self, provider_id: uuid.UUID) -> None:
        """Delete all vault secrets for an SSO provider."""
        from user_management.services.unified_vault_client import (
            UnifiedVaultClientError,
            UnifiedVaultSecretNotFound,
            is_configured,
            vault_delete,
        )

        # Rollout fallback: vault not provisioned → only legacy rows exist.
        if not is_configured():
            await self._delete_legacy(provider_id)
            return

        for field in SENSITIVE_FIELDS:
            vault_id = await self._resolve_vault_id(provider_id, field)
            if vault_id is None:
                vault_id = await self._find_vault_id_by_name(provider_id, field)
            if vault_id is None:
                continue
            try:
                await vault_delete(vault_id)
                logger.info("unified-vault: deleted SSO secret field=%s provider=%s", field, provider_id)
            except UnifiedVaultSecretNotFound:
                pass  # already gone — idempotent
            except UnifiedVaultClientError as exc:
                logger.warning("unified-vault: delete failed field=%s: %s", field, type(exc).__name__)

        # Also clean up legacy SystemSecret rows if present.
        await self._delete_legacy(provider_id)

    async def has_plaintext_secrets(self, config: dict) -> bool:
        """Return True when config contains un-migrated plaintext secrets."""
        return any(field in config for field in SENSITIVE_FIELDS)

    async def migrate_plaintext_to_secrets(self, provider_id: uuid.UUID, config: dict) -> dict:
        """Migrate plaintext secrets in config to the unified vault (idempotent)."""
        if not await self.has_plaintext_secrets(config):
            return config
        logger.info("migrating plaintext SSO secrets to unified vault for provider %s", provider_id)
        return await self.store_secrets(provider_id, config)

    # ------------------------------------------------------------------
    # One-shot vault migration helper (called from migration script)
    # ------------------------------------------------------------------

    async def migrate_to_vault(self, provider_id: uuid.UUID, config: dict[str, Any]) -> dict[str, Any]:
        """Copy existing SystemSecret entries into the vault (idempotent).

        Called by the migration script for each SSO provider.  Returns the
        updated config (with vault IDs) so the caller can persist it.
        """
        from models.database import SystemSecret
        from services.encryption import decrypt_data
        from user_management.services.unified_vault_client import (
            UnifiedVaultClientError,
            vault_create,
        )

        updated = config.copy()
        for field in SENSITIVE_FIELDS:
            vault_id_key = _vault_id_config_key(field)
            if updated.get(vault_id_key):
                logger.info("migrate_to_vault: skip field=%s provider=%s (already migrated)", field, provider_id)
                continue

            # Read from legacy store.
            key = _vault_name(provider_id, field)
            row = await self._session.execute(select(SystemSecret).where(SystemSecret.key == key))
            secret_row = row.scalar_one_or_none()
            if secret_row is None:
                continue

            try:
                plaintext = decrypt_data(secret_row.encrypted_value)
            except Exception as exc:
                logger.error(
                    "migrate_to_vault: decrypt failed field=%s provider=%s: %s",
                    field,
                    provider_id,
                    type(exc).__name__,
                )
                continue

            try:
                meta = await vault_create(key, _SECRET_TYPE, plaintext)
            except UnifiedVaultClientError as exc:
                logger.error(
                    "migrate_to_vault: vault_create failed field=%s provider=%s: %s",
                    field,
                    provider_id,
                    type(exc).__name__,
                )
                raise

            updated[vault_id_key] = str(meta["id"])
            updated[f"{field}_ref"] = key
            updated.pop(field, None)
            logger.info(
                "migrate_to_vault: migrated field=%s provider=%s vault_id=%s",
                field,
                provider_id,
                meta["id"],
            )

        return updated

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_vault_id(self, provider_id: uuid.UUID, field: str) -> uuid.UUID | None:
        """Look up the vault UUID from the provider's persisted config (fast path)."""
        try:
            from sqlalchemy import select as sa_select

            from user_management.models.sso import SSOProvider

            row = await self._session.execute(sa_select(SSOProvider).where(SSOProvider.id == provider_id))
            provider = row.scalar_one_or_none()
            if provider is None:
                return None
            vault_id_str = provider.config.get(_vault_id_config_key(field))
            if vault_id_str:
                return uuid.UUID(vault_id_str)
        except Exception as exc:
            logger.warning(
                "unified-vault: vault_id lookup failed field=%s provider=%s: %s",
                field,
                provider_id,
                type(exc).__name__,
            )
        return None

    async def _find_vault_id_by_name(self, provider_id: uuid.UUID, field: str) -> uuid.UUID | None:
        """Scan vault listing to find a secret by canonical name (slow path)."""
        from user_management.services.unified_vault_client import UnifiedVaultClientError, vault_list

        target = _vault_name(provider_id, field)
        try:
            entries = await vault_list()
            for entry in entries:
                if entry.get("name") == target:
                    return uuid.UUID(entry["id"])
        except UnifiedVaultClientError:
            pass
        return None

    async def _delete_legacy(self, provider_id: uuid.UUID) -> None:
        """Remove legacy SystemSecret rows for a provider (cleanup after migration)."""
        try:
            from models.database import SystemSecret

            for field in SENSITIVE_FIELDS:
                key = _vault_name(provider_id, field)
                row = await self._session.execute(select(SystemSecret).where(SystemSecret.key == key))
                secret = row.scalar_one_or_none()
                if secret is not None:
                    await self._session.delete(secret)
        except Exception as exc:
            logger.warning("_delete_legacy failed for provider %s: %s", provider_id, type(exc).__name__)
