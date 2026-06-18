# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migrate legacy Fernet ``secrets`` rows onto the envelope store (#10088 / Task 3a).

In-place conversion of the PostgreSQL ``secrets`` table: rows written the old way
(``encrypted_value`` = Fernet ciphertext, ``sealed_value`` NULL) are decrypted
with the legacy Fernet key and re-sealed under the envelope crypto
(``autobot_shared.secrets_envelope``), keeping the same row id. This store has no
live readers/writers (the envelope path is already authoritative for PG writes),
so there is no cutover risk — it's the reusable conversion + reconciliation core
the JSON/SQLite cutovers (separate, higher-risk slices) build on.

Idempotent (the query only selects un-converted rows) and conservative:
``encrypted_value`` is **kept** so a row can be rolled back / re-verified until a
later cleanup slice nulls it.

Legacy scope → vault mapping:
- ``user`` / ``session`` / ``workflow`` → owner ``user:<owner_id>``
- ``organization`` → owner ``company:<org_id>`` (falls back to the creator's user
  vault if ``org_id`` is unset)
- ``shared`` → owner ``user:<owner_id>`` + a grant per ``shared_with`` user
- ``group`` → owner ``user:<owner_id>`` + a grant per ``team_ids`` team
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.secrets_envelope import derive_vault_key, seal, wrap_dek
from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret
from models.secret_grant import SecretGrant


@dataclass
class MigrationReport:
    """Reconciliation counts for one migration run."""

    total_legacy: int = 0
    migrated: int = 0
    failed: list[str] = field(default_factory=list)


def _owner_and_extra_grantees(secret: Secret) -> tuple[VaultRef, list[VaultRef]]:
    """Map a legacy row's scope/ownership to an owner vault + extra grantee vaults."""
    if secret.scope == "organization" and secret.org_id is not None:
        owner = VaultRef(VaultKind.COMPANY, str(secret.org_id))
    else:
        owner = VaultRef(VaultKind.USER, str(secret.owner_id))

    extra: list[VaultRef] = []
    if secret.scope == "shared":
        extra += [VaultRef(VaultKind.USER, str(u)) for u in (secret.shared_with or [])]
    if secret.scope == "group":
        extra += [VaultRef(VaultKind.TEAM, str(t)) for t in (secret.team_ids or [])]
    return owner, extra


def _prepare_envelope(secret: Secret, plaintext: bytes, root_key: bytes) -> tuple[dict, str, list[SecretGrant]]:
    """Seal *plaintext* and build the grant rows for *secret*. Raises (before any row mutation)
    on a bad vault id, so a partial conversion never persists."""
    sid = str(secret.id)
    sealed, dek = seal(plaintext, secret_id=sid)
    owner, extra = _owner_and_extra_grantees(secret)
    grants: list[SecretGrant] = []
    seen: set[str] = set()
    for grantee in (owner, *extra):
        key = grantee.to_str()
        if key in seen:
            continue
        seen.add(key)
        wrapped = wrap_dek(dek, derive_vault_key(root_key, key), key, secret_id=sid)
        grants.append(
            SecretGrant(secret_id=secret.id, grantee=key, wrapped_dek=wrapped.to_dict(), created_by=secret.owner_id)
        )
    return sealed.to_dict(), owner.to_str(), grants


async def migrate_pg_legacy_secrets(session: AsyncSession, *, fernet, root_key: bytes) -> MigrationReport:
    """Convert every legacy Fernet row in ``secrets`` to envelope form. Returns a reconciliation report.

    ``fernet`` is a ``cryptography.fernet.Fernet`` (or MultiFernet) built from the legacy
    ``AUTOBOT_SECRETS_KEY``; ``root_key`` is the envelope root key (``AUTOBOT_SECRETS_ROOT_KEY``).
    """
    from cryptography.fernet import InvalidToken

    report = MigrationReport()
    # Filter "not yet envelope-backed" in Python (``sealed_value is None``) to match
    # exactly how UnifiedSecretsService detects legacy rows. A SQL ``sealed_value IS
    # NULL`` would miss rows whose JSONB holds JSON ``null`` (not SQL NULL) — SQLAlchemy's
    # JSONB defaults to none_as_null=False, so an explicit None persists as JSON null.
    rows = (await session.execute(select(Secret).where(Secret.encrypted_value.isnot(None)))).scalars().all()
    candidates = [s for s in rows if s.sealed_value is None]
    report.total_legacy = len(candidates)

    for secret in candidates:
        try:
            plaintext = fernet.decrypt(secret.encrypted_value.encode("utf-8"))
        except (InvalidToken, ValueError) as exc:
            report.failed.append(f"{secret.id}: decrypt failed ({exc})")
            continue
        try:
            sealed_dict, owner_vault, grants = _prepare_envelope(secret, plaintext, root_key)
        except ValueError as exc:  # bad vault id from corrupt scope data — row left untouched
            report.failed.append(f"{secret.id}: convert failed ({exc})")
            continue
        secret.sealed_value = sealed_dict
        secret.owner_vault = owner_vault
        secret.version = secret.version or 1
        for grant in grants:
            session.add(grant)
        report.migrated += 1

    await session.flush()
    return report
