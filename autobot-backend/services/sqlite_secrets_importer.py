# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Import the legacy SQLite secrets store into the unified envelope store (#10088 / Task 3c).

Additive, one-shot migration: reads the legacy SQLite ``secrets`` table
(``services.secrets_service.SecretsService`` / ``secrets.db``), decrypts each
value with the legacy Fernet key, and **creates** a new envelope-backed row in
the PostgreSQL unified store owned by the creator's user vault. The SQLite store
is left intact — this populates and lets us verify the unified store *before* the
separate reader-cutover slice repoints ConnectorCredentialStore / WorkflowSecretService
/ AgentSecretsIntegration off SQLite.

Owner mapping: a row's ``created_by`` (the creator's user id) → owner ``user:<created_by>``.
The PG ``owner_id`` column carries no DB-level FK, so the only owner requirement is
that ``created_by`` parse as a UUID; rows with a missing or non-UUID ``created_by``
are **skipped and reported** rather than given a fabricated owner. The legacy
``scope``/``chat_id`` are preserved in ``extra_data`` for traceability.

Idempotent: each imported row records its source id in ``extra_data['imported_from_sqlite']``;
a re-run skips source ids already present. Run inside one transaction and ``commit()`` once.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.secrets_envelope import derive_vault_key, seal, wrap_dek
from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret
from models.secret_grant import SecretGrant

if TYPE_CHECKING:  # typing only — avoid a hard cryptography import at module load
    from cryptography.fernet import Fernet, MultiFernet

_MARKER = "imported_from_sqlite"


@dataclass
class ImportReport:
    """Reconciliation counts for one import run."""

    total: int = 0
    imported: int = 0
    skipped_existing: int = 0
    failed: list[str] = field(default_factory=list)


def _read_active_rows(sqlite_path: str) -> list[dict]:
    """Read active rows from the legacy SQLite secrets store (sync, one-shot)."""
    conn = sqlite3.connect(sqlite_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, name, description, secret_type, encrypted_value, scope, chat_id, created_by "
            "FROM secrets WHERE is_active = 1"
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


async def _existing_markers(session: AsyncSession) -> set[str]:
    """Source ids already imported (so a re-run is idempotent)."""
    marker = Secret.extra_data[_MARKER].astext
    rows = (await session.execute(select(marker).where(marker.isnot(None)))).scalars().all()
    return {r for r in rows if r}


def _build_secret_grant(row: dict, plaintext: bytes, owner: uuid.UUID, root_key: bytes) -> tuple[Secret, SecretGrant]:
    """Seal *plaintext* and build the new vault Secret + owner grant for a legacy SQLite row."""
    new_id = uuid.uuid4()
    sid = str(new_id)
    vault = VaultRef(VaultKind.USER, str(owner))
    sealed, dek = seal(plaintext, secret_id=sid)
    wrapped = wrap_dek(dek, derive_vault_key(root_key, vault.to_str()), vault.to_str(), secret_id=sid)
    secret = Secret(
        id=new_id,
        owner_id=owner,
        name=row["name"],
        type=row["secret_type"],
        scope=VaultKind.USER.value,
        owner_vault=vault.to_str(),
        sealed_value=sealed.to_dict(),
        version=1,
        description=row.get("description"),
        extra_data={_MARKER: str(row["id"]), "legacy_scope": row.get("scope"), "legacy_chat_id": row.get("chat_id")},
    )
    grant = SecretGrant(secret_id=new_id, grantee=vault.to_str(), wrapped_dek=wrapped.to_dict(), created_by=owner)
    return secret, grant


async def import_sqlite_secrets(
    session: AsyncSession, *, sqlite_path: str, fernet: "Fernet | MultiFernet", root_key: bytes
) -> ImportReport:
    """Import the legacy SQLite secrets store into the unified store. Returns a reconciliation report.

    ``fernet`` is a ``cryptography.fernet.Fernet`` built from the legacy ``AUTOBOT_SECRETS_KEY``;
    ``root_key`` is the envelope root key. See the module docstring for the transaction contract.
    """
    from cryptography.fernet import InvalidToken

    report = ImportReport()
    rows = _read_active_rows(sqlite_path)
    report.total = len(rows)
    already = await _existing_markers(session)

    for row in rows:
        src = str(row["id"])
        if src in already:
            report.skipped_existing += 1
            continue
        owner_raw = row.get("created_by")
        if not owner_raw:
            report.failed.append(f"{src}: no created_by (owner)")
            continue
        try:
            owner = uuid.UUID(str(owner_raw))
        except ValueError:
            report.failed.append(f"{src}: created_by not a uuid ({owner_raw!r})")
            continue
        cipher = row.get("encrypted_value")
        if not cipher:
            report.failed.append(f"{src}: no encrypted_value")
            continue
        try:
            plaintext = fernet.decrypt(cipher.encode("utf-8"))
        except (InvalidToken, ValueError, TypeError) as exc:
            report.failed.append(f"{src}: decrypt failed ({exc})")
            continue
        try:
            # Per-row SAVEPOINT so one bad row (FK/unique violation, or dirty data
            # that overflows a PG column → DataError) is reported without aborting the batch.
            async with session.begin_nested():
                secret, grant = _build_secret_grant(row, plaintext, owner, root_key)
                session.add(secret)
                session.add(grant)
                await session.flush()
            report.imported += 1
        except SQLAlchemyError as exc:
            report.failed.append(f"{src}: persist failed ({exc})")

    return report
