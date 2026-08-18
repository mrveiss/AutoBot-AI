# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared people directory, and merging duplicates (#13998).

Owner decision:

    real employees and contacts are shared across the Company OS — that means
    shared

So there is **one installation-wide directory of humans**. A company never
re-creates a person it already has; it draws from the same pool. What is
company-scoped is the **role** a person holds and the work that role touches —
not whether they appear in the directory at all.

That is why this module carries no visibility table. An earlier draft gated the
directory per company with `llc_contact_company_links`; the owner's correction
removed the need for it, and the involvement it modelled is already expressed by
``llc_role_assignments`` with ``holder_type = contact`` (#14221 step 2). Two
ways to say "this person is involved with this company" would eventually
disagree, and the derived one cannot go stale.

Consistency with #13992 ("access is need-to-know… only when a specific role is
required"): a shared *directory* is not shared *access*. Knowing a supplier
exists is not permission to see the work they do — that still requires a role in
the company, and role permissions still gate what a holder may do.

Deletion is the sharp edge of a shared directory: removing a person removes them
for everyone. So :meth:`delete` refuses while the contact still holds a role
anywhere, rather than silently emptying another company's org chart.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.activity import ActorType
from ..models.contact import LLCContact
from ..models.enums import RoleHolderType
from ..models.role_assignment import LLCRoleAssignment
from .authz import require_company_admin
from .base import LLCServiceBase


class ContactInUseError(Exception):
    """The contact still holds a role, so deleting them would break a company.

    Distinct from a plain ``ValueError``: the request is well formed and the
    caller is authorised — the refusal is about consequences elsewhere, and the
    caller needs to know *which* companies to look at rather than being told
    they asked for something nonsensical.
    """

    def __init__(self, contact_id: uuid.UUID, company_ids: List[uuid.UUID]) -> None:
        super().__init__(
            f"contact {contact_id} still holds a role in {len(company_ids)} company/companies; "
            "end those tenures before removing them from the shared directory"
        )
        self.contact_id = contact_id
        self.company_ids = company_ids


class ContactDirectoryService(LLCServiceBase):
    """Reads the shared people directory and merges duplicate records."""

    async def _record(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        contact_id: uuid.UUID,
        event_type: str,
        actor: Optional[uuid.UUID],
        after: Optional[Dict[str, Any]],
    ) -> None:
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(company_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=str(actor) if actor else None,
            event_type=event_type,
            entity_type="llc_contact",
            entity_id=str(contact_id),
            # Ids only — a contact is entirely PII, so no name, email or phone
            # reaches the audit trail.
            after=after,
        )

    async def list_directory(self, session: AsyncSession) -> List[LLCContact]:
        """Every contact in the installation, ordered by name.

        Deliberately takes no ``company_id``. The directory is shared, and a
        per-company signature would invite a filter to creep back in — quietly
        re-introducing the duplication this decision exists to remove, as
        companies fail to find people the installation already has.
        """
        result = await session.execute(select(LLCContact).order_by(LLCContact.full_name))
        return list(result.scalars().all())

    async def companies_for_contact(self, session: AsyncSession, contact_id: uuid.UUID) -> List[uuid.UUID]:
        """Companies where this contact currently holds a role.

        Derived from open tenures rather than stored: involvement *is* holding a
        role, so recording it separately would create a second answer that can
        disagree with the first.
        """
        result = await session.execute(
            select(LLCRoleAssignment.company_id)
            .where(
                LLCRoleAssignment.holder_type == RoleHolderType.CONTACT.value,
                LLCRoleAssignment.holder_contact_id == contact_id,
                LLCRoleAssignment.ended_at.is_(None),
            )
            .distinct()
        )
        return list(result.scalars().all())

    async def delete(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        contact_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> bool:
        """Remove a person from the shared directory.

        Refuses while they hold a role anywhere. In a shared directory a delete
        is global, so an admin of one company could otherwise empty another
        company's org chart without ever seeing it happen.
        """
        await require_company_admin(session, company_id, actor_user_id)

        held = await self.companies_for_contact(session, contact_id)
        if held:
            raise ContactInUseError(contact_id, held)

        result = await session.execute(sa_delete(LLCContact).where(LLCContact.id == contact_id))
        deleted = bool(result.rowcount)
        if deleted:
            await self._record(session, company_id, contact_id, "contact.deleted", actor_user_id, None)
        return deleted

    async def merge(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        keep_id: uuid.UUID,
        merge_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> LLCContact:
        """Fold ``merge_id`` into ``keep_id``: move its role tenures, then delete it.

        Moving the tenures is what makes this a merge rather than a delete.
        Dropping them would silently vacate every role the duplicate held, so
        the person would disappear from org charts in companies the merging
        admin never looked at.
        """
        await require_company_admin(session, company_id, actor_user_id)
        if keep_id == merge_id:
            raise ValueError("cannot merge a contact into itself")

        for contact_id in (keep_id, merge_id):
            found = await session.execute(select(LLCContact.id).where(LLCContact.id == contact_id))
            if found.scalar_one_or_none() is None:
                raise ValueError(f"contact {contact_id} does not exist")

        moved = await session.execute(
            select(LLCRoleAssignment).where(
                LLCRoleAssignment.holder_type == RoleHolderType.CONTACT.value,
                LLCRoleAssignment.holder_contact_id == merge_id,
            )
        )
        tenures = list(moved.scalars().all())
        for tenure in tenures:
            tenure.holder_contact_id = keep_id

        await session.execute(sa_delete(LLCContact).where(LLCContact.id == merge_id))
        await session.flush()

        survivor = await session.execute(select(LLCContact).where(LLCContact.id == keep_id))
        await self._record(
            session,
            company_id,
            keep_id,
            "contact.merged",
            actor_user_id,
            {"merged_id": str(merge_id), "tenures_moved": len(tenures)},
        )
        return survivor.scalar_one()

    async def find_duplicate_candidates(self, session: AsyncSession) -> List[List[uuid.UUID]]:
        """Directory-wide groups of contacts sharing an email, for review.

        Suggests only. Two people can share a mailbox (``info@supplier``), so
        merging on this automatically would fuse them silently — which is why
        this returns candidates and :meth:`merge` takes explicit ids.

        Plain SQL rather than ``array_agg``: that is Postgres-only, and a helper
        that cannot run on the SQLite harness is one whose behaviour is never
        verified.
        """
        rows = await session.execute(
            select(LLCContact.id, LLCContact.email)
            .where(LLCContact.email.isnot(None), LLCContact.email != "")
            .order_by(LLCContact.email, LLCContact.id)
        )
        by_email: Dict[str, List[uuid.UUID]] = {}
        for contact_id, email in rows.all():
            # Case-insensitive: "Ada@x" and "ada@x" are one mailbox, and leaving
            # them in separate groups would hide the duplicate this looks for.
            by_email.setdefault(email.strip().lower(), []).append(contact_id)
        return [ids for ids in by_email.values() if len(ids) > 1]
