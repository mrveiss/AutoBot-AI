# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unified envelope SecretsService — CRUD + sharing orchestration (#10088 / Task 2.2).

Orchestrates the envelope crypto (``autobot_shared.secrets_envelope``) over the
``secrets`` + ``secret_grants`` schema (Task 2.1) using the canonical vault
namespace (``autobot_shared.secrets_vault``):

- **create**  seal the value once under a fresh DEK; wrap the DEK for the owner
  vault → one ``secrets`` row + one owner ``secret_grants`` row.
- **read**    find a grant whose grantee is one of the caller's accessible
  vaults; unwrap that DEK and open the value.
- **share**   recover the DEK via a vault the actor already holds, wrap it for
  the new grantee → an extra grant (no re-encrypt, no plaintext copy).
- **revoke**  drop one grant. **rotate** re-seal with a new DEK and re-wrap
  every grant. **delete** removes the secret (grants cascade).

This service is **policy-free**: callers pass the already-resolved set of vaults
they may use (``accessible_vaults`` / ``actor_vaults``). The RBAC layer that
computes those sets from user/agent identity + membership is Task 2.3 / 9.2.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.secrets_envelope import (
    SealedSecret,
    WrappedDek,
    derive_vault_key,
    load_root_key,
    open_secret,
    seal,
    unwrap_dek,
    wrap_dek,
)
from autobot_shared.secrets_vault import VaultRef
from models.secret import Secret
from models.secret_grant import SecretGrant


class SecretNotFoundError(Exception):
    """The secret does not exist (or is not envelope-backed)."""


class SecretAccessError(PermissionError):
    """The caller holds no grant for any of their accessible vaults."""


def _vault_strs(vaults: Iterable[VaultRef]) -> set[str]:
    return {v.to_str() for v in vaults}


