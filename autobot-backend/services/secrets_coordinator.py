# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Authorization + envelope orchestration for the secrets API (#10088 / Task 2.4).

The seam between HTTP and the store: each operation resolves the caller's
:class:`PrincipalFacts` (Task 2.3 part 2), applies the RBAC policy
(``secrets_authz``, Task 2.3 part 1), then calls the envelope
``EnvelopeSecretsService`` (Task 2.2). Kept free of FastAPI so it is testable
against Postgres without loading the whole app (the only Postgres CI job runs a
minimal dep set); the ``/api/v2/secrets`` router is a thin shell over this.

Authorization model
-------------------
- **create** — ``authorize("write", owner_vault)``: you may create a secret in a
  vault you can write to.
- **read** / **list** — gated by ``accessible_vaults``: the service only opens a
  secret you hold a grant for, in a vault you can reach. No accessible grant ⇒
  :class:`SecretAccessError`.
- **share** — ``authorize("share", owner_vault)`` (manage grants on the owning
  vault) *and* you must already be able to open the secret (the service unwraps
  the DEK via your ``actor_vaults``).
- **revoke** — ``authorize("revoke", owner_vault)``.
- **rotate** / **delete** — ``authorize("write", owner_vault)``.

Every mutation authorizes against the secret's **owner vault** (the authority
that owns it), not the grantee — sharing with company B is gated by your rights
in the owning vault, never by B's.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.secrets_vault import VaultKind, VaultRef
from models.secret import Secret
from models.secret_dependency import SecretDependency
from models.secret_grant import SecretGrant
from services.secret_dependency_service import SecretDependencyService
from services.secrets_access_audit import SecretAccessReport, describe_secret_access
from services.secrets_authz import PrincipalFacts, authorize
from services.secrets_principal_resolver import resolve_principal_facts
from services.envelope_secrets_service import (
    EnvelopeSecretsService,
    SecretAccessError,
    SecretNotFoundError,
)

logger = logging.getLogger(__name__)

#: Sentinel UUID used as ``created_by`` for service-principal operations (no real user).
_SERVICE_OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


