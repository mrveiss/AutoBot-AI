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

Conservative: ``encrypted_value`` is **kept** so a row can be rolled back /
re-verified until a later cleanup slice nulls it.

Transaction contract: call inside a single transaction and ``commit()`` the
session once afterwards. Each row is converted inside its own SAVEPOINT, so a
single bad row is reported and skipped without poisoning the batch. Idempotent
across runs — a re-run skips rows that already carry a ``sealed_value`` (the
seal + its grants commit together within one savepoint, so a converted row never
re-seals or double-grants).

Legacy scope → vault mapping:
- ``user`` / ``session`` / ``workflow`` (and any unknown scope) → owner ``user:<owner_id>``
- ``organization`` → owner ``company:<org_id>`` (falls back to the creator's user
  vault if ``org_id`` is unset — recorded in the report's ``warnings``)
- ``shared`` → owner ``user:<owner_id>`` + a grant per ``shared_with`` user
- ``group`` → owner ``user:<owner_id>`` + a grant per ``team_ids`` team
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.secrets_envelope import derive_vault_key, seal, wrap_dek
from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret
from models.secret_grant import SecretGrant

if TYPE_CHECKING:  # avoid a hard import at module load; only used for typing
    from cryptography.fernet import Fernet, MultiFernet


@dataclass
class MigrationReport:
    """Reconciliation counts for one migration run."""

    total_legacy: int = 0
    migrated: int = 0
    failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _grantee_vaults(values, kind: VaultKind, field_name: str) -> list[VaultRef]:
    """Build grantee vaults from a legacy JSONB list field. Raises on dirty (non-list) data
    so the row is reported rather than silently mis-granted (iterating a str/dict)."""
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} is not a list: {type(values).__name__}")
    return [VaultRef(kind, str(v)) for v in values]


def _owner_and_extra_grantees(secret: Secret) -> tuple[VaultRef, list[VaultRef], str | None]:
    """Map a legacy row's scope/ownership to an owner vault + extra grantee vaults.

    Returns ``(owner, extra, warning)`` — ``warning`` is set when an organization-scoped
    secret lacks ``org_id`` and is demoted to the creator's personal vault.
    """
    warning: str | None = None
    if secret.scope == "organization" and secret.org_id is not None:
        owner = VaultRef(VaultKind.COMPANY, str(secret.org_id))
    else:
        owner = VaultRef(VaultKind.USER, str(secret.owner_id))
        if secret.scope == "organization":
            warning = f"{secret.id}: organization scope with no org_id → demoted to owner user vault"

    extra: list[VaultRef] = []
    if secret.scope == "shared":
        extra += _grantee_vaults(secret.shared_with, VaultKind.USER, "shared_with")
    if secret.scope == "group":
        extra += _grantee_vaults(secret.team_ids, VaultKind.TEAM, "team_ids")
    return owner, extra, warning


def _prepare_envelope(
    secret: Secret, plaintext: bytes, root_key: bytes
) -> tuple[dict, str, list[SecretGrant], str | None]:
    """Seal *plaintext* and build the grant rows for *secret*. Raises (before any row mutation)
    on dirty scope data, so a partial conversion never persists."""
    sid = str(secret.id)
    sealed, dek = seal(plaintext, secret_id=sid)
    owner, extra, warning = _owner_and_extra_grantees(secret)
    grants: list[SecretGrant] = []
    seen: set[str] = set()
    for grantee in (owner, *extra):
        key = grantee.to_str()
        if key in seen:  # e.g. owner also listed in shared_with — avoid UNIQUE(secret_id,grantee)
            continue
        seen.add(key)
        wrapped = wrap_dek(dek, derive_vault_key(root_key, key), key, secret_id=sid)
        grants.append(
            SecretGrant(secret_id=secret.id, grantee=key, wrapped_dek=wrapped.to_dict(), created_by=secret.owner_id)
        )
    return sealed.to_dict(), owner.to_str(), grants, warning


async def migrate_pg_legacy_secrets(
    session: AsyncSession, *, fernet: "Fernet | MultiFernet", root_key: bytes
) -> MigrationReport:
    """Convert every legacy Fernet row in ``secrets`` to envelope form. Returns a reconciliation report.

    ``fernet`` is a ``cryptography.fernet.Fernet`` (or MultiFernet) built from the legacy
    ``AUTOBOT_SECRETS_KEY``; ``root_key`` is the envelope root key (``AUTOBOT_SECRETS_ROOT_KEY``).
    See the module docstring for the transaction contract.
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
        except (InvalidToken, ValueError, TypeError) as exc:
            report.failed.append(f"{secret.id}: decrypt failed ({exc})")
            continue
        try:
            sealed_dict, owner_vault, grants, warning = _prepare_envelope(secret, plaintext, root_key)
        except ValueError as exc:  # dirty scope data — row left untouched
            report.failed.append(f"{secret.id}: convert failed ({exc})")
            continue
        try:
            # Per-row SAVEPOINT: one bad row (e.g. a UNIQUE grant collision from a prior
            # partial run) is reported and skipped without aborting the whole batch.
            async with session.begin_nested():
                secret.sealed_value = sealed_dict
                secret.owner_vault = owner_vault
                if secret.version is None:
                    secret.version = 1
                session.add_all(grants)
                await session.flush()
        except IntegrityError as exc:
            report.failed.append(f"{secret.id}: persist failed ({exc})")
            continue
        if warning:
            report.warnings.append(warning)
        report.migrated += 1

    return report
