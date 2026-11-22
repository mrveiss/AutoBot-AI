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

#: The envelope-store name prefix reserved for connector credentials (#17850); the one definition. Only this
#: module's writer creates or rotates such names -- user-facing create/rename refuse it (``services.secret_names``).
CONNECTOR_NAME_PREFIX = "connector:"


def connector_secret_name(connector_id: str) -> str:
    """The envelope-store name of *connector_id*'s credential."""
    return f"{CONNECTOR_NAME_PREFIX}{connector_id}:auth"


async def _find_by_marker(session, sqlite_id: str, owner_uuid):
    from sqlalchemy import select

    from models.secret import Secret

    marker = Secret.extra_data[_MARKER].astext
    return (
        (
            await session.execute(
                select(Secret).where(
                    marker == str(sqlite_id),
                    Secret.owner_id == owner_uuid,
                    Secret.is_active.is_(True),
                )
            )
        )
        .scalars()
        .first()
    )


async def mirror_in_session(
    session,
    sqlite_id: str,
    owner_id: str,
    value: str,
    root_key: bytes,
    *,
    name=None,
    secret_type=None,
) -> None:
    """Testable core: upsert the envelope copy within *session* (caller commits).

    Rotates an existing copy (matched by marker + owner); creates one when absent and
    ``name``/``secret_type`` are supplied (the create paths). Owner not a uuid → no-op.
    """
    ctx = _mirror_context(owner_id, root_key)
    if ctx is None:
        return  # owner isn't a uuid → cannot key an envelope row
    owner_uuid, vault, svc = ctx
    row = await _find_by_marker(session, sqlite_id, owner_uuid)
    if row is None and name and secret_type:
        await _upsert_by_name(session, svc, vault, owner_uuid, sqlite_id, value, name, secret_type)
    else:
        await _rotate_or_skip(session, svc, vault, row, sqlite_id, value)


def _mirror_context(owner_id: str, root_key: bytes):
    """``(owner_uuid, vault, service)`` for *owner_id*, or None when it is not a uuid."""
    import uuid

    from autobot_shared.secrets_vault import VaultKind, VaultRef
    from services.envelope_secrets_service import EnvelopeSecretsService

    try:
        owner_uuid = uuid.UUID(str(owner_id))
    except ValueError:
        return None
    return owner_uuid, VaultRef(VaultKind.USER, str(owner_id)), EnvelopeSecretsService(root_key=root_key)


async def _rotate_or_skip(session, svc, vault, row, sqlite_id: str, value: str) -> None:
    """Rotate the marked envelope copy *row*; with no copy and nothing to create one from, skip."""
    if row is None:
        logger.debug("No envelope copy for the credential and no name/type to create one — skipping mirror")
        return
    await svc.rotate_value(
        session,
        secret_id=row.id,
        new_plaintext=value.encode("utf-8"),
        actor_vaults={vault},
    )


def _adoptable(existing, secret_type, sqlite_id) -> str | None:
    """None when *existing* is safe to adopt as this credential's mirror, else the failed condition."""
    if not existing.is_live:
        return "inactive"
    if existing.type != secret_type:
        return "type_differs"
    marker = (existing.extra_data or {}).get(_MARKER)
    if marker is not None and marker != str(sqlite_id):
        return "marked_for_another_credential"
    return None


async def _stamp_marker(session, target, sqlite_id: str) -> None:
    """Mark *target* as the envelope copy of credential *sqlite_id* (the key the read path resolves)."""
    target.extra_data = {**(target.extra_data or {}), _MARKER: str(sqlite_id)}
    await session.flush()


async def _upsert_by_name(session, svc, vault, owner_uuid, sqlite_id, value, name, secret_type) -> None:
    """No marker row: adopt a same-name row of THIS vault only when safe, else create; never overwrite blindly.

    ``find_by_name`` is scoped to the vault; several rows raise ``AmbiguousSecretError`` (nothing written). A
    same-name row is rotated and marked only when active, of this secret type, and unmarked (or marked for this
    credential); otherwise nothing is written (a deactivated row is never revived). Names and values are not logged.
    """
    plaintext = value.encode("utf-8")
    existing = await svc.find_by_name(session, owner_vault=vault.to_str(), name=name)
    if existing is not None:
        if (refusal := _adoptable(existing, secret_type, sqlite_id)) is not None:
            logger.warning("Envelope mirror skipped: same-name row not adoptable (%s)", refusal)
            return
        await svc.rotate_value(
            session,
            secret_id=existing.id,
            new_plaintext=plaintext,
            actor_vaults={vault},
        )
        target = existing
    else:
        target = await svc.create(
            session,
            owner_vault=vault,
            name=name,
            secret_type=secret_type,
            plaintext=plaintext,
            created_by=owner_uuid,
        )
    await _stamp_marker(session, target, sqlite_id)


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


async def mirror_credential_to_vault(sqlite_id: str, owner_id: str, value: str, *, name=None, secret_type=None) -> None:
    """Best-effort upsert of a credential's envelope vault copy. Never raises."""
    try:
        root_key = _root_key_or_none()
        if root_key is None:
            return
        from user_management.database import get_async_session_factory

        async with get_async_session_factory()() as session:
            await mirror_in_session(
                session,
                sqlite_id,
                owner_id,
                value,
                root_key,
                name=name,
                secret_type=secret_type,
            )
            await session.commit()
    except Exception as exc:  # dual-write must never break the canonical SQLite write
        # Neither the exception text (it can echo the value being written) nor the credential's
        # identifiers are logged; the canonical SQLite row is intact and the mirror retries on write.
        logger.warning("Envelope mirror failed for one credential: %s", type(exc).__name__)


async def delete_credential_from_vault(sqlite_id: str, owner_id: str) -> None:
    """Best-effort delete of a credential's envelope vault copy by marker. Never raises.

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
        # Class only, no identifiers or exception text (same convention as the mirror failure above). The stale
        # copy stays findable for reconciliation by its ``imported_from_sqlite`` marker with no SQLite row.
        logger.error("Envelope delete failed for one credential (stale envelope copy remains): %s", type(exc).__name__)
