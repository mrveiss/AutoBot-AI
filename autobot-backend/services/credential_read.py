# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read path for imported credentials from the envelope store (#10088 / Task 3c-2).

Resolves a credential imported from the legacy SQLite store into the envelope
store via the ``imported_from_sqlite`` marker the 3c-1 import stamped, and decrypts it
through the owner's user vault. Lives in the service layer (not the heavy
``knowledge.connectors`` package) so it imports cleanly in the minimal migration-gate
test environment.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def read_imported_credential_in_session(session, secret_id: str, owner_id: str, root_key: bytes) -> dict | None:
    """Resolve + decrypt an imported credential within *session* (the testable core).

    Matches the legacy SQLite id via the ``imported_from_sqlite`` marker the 3c-1 import
    stamped (scoped to *owner_id* for defence in depth), then decrypts through the owner's
    user vault. Returns a SecretsService-shaped dict (``{"created_by", "value"}``), or
    ``None`` to fall back to SQLite. Any envelope-read failure — not imported, not
    accessible, or a corrupt/partial row — returns ``None`` so the fallback can never be
    fatal while SQLite is still authoritative.
    """
    import uuid

    from sqlalchemy import select

    from autobot_shared.secrets_envelope import DecryptionError, UnsupportedFormatError
    from autobot_shared.secrets_vault import VaultKind, VaultRef
    from models.secret import Secret
    from services.envelope_secrets_service import EnvelopeSecretsService, SecretAccessError, SecretNotFoundError

    try:
        owner_uuid = uuid.UUID(str(owner_id))
    except ValueError:
        return None  # owner isn't a uuid → cannot match an imported row

    marker = Secret.extra_data["imported_from_sqlite"].astext
    row = (
        (
            await session.execute(
                select(Secret).where(
                    marker == str(secret_id), Secret.owner_id == owner_uuid, Secret.is_active.is_(True)
                )
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return None  # not yet imported → SQLite fallback
    try:
        plaintext = await EnvelopeSecretsService(root_key=root_key).read(
            session, secret_id=row.id, accessible_vaults={VaultRef(VaultKind.USER, str(owner_id))}
        )
    except (
        SecretAccessError,
        SecretNotFoundError,
        DecryptionError,
        UnsupportedFormatError,
        KeyError,
        ValueError,
    ) as exc:
        logger.warning(
            "Envelope read unusable for imported secret %s (owner %s): %s — falling back", secret_id, owner_id, exc
        )
        return None
    return {"created_by": str(owner_id), "value": plaintext.decode("utf-8")}


async def load_imported_credential(secret_id: str, owner_id: str) -> dict | None:
    """Acquire a session and read an imported credential from the envelope store.

    Returns ``None`` to fall back to SQLite when the envelope store is not configured
    (root key unset) on this deployment. See :func:`read_imported_credential_in_session`.
    """
    from autobot_shared.secrets_envelope import load_root_key
    from user_management.database import get_async_session_factory

    try:
        root_key = load_root_key()
    except RuntimeError:
        return None  # envelope store not configured on this deployment

    factory = get_async_session_factory()
    async with factory() as session:
        return await read_imported_credential_in_session(session, secret_id, owner_id, root_key)
