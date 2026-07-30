# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Generic ``system_secrets`` -> unified-secrets System vault bridge (#10088 Task 6a).

Same client/pattern as ``user_management.services.sso_secrets`` (#10153,
PR #10498): the SLM Manager reaches the System vault over HTTP via
``vault_client`` (HMAC / X-Internal-API-Key auth), never a direct import —
the vault lives in a different service (autobot-backend) with its own DB.

Unlike SSO secrets (one JSONB config column per provider to cache the vault
UUID), ``SystemSecret`` rows are flat ``key -> encrypted_value`` pairs with no
spare column to stash a vault id, so lookups always resolve by **name**
(``vault_list()`` filtered by ``name == key``) rather than a cached UUID.

Read ordering is LEGACY-FIRST, by design
-----------------------------------------
The legacy ``system_secrets`` CRUD (``api/secrets.py``, the current SLM
Secrets UI) is left untouched by this task (Task 6c, unifying the two
Secrets UIs, is a product decision for the owner — see #10088). Since that
UI remains the live write path for arbitrary admin-managed keys, the legacy
row is still the freshest copy; ``retrieve_secret`` therefore checks legacy
first and only falls back to the vault for a key that has been imported and
subsequently removed from ``system_secrets`` (so a migrated-then-pruned
secret never becomes unreachable — the "no secret becomes unreachable
mid-cutover" invariant, satisfied without introducing a second, divergent
write path (no dual-write)).

Irreducible keys are never migrated
------------------------------------
``autobot_internal_api_key`` is the credential ``vault_client`` itself uses
to authenticate every call in this module (X-Internal-API-Key). Storing it
*inside* the vault it unlocks is the exact confused-deputy cycle the #10088
Appendix's "auth-bootstrap" classification exists to prevent — it is
irreducible and MUST stay in ``system_secrets`` (or, per the Appendix, an
env file) regardless of vault availability. ``sso:provider:*`` keys are
already handled by the dedicated #10153 migration
(``migrations/migrate_sso_to_unified_vault.py`` /
``user_management.services.sso_secrets``) — skipped here to avoid a
duplicate vault entry under the same name.

Never log a secret value. Never expose one in an exception message.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Auth-bootstrap credential — gates access to the vault this module talks to.
#: Migrating it would create a confused-deputy cycle; see module docstring.
IRREDUCIBLE_KEYS: frozenset[str] = frozenset({"autobot_internal_api_key"})  # nosec B105 - key name, not a credential

#: SSO provider secrets already have a dedicated migration path (#10153).
_SSO_KEY_PREFIX = "sso:provider:"

#: Vault secret-type label for system_secrets rows imported by this module.
_SECRET_TYPE = "system-secret"  # nosec B105 - type label, not a credential


def is_migratable(key: str) -> bool:
    """True when *key* is eligible to move into the System vault.

    False for the auth-bootstrap key (irreducible, #10088 Appendix) and for
    SSO provider fields (already migrated under a dedicated #10153 path).
    """
    return key not in IRREDUCIBLE_KEYS and not key.startswith(_SSO_KEY_PREFIX)


async def _legacy_get(session: AsyncSession, key: str) -> str | None:
    """Read+decrypt a legacy ``system_secrets`` row; ``None`` if absent."""
    from models.database import SystemSecret
    from services.encryption import decrypt_data

    result = await session.execute(select(SystemSecret).where(SystemSecret.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return decrypt_data(row.encrypted_value)


async def _find_vault_id_by_name(name: str) -> uuid.UUID | None:
    """Scan the System vault listing for an entry named *name* (no cached id available)."""
    from user_management.services.vault_client import VaultClientError, vault_list

    try:
        entries = await vault_list()
    except VaultClientError:
        return None
    for entry in entries:
        if entry.get("name") == name:
            return uuid.UUID(entry["id"])
    return None


async def retrieve_secret(session: AsyncSession, key: str) -> str | None:
    """Return the plaintext value of *key*, legacy-first (see module docstring).

    Falls back to the System vault only when the legacy row is absent —
    covers a key that was imported by :func:`migrate_key_to_vault` and later
    pruned from ``system_secrets``. Returns ``None`` when the key exists
    nowhere.
    """
    legacy_value = await _legacy_get(session, key)
    if legacy_value is not None:
        return legacy_value

    if key in IRREDUCIBLE_KEYS:
        return None  # never consult the vault for the auth-bootstrap key

    from user_management.services.vault_client import (
        VaultClientError,
        VaultSecretNotFound,
        is_configured,
        vault_read,
    )

    if not is_configured():
        return None

    vault_id = await _find_vault_id_by_name(key)
    if vault_id is None:
        return None
    try:
        return await vault_read(vault_id)
    except VaultSecretNotFound:
        return None
    except VaultClientError as exc:
        logger.warning("system-secrets-vault: read failed key=%s: %s", key, type(exc).__name__)
        return None


async def delete_vault_copy(key: str) -> None:
    """Delete *key*'s vault entry, if any (best-effort, never raises).

    Called whenever the legacy row is deleted (``api/secrets.py``) so a
    revoked/deleted secret can never resurrect through the vault-fallback
    read path in :func:`retrieve_secret` — mirrors
    ``SSOSecretsManager.delete_secrets`` deleting both copies (#10153).
    """
    if key in IRREDUCIBLE_KEYS:
        return  # never touches the vault for the auth-bootstrap key

    from user_management.services.vault_client import (
        VaultClientError,
        VaultSecretNotFound,
        is_configured,
        vault_delete,
    )

    if not is_configured():
        return
    vault_id = await _find_vault_id_by_name(key)
    if vault_id is None:
        return
    try:
        await vault_delete(vault_id)
        logger.info("system-secrets-vault: deleted vault copy key=%s", key)
    except VaultSecretNotFound:
        pass  # already gone — idempotent
    except VaultClientError as exc:
        logger.warning("system-secrets-vault: delete failed key=%s: %s", key, type(exc).__name__)


async def migrate_key_to_vault(session: AsyncSession, key: str) -> bool:
    """Copy one ``system_secrets`` row into the System vault (idempotent).

    Returns ``True`` when a vault write happened, ``False`` when the key is
    ineligible, absent from the legacy table, already present in the vault,
    or the vault is not configured. Never deletes the legacy row — the
    existing CRUD (``api/secrets.py``) stays the live write path (#10088
    Task 6c is undecided; see module docstring).
    """
    if not is_migratable(key):
        return False

    from user_management.services.vault_client import VaultClientError, is_configured, vault_create

    if not is_configured():
        return False

    if await _find_vault_id_by_name(key) is not None:
        logger.info("system-secrets-vault: migrate skip key=%s (already migrated)", key)
        return False

    plaintext = await _legacy_get(session, key)
    if plaintext is None:
        return False

    try:
        await vault_create(key, _SECRET_TYPE, plaintext)
    except VaultClientError as exc:
        logger.error("system-secrets-vault: migrate failed key=%s: %s", key, type(exc).__name__)
        raise
    logger.info("system-secrets-vault: migrated key=%s", key)
    return True
