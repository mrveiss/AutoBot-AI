# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dual-write mirror of connector credentials into the envelope store (#10088 / Task 3c-2).

Expand-phase write side of the expand/contract cutover. When dual-write is enabled, every
ConnectorCredentialStore write also mirrors the credential into the envelope store,
keyed by the same ``imported_from_sqlite`` marker the read path resolves. SQLite stays the
canonical store, so the public helpers are **best-effort**: a mirror failure is logged and
swallowed (never breaks the canonical SQLite write), and a missing/stale envelope copy simply
degrades to the SQLite fallback on read. Lives in the service layer (not the heavy
``knowledge.connectors`` package) so it imports cleanly in the minimal migration-gate env.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MARKER = "imported_from_sqlite"


async def _find_by_marker(session, sqlite_id: str, owner_uuid):
    from sqlalchemy import select

    from models.secret import Secret

    marker = Secret.extra_data[_MARKER].astext
    return (
        (
            await session.execute(
                select(Secret).where(
                    marker == str(sqlite_id), Secret.owner_id == owner_uuid, Secret.is_active.is_(True)
                )
            )
        )
        .scalars()
        .first()
    )


async def mirror_in_session(
    session, sqlite_id: str, owner_id: str, value: str, root_key: bytes, *, name=None, secret_type=None
) -> None:
    """Testable core: upsert the envelope copy within *session* (caller commits).

    Rotates an existing copy (matched by marker + owner); creates one when absent and
    ``name``/``secret_type`` are supplied (the create paths). Owner not a uuid → no-op.
    """
    import uuid

    from autobot_shared.secrets_vault import VaultKind, VaultRef
    from services.envelope_secrets_service import EnvelopeSecretsService

    try:
        owner_uuid = uuid.UUID(str(owner_id))
    except ValueError:
        return  # owner isn't a uuid → cannot key an envelope row

    vault = VaultRef(VaultKind.USER, str(owner_id))
    svc = EnvelopeSecretsService(root_key=root_key)
    row = await _find_by_marker(session, sqlite_id, owner_uuid)
    if row is not None:
        await svc.rotate_value(session, secret_id=row.id, new_plaintext=value.encode("utf-8"), actor_vaults={vault})
    elif name and secret_type:
        created = await svc.create(
            session,
            owner_vault=vault,
            name=name,
            secret_type=secret_type,
            plaintext=value.encode("utf-8"),
            created_by=owner_uuid,
        )
        created.extra_data = {_MARKER: str(sqlite_id)}
        await session.flush()
    else:
        logger.debug("No envelope copy for credential %s and no name/type to create one — skipping mirror", sqlite_id)


async def delete_in_session(session, sqlite_id: str, owner_id: str, root_key: bytes) -> None:
    """Testable core: delete the envelope copy within *session* by marker (caller commits)."""
    import uuid

    from services.envelope_secrets_service import EnvelopeSecretsService

    try:
        owner_uuid = uuid.UUID(str(owner_id))
    except ValueError:
        return
    row = await _find_by_marker(session, sqlite_id, owner_uuid)
    if row is None:
        return
    await EnvelopeSecretsService(root_key=root_key).delete(session, secret_id=row.id)


def _root_key_or_none():
    from autobot_shared.secrets_envelope import load_root_key

    try:
        return load_root_key()
    except RuntimeError:
        return None  # envelope store not configured on this deployment


async def mirror_credential_to_unified(
    sqlite_id: str, owner_id: str, value: str, *, name=None, secret_type=None
) -> None:
    """Best-effort upsert of a credential's envelope copy. Never raises."""
    try:
        root_key = _root_key_or_none()
        if root_key is None:
            return
        from user_management.database import get_async_session_factory

        async with get_async_session_factory()() as session:
            await mirror_in_session(session, sqlite_id, owner_id, value, root_key, name=name, secret_type=secret_type)
            await session.commit()
    except Exception as exc:  # dual-write must never break the canonical SQLite write
        logger.warning("Envelope mirror failed for credential %s (owner %s): %s", sqlite_id, owner_id, exc)


async def delete_credential_from_unified(sqlite_id: str, owner_id: str) -> None:
    """Best-effort delete of a credential's envelope copy by marker. Never raises.

    Logged at ERROR (not WARNING): a swallowed delete leaves an active envelope copy of a
    credential already revoked in SQLite, which read-first would serve — see #10088 (the
    revoke-resurrection gate that must be closed before the envelope read flag is enabled).
    """
    try:
        root_key = _root_key_or_none()
        if root_key is None:
            return
        from user_management.database import get_async_session_factory

        async with get_async_session_factory()() as session:
            await delete_in_session(session, sqlite_id, owner_id, root_key)
            await session.commit()
    except Exception as exc:  # never break the canonical revoke; surface loudly for reconciliation
        logger.error("Envelope delete failed for credential %s (owner %s): %s", sqlite_id, owner_id, exc)