class UnifiedSecretsService:
    """Envelope CRUD + sharing over ``secrets`` / ``secret_grants``."""

    def __init__(self, root_key: bytes | None = None) -> None:
        self._root = root_key if root_key is not None else load_root_key()

    def _kek(self, vault_str: str) -> bytes:
        return derive_vault_key(self._root, vault_str)

    async def create(
        self,
        session: AsyncSession,
        *,
        owner_vault: VaultRef,
        name: str,
        secret_type: str,
        plaintext: bytes,
        created_by: uuid.UUID,
    ) -> Secret:
        """Seal *plaintext* for *owner_vault* and persist the secret + owner grant."""
        secret_id = uuid.uuid4()
        sid = str(secret_id)
        sealed, dek = seal(plaintext, secret_id=sid)
        wrapped = wrap_dek(dek, self._kek(owner_vault.to_str()), owner_vault.to_str(), secret_id=sid)
        secret = Secret(
            id=secret_id,
            owner_id=created_by,
            name=name,
            type=secret_type,
            scope=owner_vault.kind.value,
            owner_vault=owner_vault.to_str(),
            sealed_value=sealed.to_dict(),
            version=1,
        )
        session.add(secret)
        session.add(
            SecretGrant(
                secret_id=secret_id,
                grantee=owner_vault.to_str(),
                wrapped_dek=wrapped.to_dict(),
                created_by=created_by,
            )
        )
        await session.flush()
        return secret

    async def _load(self, session: AsyncSession, secret_id: uuid.UUID) -> Secret:
        secret = await session.get(Secret, secret_id)
        if secret is None or secret.sealed_value is None:
            raise SecretNotFoundError(f"envelope secret {secret_id} not found")
        return secret

    async def _grants(self, session: AsyncSession, secret_id: uuid.UUID) -> list[SecretGrant]:
        rows = await session.execute(select(SecretGrant).where(SecretGrant.secret_id == secret_id))
        return list(rows.scalars())

    def _recover_dek(self, secret: Secret, grant: SecretGrant) -> bytes:
        return unwrap_dek(WrappedDek.from_dict(grant.wrapped_dek), self._kek(grant.grantee), secret_id=str(secret.id))

    async def read(
        self, session: AsyncSession, *, secret_id: uuid.UUID, accessible_vaults: Iterable[VaultRef]
    ) -> bytes:
        """Decrypt the value via any grant whose grantee is in *accessible_vaults*."""
        secret = await self._load(session, secret_id)
        allowed = _vault_strs(accessible_vaults)
        for grant in await self._grants(session, secret_id):
            if grant.grantee in allowed:
                sealed = SealedSecret.from_dict(secret.sealed_value)
                return open_secret(
                    sealed, WrappedDek.from_dict(grant.wrapped_dek), self._kek(grant.grantee), secret_id=str(secret_id)
                )
        raise SecretAccessError(f"no accessible grant for secret {secret_id}")

    async def _dek_via(self, session: AsyncSession, secret: Secret, actor_vaults: Iterable[VaultRef]) -> bytes:
        allowed = _vault_strs(actor_vaults)
        for grant in await self._grants(session, secret.id):
            if grant.grantee in allowed:
                return self._recover_dek(secret, grant)
        raise SecretAccessError(f"actor cannot open secret {secret.id} to act on it")

    async def share(
        self,
        session: AsyncSession,
        *,
        secret_id: uuid.UUID,
        actor_vaults: Iterable[VaultRef],
        grantee: VaultRef,
        created_by: uuid.UUID,
    ) -> SecretGrant:
        """Grant *grantee* access by wrapping the same DEK for its vault (idempotent rewrap)."""
        secret = await self._load(session, secret_id)
        dek = await self._dek_via(session, secret, actor_vaults)
        wrapped = wrap_dek(dek, self._kek(grantee.to_str()), grantee.to_str(), secret_id=str(secret_id))
        existing = next((g for g in await self._grants(session, secret_id) if g.grantee == grantee.to_str()), None)
        if existing is not None:
            existing.wrapped_dek = wrapped.to_dict()
            grant = existing
        else:
            grant = SecretGrant(
                secret_id=secret_id, grantee=grantee.to_str(), wrapped_dek=wrapped.to_dict(), created_by=created_by
            )
            session.add(grant)
        await session.flush()
        return grant

    async def revoke(self, session: AsyncSession, *, secret_id: uuid.UUID, grantee: VaultRef) -> None:
        """Drop a grant. The owner grant cannot be revoked (delete the secret instead)."""
        secret = await self._load(session, secret_id)
        if secret.owner_vault == grantee.to_str():
            raise ValueError("cannot revoke the owner grant; delete the secret instead")
        await session.execute(
            delete(SecretGrant).where(SecretGrant.secret_id == secret_id, SecretGrant.grantee == grantee.to_str())
        )

    async def rotate_value(
        self,
        session: AsyncSession,
        *,
        secret_id: uuid.UUID,
        new_plaintext: bytes,
        actor_vaults: Iterable[VaultRef],
    ) -> Secret:
        """Re-seal with a fresh DEK and re-wrap for every existing grantee; bump version."""
        secret = await self._load(session, secret_id)
        await self._dek_via(session, secret, actor_vaults)  # authorize: actor must currently hold access
        new_sealed, new_dek = seal(new_plaintext, secret_id=str(secret_id))
        secret.sealed_value = new_sealed.to_dict()
        secret.version = (secret.version or 1) + 1
        for grant in await self._grants(session, secret_id):
            grant.wrapped_dek = wrap_dek(
                new_dek, self._kek(grant.grantee), grant.grantee, secret_id=str(secret_id)
            ).to_dict()
        await session.flush()
        return secret

    async def delete(self, session: AsyncSession, *, secret_id: uuid.UUID) -> None:
        """Delete the secret; its grants cascade."""
        await session.execute(delete(Secret).where(Secret.id == secret_id))

    async def list_for_vaults(self, session: AsyncSession, *, accessible_vaults: Iterable[VaultRef]) -> list[Secret]:
        """Every envelope secret reachable by one of *accessible_vaults* (metadata; no decryption)."""
        allowed = list(_vault_strs(accessible_vaults))
        if not allowed:
            return []
        rows = await session.execute(
            select(Secret)
            .join(SecretGrant, SecretGrant.secret_id == Secret.id)
            .where(SecretGrant.grantee.in_(allowed), Secret.sealed_value.isnot(None))
            .distinct()
        )
        return list(rows.scalars())
