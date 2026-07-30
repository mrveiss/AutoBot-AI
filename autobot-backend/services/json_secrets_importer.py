# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Import the legacy JSON file secrets store into the unified envelope store (#10088 / Task 3).

Additive, one-shot migration mirroring ``sqlite_secrets_importer.py`` (Task 3c) for the
last of the three legacy stores the umbrella names: the ``secrets.json`` file store behind
``api/secrets.py`` + ``SecretsManager.vue``. Every row there is created through an
admin-only endpoint (``check_admin_permission`` on every route) and carries **no owner_id**
— ``SecretCreateRequest.owner_id`` is accepted but silently dropped by
``SecretCreateRequest.to_secret_model()`` (a pre-existing gap, filed separately). Since
there is no reliable per-user owner to assign, every imported secret is owned by the
**System vault** (admin-only) — this exactly preserves today's real-world access control
(only an admin can reach these endpoints) instead of fabricating a personal owner.

Idempotent via ``extra_data['imported_from_json']``; legacy scope/chat_id/metadata are
preserved in ``extra_data`` so ``json_secrets_read.py`` can reconstruct the exact response
shape the legacy ``GET /secrets/{id}`` handler returns. The JSON file is left intact — this
populates and lets us verify the unified store before dual-read is enabled.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.secrets_envelope import derive_vault_key, seal, wrap_dek
from autobot_shared.secrets_vault import VaultKind, VaultRef
from autobot_shared.time_utils import parse_utc_iso
from models.secret import Secret
from models.secret_grant import SecretGrant

_MARKER = "imported_from_json"

#: Sentinel owner for vault-owned (no human owner) secrets — matches the service-principal
#: convention in ``services/secrets_coordinator.py`` (``_SERVICE_OWNER_ID``); ``Secret.owner_id``
#: is NOT NULL and there is no real per-user owner for this ownerless, admin-only store.
_SYSTEM_OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@dataclass
class JsonImportReport:
    """Reconciliation counts for one import run."""

    total: int = 0
    imported: int = 0
    skipped_existing: int = 0
    failed: list[str] = field(default_factory=list)


async def _existing_markers(session: AsyncSession) -> set[str]:
    """Source ids already imported (so a re-run is idempotent)."""
    marker = Secret.extra_data[_MARKER].astext
    rows = (await session.execute(select(marker).where(marker.isnot(None)))).scalars().all()
    return {r for r in rows if r}


def _parse_expires_at(value):
    """Coerce the legacy row's ``expires_at`` (ISO string, datetime, or None) to a datetime."""
    if not value or hasattr(value, "isoformat"):
        return value or None
    return parse_utc_iso(str(value))


def _build_secret_grant(row: dict, plaintext: bytes, root_key: bytes) -> tuple[Secret, SecretGrant]:
    """Seal *plaintext* and build the System-vault ``Secret`` + owner grant for a legacy JSON row."""
    new_id = uuid.uuid4()
    sid = str(new_id)
    vault = VaultRef(VaultKind.SYSTEM)
    sealed, dek = seal(plaintext, secret_id=sid)
    wrapped = wrap_dek(dek, derive_vault_key(root_key, vault.to_str()), vault.to_str(), secret_id=sid)
    secret = Secret(
        id=new_id,
        owner_id=_SYSTEM_OWNER_ID,
        name=row["name"],
        type=row["type"],
        scope=VaultKind.SYSTEM.value,
        owner_vault=vault.to_str(),
        sealed_value=sealed.to_dict(),
        version=1,
        description=row.get("description"),
        tags=row.get("tags") or [],
        expires_at=_parse_expires_at(row.get("expires_at")),
        extra_data={
            _MARKER: str(row["id"]),
            "legacy_scope": row.get("scope"),
            "legacy_chat_id": row.get("chat_id"),
            "legacy_metadata": row.get("metadata") or {},
        },
    )
    grant = SecretGrant(secret_id=new_id, grantee=vault.to_str(), wrapped_dek=wrapped.to_dict(), created_by=None)
    return secret, grant


async def import_json_secrets(session: AsyncSession, *, root_key: bytes) -> JsonImportReport:
    """Import every ``secrets.json`` row into the unified store, owned by the System vault.

    Reads + decrypts via the process-wide ``api.secrets.secrets_manager`` singleton (the same
    file and key it already manages) so no second Fernet key path is introduced. Returns a
    reconciliation report; caller commits.
    """
    from api.secrets import secrets_manager

    report = JsonImportReport()
    rows = secrets_manager._load_secrets()
    report.total = len(rows)
    already = await _existing_markers(session)

    for secret_id, row in rows.items():
        if secret_id in already:
            report.skipped_existing += 1
            continue
        cipher = row.get("encrypted_value")
        if not cipher:
            report.failed.append(f"{secret_id}: no encrypted_value")
            continue
        try:
            plaintext = secrets_manager._decrypt_value(cipher).encode("utf-8")
        except (InvalidToken, ValueError, TypeError) as exc:
            report.failed.append(f"{secret_id}: decrypt failed ({exc})")
            continue
        try:
            # Per-row SAVEPOINT so one bad row (dirty data that overflows a PG column, a
            # UNIQUE grant collision, etc.) is reported and skipped, not an end-of-batch
            # IntegrityError/DataError aborting the whole batch.
            async with session.begin_nested():
                secret, grant = _build_secret_grant({**row, "id": secret_id}, plaintext, root_key)
                session.add(secret)
                session.add(grant)
                await session.flush()
            report.imported += 1
        except SQLAlchemyError as exc:
            report.failed.append(f"{secret_id}: persist failed ({exc})")

    return report
