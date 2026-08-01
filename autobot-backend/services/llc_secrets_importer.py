# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Import LLC company secrets into the unified envelope store (#10088 / Task 4).

Additive, one-shot migration mirroring ``sqlite_secrets_importer.py`` /
``json_secrets_importer.py`` (Task 3): reads active rows from the legacy
``llc_secrets`` table (``llc.models.secret.LLCSecret`` / ``llc.services.secret.
SecretService``, per-company HKDF+Fernet), decrypts each with its
company-derived Fernet key, and **creates** a new envelope-backed row owned by
that LLC company's vault (``company:<company_id>`` — ``VaultKind.COMPANY``).

Unlike the JSON/SQLite stores, ``llc_secrets`` already lives in the same
PostgreSQL database as the unified ``secrets`` table, so this importer reads
it through the same ``AsyncSession`` rather than a separate file/connection.

Owner mapping: an LLC secret has no single human owner — ``created_by_
agent_id`` names an *agent*, not a ``user_management`` user, and the umbrella
governs company vaults by LLC membership, not by a personal owner. The
envelope ``Secret.owner_id`` column is NOT NULL with no FK, so imported rows
use the same sentinel service-owner UUID as other vault-owned (non-personal)
imports (see ``services/secrets_coordinator.py``'s ``_SERVICE_OWNER_ID`` and
``json_secrets_importer.py``'s ``_SYSTEM_OWNER_ID``).

Only **active** (``revoked_at IS NULL``) rows are imported — a revoked legacy
secret has no live reader and importing it would let a stale copy resurrect
through the unified store. ``(company_id, name)`` is unique in ``llc_secrets``
and reactivation reuses the same row id, so the marker keyed on the legacy
row's id is stable across revoke/re-set cycles.

Idempotent via ``extra_data['imported_from_llc_secrets']`` (the legacy row's
UUID). Run inside one transaction and ``commit()`` the session once
afterwards, exactly like the other two importers. ``llc_secrets`` and
``llc/services/secret.py`` are left fully intact — this populates the unified
store so the dual-read path (``services/llc_secrets_read.py``) can serve reads
from it while ``llc_secrets`` stays authoritative for writes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.legacy_secret_keys import derive_llc_company_fernet
from autobot_shared.secrets_envelope import derive_vault_key, seal, wrap_dek
from autobot_shared.secrets_vault import VaultKind, VaultRef
from llc.models.secret import LLCSecret
from models.secret import Secret, SecretType
from models.secret_grant import SecretGrant

_MARKER = "imported_from_llc_secrets"

#: Sentinel owner for vault-owned (no human owner) secrets — matches the
#: convention in ``services/secrets_coordinator.py`` (``_SERVICE_OWNER_ID``) and
#: ``json_secrets_importer.py`` (``_SYSTEM_OWNER_ID``); ``Secret.owner_id`` is
#: NOT NULL and an LLC company secret has no single per-user owner.
_COMPANY_OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@dataclass
class LlcImportReport:
    """Reconciliation counts for one import run."""

    total: int = 0
    imported: int = 0
    skipped_existing: int = 0
    failed: list[str] = field(default_factory=list)


async def _read_active_rows(session: AsyncSession) -> list[LLCSecret]:
    """Return active (non-revoked) llc_secrets rows, ordered for deterministic runs."""
    result = await session.execute(
        select(LLCSecret).where(LLCSecret.revoked_at.is_(None)).order_by(LLCSecret.company_id, LLCSecret.name)
    )
    return list(result.scalars().all())


async def _existing_markers(session: AsyncSession) -> set[str]:
    """Source (legacy) row ids already imported (so a re-run is idempotent)."""
    marker = Secret.extra_data[_MARKER].astext
    rows = (await session.execute(select(marker).where(marker.isnot(None)))).scalars().all()
    return {r for r in rows if r}


def _build_secret_grant(row: LLCSecret, plaintext: bytes, root_key: bytes) -> tuple[Secret, SecretGrant]:
    """Seal *plaintext* and build the Company-vault ``Secret`` + owner grant for a legacy row."""
    new_id = uuid.uuid4()
    sid = str(new_id)
    vault = VaultRef(VaultKind.COMPANY, row.company_id)
    sealed, dek = seal(plaintext, secret_id=sid)
    wrapped = wrap_dek(dek, derive_vault_key(root_key, vault.to_str()), vault.to_str(), secret_id=sid)
    secret = Secret(
        id=new_id,
        owner_id=_COMPANY_OWNER_ID,
        name=row.name,
        type=SecretType.OTHER.value,
        scope=VaultKind.COMPANY.value,
        owner_vault=vault.to_str(),
        sealed_value=sealed.to_dict(),
        version=1,
        extra_data={
            _MARKER: str(row.id),
            "legacy_company_id": row.company_id,
            "legacy_version": row.version,
            "legacy_created_by_agent_id": row.created_by_agent_id,
        },
    )
    grant = SecretGrant(secret_id=new_id, grantee=vault.to_str(), wrapped_dek=wrapped.to_dict(), created_by=None)
    return secret, grant


async def import_llc_secrets(session: AsyncSession, *, master_key: bytes, root_key: bytes) -> LlcImportReport:
    """Import every active ``llc_secrets`` row into the unified store, owned by its Company vault.

    ``master_key`` is the raw ``LLC_SECRET_MASTER_KEY`` bytes (the same input
    ``llc.services.secret.SecretService._get_master_key()`` reads from env); each
    row is decrypted with its own company-derived Fernet key, mirroring the live
    service exactly. ``root_key`` is the envelope root key
    (``AUTOBOT_SECRETS_ROOT_KEY``). Returns a reconciliation report; caller commits.
    """
    from cryptography.fernet import InvalidToken

    report = LlcImportReport()
    rows = await _read_active_rows(session)
    report.total = len(rows)
    already = await _existing_markers(session)

    for row in rows:
        src = str(row.id)
        if src in already:
            report.skipped_existing += 1
            continue
        try:
            plaintext = derive_llc_company_fernet(master_key, row.company_id).decrypt(row.value)
        except (InvalidToken, ValueError, TypeError) as exc:
            report.failed.append(f"{src}: decrypt failed ({exc})")
            continue
        try:
            # Per-row SAVEPOINT so one bad row (a UNIQUE grant collision, dirty
            # data that overflows a PG column, etc.) is reported and skipped
            # without aborting the whole batch.
            async with session.begin_nested():
                secret, grant = _build_secret_grant(row, plaintext, root_key)
                session.add(secret)
                session.add(grant)
                await session.flush()
            report.imported += 1
        except SQLAlchemyError as exc:
            report.failed.append(f"{src}: persist failed ({exc})")

    return report
