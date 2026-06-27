# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLM provider api_key storage via the unified-secrets System vault (#10503).

Mirrors the pattern from ``sso_secrets.py``: sensitive fields are extracted from
LLM provider config before persistence, stored in the unified vault, and
replaced with a ``{field}_vault_id`` reference.  A backward-compatible read path
falls back to the legacy inline-encrypted value (``services.encryption``) during
the rollout window.

Secret naming in the vault:
    ``llm:provider:{provider_name}:api_key``

The vault ``secret_id`` (UUID) is cached as ``api_key_vault_id`` in the provider
dict so subsequent reads and rotations address the secret directly.

Never log secret values.  Never expose them in exception messages.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# The only sensitive field in an LLM provider config entry.
_SENSITIVE_FIELD = "api_key"
_SECRET_TYPE = "llm-api-key"  # nosec B105 - type label, not a hardcoded secret
_VAULT_ID_KEY = "api_key_vault_id"


def _vault_name(provider_name: str) -> str:
    """Canonical vault secret name for an LLM provider api_key."""
    return f"llm:provider:{provider_name}:api_key"


# ---------------------------------------------------------------------------
# Legacy fallback helpers (inline AES-GCM encrypted value)
# ---------------------------------------------------------------------------


def _encrypt(value: str) -> str:
    from services.encryption import encrypt_data

    return encrypt_data(value)


def _decrypt(encrypted: str) -> str:
    from services.encryption import decrypt_data

    return decrypt_data(encrypted)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


async def store_provider_api_key(provider_name: str, provider_dict: dict[str, Any]) -> dict[str, Any]:
    """Extract ``api_key`` from *provider_dict*, write to vault, return sanitized copy.

    The returned dict has ``api_key`` removed, ``api_key_vault_id`` set to the
    vault UUID string, and ``api_key_ref`` set to the canonical vault name.
    Idempotent: rotates an existing vault entry when ``api_key_vault_id`` is
    already present.

    Falls back to legacy inline encryption when the vault is not configured.
    """
    from user_management.services.unified_vault_client import (
        UnifiedVaultClientError,
        is_configured,
        vault_create,
        vault_rotate,
    )

    api_key = provider_dict.get(_SENSITIVE_FIELD)
    if not api_key:
        return provider_dict

    sanitized = provider_dict.copy()

    if not is_configured():
        # Rollout fallback: encrypt inline as before.
        if not api_key.startswith("gAAA"):
            sanitized[_SENSITIVE_FIELD] = _encrypt(api_key)
        return sanitized

    name = _vault_name(provider_name)
    existing_vault_id = provider_dict.get(_VAULT_ID_KEY)
    try:
        if existing_vault_id:
            import uuid

            await vault_rotate(uuid.UUID(existing_vault_id), api_key)
            logger.info("unified-vault: rotated LLM api_key for provider=%s", provider_name)
        else:
            meta = await vault_create(name, _SECRET_TYPE, api_key)
            existing_vault_id = str(meta["id"])
            logger.info("unified-vault: stored LLM api_key for provider=%s", provider_name)
    except UnifiedVaultClientError as exc:
        logger.error("unified-vault: failed to store LLM api_key provider=%s: %s", provider_name, type(exc).__name__)
        raise

    sanitized[_VAULT_ID_KEY] = existing_vault_id
    sanitized["api_key_ref"] = name
    sanitized.pop(_SENSITIVE_FIELD, None)
    return sanitized


async def retrieve_provider_api_key(provider_name: str, provider_dict: dict[str, Any]) -> str:
    """Return plaintext api_key for a provider.

    Primary: vault (via ``api_key_vault_id``).
    Fallback: legacy inline-encrypted value during migration window.
    Returns ``""`` when no key is stored.
    """
    from user_management.services.unified_vault_client import (
        UnifiedVaultClientError,
        UnifiedVaultSecretNotFound,
        is_configured,
        vault_list,
        vault_read,
    )

    if not is_configured():
        raw = provider_dict.get(_SENSITIVE_FIELD, "")
        return _decrypt(raw) if raw else ""

    vault_id_str = provider_dict.get(_VAULT_ID_KEY)
    if vault_id_str:
        import uuid

        try:
            return await vault_read(uuid.UUID(vault_id_str))
        except UnifiedVaultSecretNotFound:
            logger.warning("unified-vault: LLM api_key not found provider=%s, falling back", provider_name)
        except UnifiedVaultClientError as exc:
            logger.error(
                "unified-vault: read failed provider=%s: %s; falling back", provider_name, type(exc).__name__
            )
    else:
        # Scan vault by name (slow path for entries that predate vault_id caching).
        target = _vault_name(provider_name)
        try:
            entries = await vault_list()
            for entry in entries:
                if entry.get("name") == target:
                    import uuid

                    return await vault_read(uuid.UUID(entry["id"]))
        except UnifiedVaultClientError:
            pass

    # Legacy inline fallback.
    raw = provider_dict.get(_SENSITIVE_FIELD, "")
    return _decrypt(raw) if raw else ""


async def delete_provider_api_key(provider_name: str, provider_dict: dict[str, Any]) -> None:
    """Delete the vault secret for a provider's api_key (best-effort, no-op if absent)."""
    from user_management.services.unified_vault_client import (
        UnifiedVaultClientError,
        UnifiedVaultSecretNotFound,
        is_configured,
        vault_delete,
    )

    if not is_configured():
        return

    vault_id_str = provider_dict.get(_VAULT_ID_KEY)
    if not vault_id_str:
        return
    import uuid

    try:
        await vault_delete(uuid.UUID(vault_id_str))
        logger.info("unified-vault: deleted LLM api_key for provider=%s", provider_name)
    except UnifiedVaultSecretNotFound:
        pass
    except UnifiedVaultClientError as exc:
        logger.warning("unified-vault: delete failed provider=%s: %s", provider_name, type(exc).__name__)