class SecretsCoordinator:
    """Resolve facts → authorize → call the envelope service."""

    def __init__(self, service: EnvelopeSecretsService | None = None) -> None:
        self._service = service if service is not None else EnvelopeSecretsService()

    async def _facts(self, session: AsyncSession, user_id: uuid.UUID, permissions: set[str]) -> PrincipalFacts:
        return await resolve_principal_facts(session, user_id, permissions)

    async def _owner_vault(self, session: AsyncSession, secret_id: uuid.UUID) -> VaultRef:
        row = await session.execute(
            select(Secret.owner_vault).where(Secret.id == secret_id, Secret.sealed_value.isnot(None))
        )
        owner = row.scalar_one_or_none()
        if owner is None:
            raise SecretNotFoundError(f"envelope secret {secret_id} not found")
        return VaultRef.parse(owner)

    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        permissions: set[str],
        owner_vault: VaultRef,
        name: str,
        secret_type: str,
        plaintext: bytes,
    ) -> Secret:
        facts = await self._facts(session, user_id, permissions)
        if not authorize(facts, "write", owner_vault):
            raise SecretAccessError(f"not authorized to write to {owner_vault.to_str()}")
        return await self._service.create(
            session,
            owner_vault=owner_vault,
            name=name,
            secret_type=secret_type,
            plaintext=plaintext,
            created_by=user_id,
        )

    async def read(
        self, session: AsyncSession, *, user_id: uuid.UUID, permissions: set[str], secret_id: uuid.UUID
    ) -> bytes:
        facts = await self._facts(session, user_id, permissions)
        return await self._service.read(session, secret_id=secret_id, accessible_vaults=facts.accessible_vaults())

    async def list(self, session: AsyncSession, *, user_id: uuid.UUID, permissions: set[str]) -> list[Secret]:
        facts = await self._facts(session, user_id, permissions)
        return await self._service.list_for_vaults(session, accessible_vaults=facts.accessible_vaults())

    async def describe_access(
        self, session: AsyncSession, *, user_id: uuid.UUID, permissions: set[str], secret_id: uuid.UUID
    ) -> SecretAccessReport:
        """Who can access *secret_id*. Gated on **manage** authority (``share``): you may audit who
        has access only if you may change who has access — i.e. the owner, an admin, or a company
        OWNER/ADMIN/LEAD — so a mere reader (company guest/member, plain grantee) cannot enumerate
        the cross-vault roster."""
        facts = await self._facts(session, user_id, permissions)
        owner = await self._owner_vault(session, secret_id)  # raises SecretNotFoundError when absent
        if not authorize(facts, "share", owner):
            raise SecretAccessError(f"not authorized to view access for secret {secret_id}")
        return await describe_secret_access(session, secret_id)

    async def describe_dependencies(
        self, session: AsyncSession, *, user_id: uuid.UUID, permissions: set[str], secret_id: uuid.UUID
    ) -> list[SecretDependency]:
        """What depends on *secret_id* — the rotation/revocation impact list. Same manage-authority
        gate as :meth:`describe_access` (owner / admin / company OWNER-ADMIN-LEAD)."""
        facts = await self._facts(session, user_id, permissions)
        owner = await self._owner_vault(session, secret_id)  # raises SecretNotFoundError when absent
        if not authorize(facts, "share", owner):
            raise SecretAccessError(f"not authorized to view dependencies for secret {secret_id}")
        return await SecretDependencyService().what_depends_on(session, secret_id=secret_id)

    async def share(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        permissions: set[str],
        secret_id: uuid.UUID,
        grantee: VaultRef,
    ) -> SecretGrant:
        facts = await self._facts(session, user_id, permissions)
        owner_vault = await self._owner_vault(session, secret_id)
        if not authorize(facts, "share", owner_vault):
            raise SecretAccessError(f"not authorized to share secrets in {owner_vault.to_str()}")
        return await self._service.share(
            session,
            secret_id=secret_id,
            actor_vaults=facts.accessible_vaults(),
            grantee=grantee,
            created_by=user_id,
        )

    async def revoke(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        permissions: set[str],
        secret_id: uuid.UUID,
        grantee: VaultRef,
    ) -> None:
        facts = await self._facts(session, user_id, permissions)
        owner_vault = await self._owner_vault(session, secret_id)
        if not authorize(facts, "revoke", owner_vault):
            raise SecretAccessError(f"not authorized to revoke grants in {owner_vault.to_str()}")
        await self._service.revoke(session, secret_id=secret_id, grantee=grantee)

    async def rotate(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        permissions: set[str],
        secret_id: uuid.UUID,
        new_plaintext: bytes,
    ) -> Secret:
        facts = await self._facts(session, user_id, permissions)
        owner_vault = await self._owner_vault(session, secret_id)
        if not authorize(facts, "write", owner_vault):
            raise SecretAccessError(f"not authorized to rotate secrets in {owner_vault.to_str()}")
        return await self._service.rotate_value(
            session, secret_id=secret_id, new_plaintext=new_plaintext, actor_vaults=facts.accessible_vaults()
        )

    async def rotate_kek(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        permissions: set[str],
        secret_id: uuid.UUID,
        new_root_key: bytes,
    ) -> Secret:
        facts = await self._facts(session, user_id, permissions)
        owner_vault = await self._owner_vault(session, secret_id)
        if not authorize(facts, "write", owner_vault):
            raise SecretAccessError(f"not authorized to rotate KEK for secrets in {owner_vault.to_str()}")
        return await self._service.rotate_kek(
            session,
            secret_id=secret_id,
            new_root_key=new_root_key,
            actor_vaults=facts.accessible_vaults(),
        )

    async def delete(
        self, session: AsyncSession, *, user_id: uuid.UUID, permissions: set[str], secret_id: uuid.UUID
    ) -> None:
        facts = await self._facts(session, user_id, permissions)
        owner_vault = await self._owner_vault(session, secret_id)
        if not authorize(facts, "write", owner_vault):
            raise SecretAccessError(f"not authorized to delete secrets in {owner_vault.to_str()}")
        await self._service.delete(session, secret_id=secret_id)

    # ------------------------------------------------------------------
    # Service-principal operations (#10436): bypass user RBAC; scope is
    # STRICTLY the system vault — callers must already have enforced this
    # (see _require_system_vault in the API layer).  These methods exist
    # so the coordinator boundary is still the single enforcement point
    # for crypto orchestration, while the API layer handles auth.
    # ------------------------------------------------------------------

    def _assert_system_vault(self, vault: VaultRef) -> None:
        """Double-check that only the system vault is used; raises SecretAccessError otherwise."""
        if vault.kind is not VaultKind.SYSTEM:
            raise SecretAccessError(f"service operations are restricted to the system vault; got {vault.to_str()!r}")

    async def service_create(
        self,
        session: AsyncSession,
        *,
        owner_vault: VaultRef,
        name: str,
        secret_type: str,
        plaintext: bytes,
        service_id: str,
    ) -> Secret:
        """Create a system-vault secret on behalf of a service identity."""
        self._assert_system_vault(owner_vault)
        logger.info("service_create system secret", extra={"service_id": service_id, "name": name})
        return await self._service.create(
            session,
            owner_vault=owner_vault,
            name=name,
            secret_type=secret_type,
            plaintext=plaintext,
            created_by=_SERVICE_OWNER_ID,
        )

    async def service_read(self, session: AsyncSession, *, secret_id: uuid.UUID, vault: VaultRef) -> bytes:
        """Read a system-vault secret value on behalf of a service identity."""
        self._assert_system_vault(vault)
        return await self._service.read(session, secret_id=secret_id, accessible_vaults={vault})

    async def service_list(self, session: AsyncSession, *, vault: VaultRef) -> list[Secret]:
        """List system-vault secrets accessible to a service identity."""
        self._assert_system_vault(vault)
        return await self._service.list_for_vaults(session, accessible_vaults={vault})

    async def service_rotate(
        self, session: AsyncSession, *, secret_id: uuid.UUID, new_plaintext: bytes, vault: VaultRef
    ) -> Secret:
        """Rotate (re-seal) a system-vault secret value on behalf of a service identity."""
        self._assert_system_vault(vault)
        return await self._service.rotate_value(
            session, secret_id=secret_id, new_plaintext=new_plaintext, actor_vaults={vault}
        )

    async def service_rotate_kek(
        self, session: AsyncSession, *, secret_id: uuid.UUID, new_root_key: bytes, vault: VaultRef
    ) -> Secret:
        """Rewrap a system-vault secret's DEKs under a new root key on behalf of a service identity.

        The sealed plaintext is unchanged (KEK-only rotation). Scope is strictly
        the system vault — the service-auth API layer already enforced this.
        """
        self._assert_system_vault(vault)
        return await self._service.rotate_kek(
            session, secret_id=secret_id, new_root_key=new_root_key, actor_vaults={vault}
        )

    async def service_delete(self, session: AsyncSession, *, secret_id: uuid.UUID, vault: VaultRef) -> None:
        """Delete a system-vault secret on behalf of a service identity."""
        self._assert_system_vault(vault)
        owner_vault = await self._owner_vault(session, secret_id)
        if owner_vault.kind is not VaultKind.SYSTEM:
            raise SecretAccessError(
                f"service may only delete system-vault secrets; found owner {owner_vault.to_str()!r}"
            )
        await self._service.delete(session, secret_id=secret_id)
