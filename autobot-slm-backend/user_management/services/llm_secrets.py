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
import re
from typing import Any

logger = logging.getLogger(__name__)

# The only sensitive field in an LLM provider config entry.
_SENSITIVE_FIELD = "api_key"
_SECRET_TYPE = "llm-api-key"  # nosec B105  # type label, not a hardcoded secret
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
    from user_management.services.vault_client import VaultClientError, is_configured

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
        existing_vault_id = await _rotate_or_create(name, provider_name, existing_vault_id, api_key)
    except VaultClientError as exc:
        logger.error("unified-vault: failed to store LLM api_key provider=%s: %s", provider_name, type(exc).__name__)
        raise

    sanitized[_VAULT_ID_KEY] = existing_vault_id
    sanitized["api_key_ref"] = name
    sanitized.pop(_SENSITIVE_FIELD, None)
    return sanitized


async def _rotate_or_create(name: str, provider_name: str, vault_id: str | None, api_key: str) -> str:
    """Rotate the stored secret, or create one when there is none -- or it is gone.

    A stored id whose secret no longer exists is treated as absent (#17826):
    rotating it would fail every save for that provider, permanently.
    """
    from user_management.services.vault_client import VaultSecretNotFound, vault_create, vault_rotate

    if vault_id:
        import uuid

        try:
            await vault_rotate(uuid.UUID(vault_id), api_key)
            logger.info("unified-vault: rotated LLM api_key for provider=%s", provider_name)
            return vault_id
        except VaultSecretNotFound:
            logger.warning("unified-vault: stored LLM api_key id is gone, creating provider=%s", provider_name)
    meta = await vault_create(name, _SECRET_TYPE, api_key)
    logger.info("unified-vault: stored LLM api_key for provider=%s", provider_name)
    return str(meta["id"])


async def retrieve_provider_api_key(provider_name: str, provider_dict: dict[str, Any]) -> str:
    """Return plaintext api_key for a provider.

    Primary: vault (via ``api_key_vault_id``).
    Fallback: legacy inline-encrypted value during migration window.
    Returns ``""`` when no key is stored.
    """
    from user_management.services.vault_client import (
        VaultClientError,
        VaultSecretNotFound,
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
        except VaultSecretNotFound:
            logger.warning("unified-vault: LLM api_key not found provider=%s, falling back", provider_name)
        except VaultClientError as exc:
            logger.error("unified-vault: read failed provider=%s: %s; falling back", provider_name, type(exc).__name__)
    else:
        # Scan vault by name (slow path for entries that predate vault_id caching).
        target = _vault_name(provider_name)
        try:
            entries = await vault_list()
            for entry in entries:
                if entry.get("name") == target:
                    import uuid

                    return await vault_read(uuid.UUID(entry["id"]))
        except VaultClientError:
            pass

    # Legacy inline fallback.
    raw = provider_dict.get(_SENSITIVE_FIELD, "")
    return _decrypt(raw) if raw else ""


async def delete_provider_api_key(provider_name: str, provider_dict: dict[str, Any]) -> None:
    """Delete the vault secret for a provider's api_key (best-effort, no-op if absent)."""
    from user_management.services.vault_client import (
        VaultClientError,
        VaultSecretNotFound,
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
    except VaultSecretNotFound:
        pass
    except VaultClientError as exc:
        logger.warning("unified-vault: delete failed provider=%s: %s", provider_name, type(exc).__name__)


# ---------------------------------------------------------------------------
# Client round-trip (#17826)
# ---------------------------------------------------------------------------

# Every field that locates or holds a stored api_key. None of them is sent to a
# client, and all of them are carried forward when a client sends no new key.
_SECRET_REF_FIELDS = (_SENSITIVE_FIELD, _VAULT_ID_KEY, "api_key_ref")

# The display mask the settings API used to send (``sk-a...b3f2`` / ``****``).
# A tab loaded before #17826 still holds these in its state, and saving it must
# not write one into the vault as if it were a key.
_DISPLAY_MASK = re.compile(r"^(\*{4}|.{4}\.\.\..{4})$")


class MaskedKeySubmitted(ValueError):
    """A submitted api_key is a display mask, not a key (#17826)."""


def public_provider_view(provider_dict: dict[str, Any]) -> dict[str, Any]:
    """A provider entry with every secret field omitted, for any client response.

    Omitted rather than masked: a value the client never receives cannot be
    written back, so a GET-then-PUT round-trip is a no-op for the stored key.
    """
    return {k: v for k, v in provider_dict.items() if k not in _SECRET_REF_FIELDS}


async def merge_provider_secret(
    provider_name: str, incoming: dict[str, Any], stored: dict[str, Any] | None
) -> dict[str, Any]:
    """Resolve a client-submitted provider entry against what is stored.

    No ``api_key`` submitted: the stored secret reference is carried forward
    unchanged -- the vault is not touched. A new key: stored under the existing
    vault id, so it rotates that secret rather than creating a second one.
    Raises :class:`MaskedKeySubmitted` for a display mask.
    """
    merged = public_provider_view(incoming)
    prior = {k: v for k, v in (stored or {}).items() if k in _SECRET_REF_FIELDS}
    new_key = incoming.get(_SENSITIVE_FIELD) or ""
    if not new_key:
        return {**merged, **prior}
    if _DISPLAY_MASK.fullmatch(new_key):
        raise MaskedKeySubmitted(f"api_key for provider {provider_name!r} is a display mask; reload and re-enter it")
    from user_management.services.vault_client import is_configured

    # A vault id is only meaningful while the vault is configured; carried into an
    # inline write it would later shadow the new key with the old one.
    if prior.get(_VAULT_ID_KEY) and is_configured():
        merged[_VAULT_ID_KEY] = prior[_VAULT_ID_KEY]
    return await store_provider_api_key(provider_name, {**merged, _SENSITIVE_FIELD: new_key})
