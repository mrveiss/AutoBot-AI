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


def _active_secret_ids_newest_first(db_path: str, name: str) -> list[str]:
    """Ids of every active, unexpired ``user``-scope secret named *name*, newest first (ids only, no values)."""
    import sqlite3

    from autobot_shared.time_utils import now_utc

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id FROM secrets WHERE is_active = 1 AND name = ? AND scope = 'user' "
            "AND (expires_at IS NULL OR expires_at > ?) ORDER BY created_at DESC, rowid DESC",
            (name, now_utc().isoformat()),
        ).fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows]


async def find_connector_secret_ids(connector_id: str) -> list[str]:
    """Every active credential id filed under *connector_id*, NEWEST first (#13710).

    ``UNIQUE(name, scope, chat_id)`` does not stop duplicates (``chat_id`` is NULL, and SQLite treats NULLs as
    distinct), and ``get_secret(name=...)`` takes an arbitrary first row, so a stale duplicate could win.
    """
    import asyncio

    from services.credential_write import connector_secret_name
    from services.secrets_service import get_secrets_service

    return await asyncio.to_thread(
        _active_secret_ids_newest_first, get_secrets_service().db_path, connector_secret_name(connector_id)
    )


async def find_connector_secret_id(connector_id: str) -> str | None:
    """The id of the NEWEST credential filed under *connector_id*, or ``None`` when none is stored (#13710)."""
    ids = await find_connector_secret_ids(connector_id)
    return ids[0] if ids else None


async def assert_attachable_secret(secret_id: str, owner_id: str) -> None:
    """Refuse to attach *secret_id* to a connector *owner_id* may not own (#13710).

    Raises ``LookupError`` when the secret does not exist, ``PermissionError`` when its recorded owner is not
    *owner_id*, or when it (or *owner_id*) belongs to a service-owned OAuth provider -- the company mailbox,
    whose sync, update or delete would otherwise use, rotate or revoke that shared credential.
    """
    import asyncio

    from knowledge.connectors.oauth_flow import OAUTH_PROVIDERS
    from services.credential_write import connector_secret_name
    from services.secrets_service import get_secrets_service

    secret = await asyncio.to_thread(get_secrets_service().get_secret, secret_id=secret_id, include_value=False)
    if secret is None:
        raise LookupError("secret not found")
    service = [p for p in OAUTH_PROVIDERS.values() if p.service_owner_id]
    owners = {p.service_owner_id for p in service}
    names = {connector_secret_name(p.service_connector_id) for p in service}
    created_by = secret.get("created_by") or ""
    if created_by != owner_id or owner_id in owners or created_by in owners or secret.get("name") in names:
        raise PermissionError("secret cannot be attached by this owner")
