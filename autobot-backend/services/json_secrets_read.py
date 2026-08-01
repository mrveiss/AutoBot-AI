# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dual-read path for legacy JSON-store secrets imported into the envelope store (#10088 / Task 3).

Resolves a secret imported by ``json_secrets_importer`` via the ``imported_from_json`` marker,
decrypts it through the System vault, and reshapes it to the exact dict contract
``api.secrets.SecretsManager.get_secret()`` returns, so ``GET /secrets/{id}`` can use either
path with no response-shape drift for the frontend. Returns ``None`` (fall back to the legacy
JSON file) when the secret hasn't been imported yet, the envelope read fails, or the feature
flag is off — the JSON file remains authoritative until this path is enabled and proven.

Feature-flagged the same way as the connector-credential cutover
(``knowledge.connectors.credential_store.VAULT_READ_ENV``): default off, so behaviour is
byte-identical until explicitly enabled.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

JSON_UNIFIED_READ_ENV = "AUTOBOT_SECRETS_JSON_UNIFIED_READ"
_MARKER = "imported_from_json"


def json_unified_read_enabled() -> bool:
    """Whether the JSON-store dual-read (envelope-first) path is enabled."""
    return os.environ.get(JSON_UNIFIED_READ_ENV, "false").strip().lower() in ("1", "true", "yes")


async def _find_by_marker(session, secret_id: str):
    from sqlalchemy import select

    from models.secret import Secret

    marker = Secret.extra_data[_MARKER].astext
    result = await session.execute(select(Secret).where(marker == str(secret_id), Secret.is_active.is_(True)))
    return result.scalars().first()


def _to_legacy_shape(row, value: str) -> dict:
    """Reshape an envelope ``Secret`` row back into the legacy ``get_secret()`` dict contract."""
    extra = row.extra_data or {}
    return {
        "id": extra.get(_MARKER, str(row.id)),
        "name": row.name,
        "type": row.type,
        "scope": extra.get("legacy_scope"),
        "chat_id": extra.get("legacy_chat_id"),
        "description": row.description,
        "tags": row.tags or [],
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "metadata": extra.get("legacy_metadata") or {},
        "value": value,
    }


async def read_imported_json_secret_in_session(session, secret_id: str, root_key: bytes) -> dict | None:
    """Resolve + decrypt an imported JSON-store secret within *session* (the testable core)."""
    from autobot_shared.secrets_envelope import DecryptionError, UnsupportedFormatError
    from autobot_shared.secrets_vault import VaultKind, VaultRef
    from services.envelope_secrets_service import EnvelopeSecretsService, SecretAccessError, SecretNotFoundError

    row = await _find_by_marker(session, secret_id)
    if row is None:
        return None  # not yet imported -> JSON file fallback
    try:
        plaintext = await EnvelopeSecretsService(root_key=root_key).read(
            session, secret_id=row.id, accessible_vaults={VaultRef(VaultKind.SYSTEM)}
        )
    except (
        SecretAccessError,
        SecretNotFoundError,
        DecryptionError,
        UnsupportedFormatError,
        KeyError,
        ValueError,
    ) as exc:
        logger.warning("Envelope read unusable for imported JSON secret %s: %s — falling back", secret_id, exc)
        return None
    return _to_legacy_shape(row, plaintext.decode("utf-8"))


async def load_imported_json_secret(secret_id: str) -> dict | None:
    """Acquire a session and read an imported legacy-JSON secret from the envelope store.

    Returns ``None`` (triggering the legacy-file fallback) when the flag is off or the
    envelope store is not configured (root key unset) on this deployment.
    """
    if not json_unified_read_enabled():
        return None
    from autobot_shared.secrets_envelope import load_root_key
    from user_management.database import get_async_session_factory

    try:
        root_key = load_root_key()
    except RuntimeError:
        return None

    factory = get_async_session_factory()
    async with factory() as session:
        return await read_imported_json_secret_in_session(session, secret_id, root_key)
