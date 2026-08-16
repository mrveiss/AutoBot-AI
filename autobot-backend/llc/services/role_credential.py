# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attach and resolve credential references on a role (#14221 step 4).

Stores ``secret_id`` only — never a value. Plaintext stays behind
``SecretService``, which owns decryption, revocation and the audit trail.

Two properties carry the design:

* **Revocation is honoured at read time.** ``list_active_for_role`` joins
  ``llc_secrets`` and excludes ``revoked_at IS NOT NULL``. Filtering only when
  attaching would leave a revoked credential reachable through the role for as
  long as the attachment row survived, which is exactly what revocation exists
  to prevent.
* **The company boundary is crossed in one place, explicitly.**
  ``llc_roles``/``organizations`` key companies as ``UUID``; ``llc_secrets``
  keys them as ``String(255)`` (#14312). Rather than scatter coercions, this
  module converts once in :func:`_secret_company_key` and says why.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from user_management.models.role import Role

from ..models.activity import ActorType
from ..models.role_credential import LLCRoleCredential
from ..models.secret import LLCSecret
from .authz import require_company_admin
from .base import LLCServiceBase


def _secret_company_key(company_id: uuid.UUID) -> str:
    """Render a company id the way ``llc_secrets`` stores it.

    ``LLCSecret.company_id`` is ``String(255)`` while every table in this step
    uses ``UUID`` — the split tracked in #14312. Comparing a ``uuid.UUID``
    against the string column would not match, and a scoping predicate that
    matches nothing is indistinguishable from one that works. The conversion is
    therefore explicit, named, and confined to this one function so the
    eventual type migration has a single site to delete.
    """
    return str(company_id)


class RoleCredentialService(LLCServiceBase):
    """Company-scoped attachment of secret references to roles."""

    async def _record(
        self,
        session: AsyncSession,
        attachment: LLCRoleCredential,
        event_type: str,
        actor: Optional[uuid.UUID],
        after: Optional[Dict[str, Any]],
    ) -> None:
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(attachment.company_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=str(actor) if actor else None,
            event_type=event_type,
            entity_type="llc_role_credential",
            entity_id=str(attachment.id),
            # Never the secret's value or name — the id is the reference.
            after=after,
        )

    async def _require_role(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> None:
        result = await session.execute(select(Role.id).where(Role.id == role_id, Role.org_id == company_id))
        if result.scalar_one_or_none() is None:
            raise ValueError(f"role {role_id} does not exist in company {company_id}")

    async def _require_secret(self, session: AsyncSession, company_id: uuid.UUID, secret_id: uuid.UUID) -> None:
        """The secret must exist in this company and not be revoked.

        A revoked secret is refused with its own message rather than folded into
        "not found": the caller needs to distinguish "no such credential" from
        "that credential was withdrawn", because only the second is a signal
        that something upstream changed.
        """
        result = await session.execute(
            select(LLCSecret.revoked_at).where(
                LLCSecret.id == secret_id,
                LLCSecret.company_id == _secret_company_key(company_id),
            )
        )
        row = result.first()
        if row is None:
            raise ValueError(f"secret {secret_id} does not exist in company {company_id}")
        if row[0] is not None:
            raise ValueError(f"secret {secret_id} is revoked and cannot be attached to a role")

    async def attach(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        secret_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> LLCRoleCredential:
        if company_id is None or role_id is None or secret_id is None:
            raise ValueError("company_id, role_id and secret_id are all required")

        await require_company_admin(session, company_id, actor_user_id)
        await self._require_role(session, company_id, role_id)
        await self._require_secret(session, company_id, secret_id)

        if await self.get(session, company_id, role_id, secret_id) is not None:
            raise ValueError(f"secret {secret_id} is already attached to role {role_id}")

        attachment = LLCRoleCredential(company_id=company_id, role_id=role_id, secret_id=secret_id)
        session.add(attachment)
        await session.flush()
        await self._record(
            session,
            attachment,
            "role_credential.attached",
            actor_user_id,
            {"role_id": str(role_id), "secret_id": str(secret_id)},
        )
        return attachment

    async def get(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        secret_id: uuid.UUID,
    ) -> Optional[LLCRoleCredential]:
        result = await session.execute(
            select(LLCRoleCredential).where(
                LLCRoleCredential.company_id == company_id,
                LLCRoleCredential.role_id == role_id,
                LLCRoleCredential.secret_id == secret_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_role(
        self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID
    ) -> List[LLCRoleCredential]:
        """Every attachment, including ones whose secret was later revoked.

        The administrative view — use :meth:`list_active_for_role` to decide
        what a holder may actually reach.
        """
        result = await session.execute(
            select(LLCRoleCredential)
            .where(
                LLCRoleCredential.company_id == company_id,
                LLCRoleCredential.role_id == role_id,
            )
            .order_by(LLCRoleCredential.created_at)
        )
        return list(result.scalars().all())

    async def list_active_for_role(
        self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID
    ) -> List[uuid.UUID]:
        """Secret ids a holder of this role may actually reach, right now.

        Revocation is applied here rather than at attach time, so revoking a
        secret withdraws it from every role immediately with no sweep.
        """
        result = await session.execute(
            select(LLCRoleCredential.secret_id)
            .join(LLCSecret, LLCSecret.id == LLCRoleCredential.secret_id)
            .where(
                LLCRoleCredential.company_id == company_id,
                LLCRoleCredential.role_id == role_id,
                LLCSecret.company_id == _secret_company_key(company_id),
                LLCSecret.revoked_at.is_(None),
            )
            .order_by(LLCRoleCredential.secret_id)
        )
        return list(result.scalars().all())

    async def detach(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        secret_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
    ) -> bool:
        """Remove a reference. Returns True when a row was actually removed."""
        await require_company_admin(session, company_id, actor_user_id)
        attachment = await self.get(session, company_id, role_id, secret_id)
        result = await session.execute(
            sa_delete(LLCRoleCredential).where(
                LLCRoleCredential.company_id == company_id,
                LLCRoleCredential.role_id == role_id,
                LLCRoleCredential.secret_id == secret_id,
            )
        )
        detached = bool(result.rowcount)
        if detached and attachment is not None:
            await self._record(
                session,
                attachment,
                "role_credential.detached",
                actor_user_id,
                {"role_id": str(role_id), "secret_id": str(secret_id)},
            )
        return detached
