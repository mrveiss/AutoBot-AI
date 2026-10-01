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
- **register_dependency** / **unregister_dependency** (#10088 Task 8.2) —
  ``authorize("write", owner_vault)``: metadata about the secret, not a grant on it.

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
from services.envelope_secrets_service import (
    EnvelopeSecretsService,
    SecretAccessError,
    SecretNotFoundError,
)
from services.secret_dependency_service import SecretDependencyService
from services.secrets_access_audit import SecretAccessReport, describe_secret_access
from services.secrets_authz import PrincipalFacts, authorize
from services.secrets_principal_resolver import resolve_principal_facts

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

    @staticmethod
    def _scope_permits(secret: Secret, facts: PrincipalFacts, session_id: str | None) -> bool:
        """Whether *secret*'s own scope admits this principal (#16982).

        A vault grant and a secret's scope answer different questions, and until
        now only the first was asked: ``accessible_vaults()`` says *which vaults
        you reach*, while ``Secret.is_accessible_by`` says *whether this secret's
        scope admits you*. A SESSION-scoped secret sitting in a vault you reach
        was readable by anyone who reached the vault. The vault grant is
        necessary, not sufficient -- so both are asked now, and this is the
        second.

        **The org argument is the one decision the ruling did not settle.**
        ``PrincipalFacts.company_roles`` is a mapping, so a principal may hold
        several companies while ``is_accessible_by`` takes one. Passing the
        secret's own ``org_id`` unconditionally would be a HOLE, not a fix: the
        shared rule is ``resource.company_id == principal.company_id``
        (``autobot_shared/scoping/visibility.py:80``), so handing it the secret's
        own company makes the comparison tautological and every ORGANIZATION
        secret readable by anyone. Passing ``None`` is the opposite failure --
        every ORGANIZATION secret becomes unreadable, which looks like a
        permissions bug two frames from its cause.

        So the candidate company comes from the secret and is only supplied when
        the principal actually holds it. One value, cardinality resolved, and the
        rule still means what it says.
        """
        org_id = secret.org_id if secret.org_id and str(secret.org_id) in facts.company_roles else None
        return secret.is_accessible_by(
            uuid.UUID(facts.user_id) if isinstance(facts.user_id, str) else facts.user_id,
            session_id=session_id,
            user_org_id=org_id,
            user_team_ids=list(facts.team_ids),
        )

    @staticmethod
    def _own_user_vault(facts: PrincipalFacts) -> str:
        """The principal's OWN user vault, as stored in ``SecretGrant.grantee``."""
        return VaultRef(VaultKind.USER, str(facts.user_id)).to_str()

    async def _holds_direct_grant(self, session: AsyncSession, secret_id: uuid.UUID, facts: PrincipalFacts) -> bool:
        """Whether this secret was shared with this principal *by name* (#17822).

        **Why a scope refusal is not the last word.** #16982 closed a real hole:
        a secret sitting in a vault you reach was readable on vault
        reachability alone, so the secret's own scope is now asked too. But
        ``coordinator.share`` authorizes by issuing a ``SecretGrant`` to the
        grantee's own user vault, and that record is the system of record for
        "who may open this" -- without it there is no wrapped DEK and no
        decryption is possible. The model's ``shared_with`` list, which
        ``Secret._grant_lookup`` consults, is a second copy that this path never
        writes, so a scope check reading only that copy refuses a share the
        system actually granted. #17772 shipped with the sharing tests skipped,
        which is why it read as clean.

        **This does not reopen #16982.** The hole was *vault reachability* --
        being able to reach a vault that happens to hold the secret. This asks a
        strictly narrower question: is there a grant naming **this principal's
        own user vault**. A principal who merely reaches a shared, org or team
        vault does not match it, so the scope check still governs every case
        #16982 was about.
        """
        own = self._own_user_vault(facts)
        row = await session.execute(
            select(SecretGrant.secret_id).where(SecretGrant.secret_id == secret_id, SecretGrant.grantee == own)
        )
        return row.first() is not None

    async def _directly_granted_ids(self, session: AsyncSession, facts: PrincipalFacts) -> set[uuid.UUID]:
        """Secret ids shared with this principal by name -- one query, for ``list``."""
        rows = await session.execute(
            select(SecretGrant.secret_id).where(SecretGrant.grantee == self._own_user_vault(facts))
        )
        return set(rows.scalars())

    async def read(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        permissions: set[str],
        secret_id: uuid.UUID,
        session_id: str | None = None,
    ) -> bytes:
        """Decrypt *secret_id* for this principal, if the vault AND the scope admit them.

        ``session_id`` is threaded rather than defaulted away (owner ruling):
        ``_grant_lookup`` compares it to the secret's own for a SESSION-scoped
        secret, so omitting it makes every session-scoped secret unreadable
        through this path -- a correct-looking refusal with its cause two frames
        away. A caller that has no session context passes None deliberately and
        gets that refusal; one that has it must pass it.
        """
        facts = await self._facts(session, user_id, permissions)
        secret = await session.get(Secret, secret_id)
        # Absent, or a legacy non-envelope row: not found, not refused. Same condition the
        # service's own `_load` uses, so the pre-check speaks for the same population it
        # guards and a missing secret keeps its 404 (#17822).
        if secret is None or secret.sealed_value is None:
            raise SecretNotFoundError(f"envelope secret {secret_id} not found")
        if not self._scope_permits(secret, facts, session_id) and not await self._holds_direct_grant(
            session, secret_id, facts
        ):
            raise SecretAccessError(f"no accessible grant for secret {secret_id}")
        return await self._service.read(session, secret_id=secret_id, accessible_vaults=facts.accessible_vaults())

    async def list(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        permissions: set[str],
        session_id: str | None = None,
    ) -> list[Secret]:
        """Every secret this principal may read -- vault-reachable AND scope-admitted."""
        facts = await self._facts(session, user_id, permissions)
        reachable = await self._service.list_for_vaults(session, accessible_vaults=facts.accessible_vaults())
        granted = await self._directly_granted_ids(session, facts)
        return [s for s in reachable if self._scope_permits(s, facts, session_id) or s.id in granted]

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

    async def register_dependency(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        permissions: set[str],
        secret_id: uuid.UUID,
        dependent_kind: str,
        dependent_id: str,
        company_id: uuid.UUID | None = None,
    ) -> SecretDependency:
        """Record that *dependent_kind:dependent_id* consumes *secret_id* (#10088 Task 8.2).

        Gated the same as ``create``/``rotate``/``delete`` — ``write`` authority on the secret's
        owner vault — because this is metadata about the secret, not a grant on it: the caller
        needs no ability to *read* the value, only to manage the secret. Idempotent (delegates to
        :meth:`SecretDependencyService.register`); invalid ``dependent_kind`` raises ``ValueError``.
        """
        facts = await self._facts(session, user_id, permissions)
        owner = await self._owner_vault(session, secret_id)  # raises SecretNotFoundError when absent
        if not authorize(facts, "write", owner):
            raise SecretAccessError(f"not authorized to register dependencies for secret {secret_id}")
        dep = await SecretDependencyService().register(
            session,
            secret_id=secret_id,
            dependent_kind=dependent_kind,
            dependent_id=dependent_id,
            company_id=company_id,
            created_by=user_id,
        )
        if dep is None:  # pragma: no cover — concurrent unregister raced the read-back
            raise SecretNotFoundError(f"dependency {dependent_kind}:{dependent_id} vanished during registration")
        return dep

    async def unregister_dependency(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        permissions: set[str],
        secret_id: uuid.UUID,
        dependent_kind: str,
        dependent_id: str,
    ) -> int:
        """Drop a dependency row. Same ``write`` gate as :meth:`register_dependency`."""
        facts = await self._facts(session, user_id, permissions)
        owner = await self._owner_vault(session, secret_id)  # raises SecretNotFoundError when absent
        if not authorize(facts, "write", owner):
            raise SecretAccessError(f"not authorized to unregister dependencies for secret {secret_id}")
        return await SecretDependencyService().unregister(
            session, secret_id=secret_id, dependent_kind=dependent_kind, dependent_id=dependent_id
        )

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
