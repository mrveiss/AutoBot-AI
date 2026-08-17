# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sharing one contact across companies, and merging duplicates (#13998).

Owner decision: a contact is one row per human, shared, with visibility granted
per company through ``llc_contact_company_links``.

Three rules carry the design, and each exists to stop a specific loss:

* **A company sees only linked contacts.** Shared is not public — company A must
  not see a supplier because company B uses one. This is what keeps sharing
  compatible with #13992's "minimal necessary access".
* **Unlinking is not deleting.** Removing a contact from one company deletes
  that company's link; the PII is removed only when the last link goes. The
  alternative lets one company's tidying destroy a record another company is
  still using.
* **Merging is explicit.** Deciding two rows are the same human is a judgement.
  Doing it by matching email or name would fuse two people's PII on a guess —
  irreversible and invisible afterwards. :meth:`find_duplicate_candidates`
  therefore *suggests*; only :meth:`merge` acts, and only on ids a caller named.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.activity import ActorType
from ..models.contact import LLCContact
from ..models.contact_company_link import LLCContactCompanyLink
from .authz import require_company_admin
from .base import LLCServiceBase


class ContactSharingService(LLCServiceBase):
    """Links contacts to companies and merges duplicate contact rows."""

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
            # Never the contact's name, email or phone — a contact is entirely
            # PII, so the audit trail carries ids only.
            after=after,
        )

    async def link(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        contact_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> bool:
        """Give a company visibility of a contact. True if newly linked."""
        await require_company_admin(session, company_id, actor_user_id)

        exists = await session.execute(select(LLCContact.id).where(LLCContact.id == contact_id))
        if exists.scalar_one_or_none() is None:
            raise ValueError(f"contact {contact_id} does not exist")

        if await self._link_row(session, company_id, contact_id) is not None:
            return False

        session.add(LLCContactCompanyLink(contact_id=contact_id, company_id=company_id))
        await session.flush()
        await self._record(session, company_id, contact_id, "contact.linked", actor_user_id, None)
        return True

    async def _link_row(
        self, session: AsyncSession, company_id: uuid.UUID, contact_id: uuid.UUID
    ) -> Optional[LLCContactCompanyLink]:
        result = await session.execute(
            select(LLCContactCompanyLink).where(
                LLCContactCompanyLink.company_id == company_id,
                LLCContactCompanyLink.contact_id == contact_id,
            )
        )
        return result.scalar_one_or_none()

    async def unlink(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        contact_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> bool:
        """Remove one company's visibility. Deletes the PII only if it was the last.

        Returns True when a link was removed. The contact row survives while any
        other company still links to it — deleting it there would destroy
        another company's data because of an unrelated company's tidying.
        """
        await require_company_admin(session, company_id, actor_user_id)

        result = await session.execute(
            sa_delete(LLCContactCompanyLink).where(
                LLCContactCompanyLink.company_id == company_id,
                LLCContactCompanyLink.contact_id == contact_id,
            )
        )
        if not result.rowcount:
            return False

        remaining = await session.execute(
            select(func.count())
            .select_from(LLCContactCompanyLink)
            .where(LLCContactCompanyLink.contact_id == contact_id)
        )
        orphaned = (remaining.scalar_one() or 0) == 0
        if orphaned:
            # Last company let go of it: now the PII goes, satisfying #13969's
            # "deletion removes PII" without ever destroying shared data early.
            await session.execute(sa_delete(LLCContact).where(LLCContact.id == contact_id))

        await session.flush()
        await self._record(
            session,
            company_id,
            contact_id,
            "contact.unlinked",
            actor_user_id,
            {"deleted_orphan": orphaned},
        )
        return True

    async def list_for_company(self, session: AsyncSession, company_id: uuid.UUID) -> List[LLCContact]:
        """Contacts this company can see — linked ones only."""
        result = await session.execute(
            select(LLCContact)
            .join(LLCContactCompanyLink, LLCContactCompanyLink.contact_id == LLCContact.id)
            .where(LLCContactCompanyLink.company_id == company_id)
            .order_by(LLCContact.full_name)
        )
        return list(result.scalars().all())

    async def companies_for_contact(self, session: AsyncSession, contact_id: uuid.UUID) -> List[uuid.UUID]:
        """Every company linked to a contact — what a merge or unlink affects."""
        result = await session.execute(
            select(LLCContactCompanyLink.company_id)
            .where(LLCContactCompanyLink.contact_id == contact_id)
            .order_by(LLCContactCompanyLink.company_id)
        )
        return list(result.scalars().all())

    async def merge(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        keep_id: uuid.UUID,
        merge_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> LLCContact:
        """Fold ``merge_id`` into ``keep_id``: move its links, then delete it.

        Both contacts must be visible to the calling company. Without that a
        caller could merge two records they cannot see, using this as a way to
        learn that an unrelated company's contact exists — and to destroy it.
        """
        await require_company_admin(session, company_id, actor_user_id)
        if keep_id == merge_id:
            raise ValueError("cannot merge a contact into itself")

        for contact_id in (keep_id, merge_id):
            if await self._link_row(session, company_id, contact_id) is None:
                raise ValueError(f"contact {contact_id} is not linked to company {company_id}")

        # Move every link the merged contact had, skipping companies that
        # already see the survivor — otherwise the unique constraint would fire
        # on exactly the companies that see both, which is the common case.
        keep_companies = set(await self.companies_for_contact(session, keep_id))
        for company in await self.companies_for_contact(session, merge_id):
            if company in keep_companies:
                continue
            session.add(LLCContactCompanyLink(contact_id=keep_id, company_id=company))

        await session.execute(sa_delete(LLCContactCompanyLink).where(LLCContactCompanyLink.contact_id == merge_id))
        await session.execute(sa_delete(LLCContact).where(LLCContact.id == merge_id))
        await session.flush()

        survivor = await session.execute(select(LLCContact).where(LLCContact.id == keep_id))
        await self._record(
            session,
            company_id,
            keep_id,
            "contact.merged",
            actor_user_id,
            {"merged_id": str(merge_id)},
        )
        return survivor.scalar_one()

    async def find_duplicate_candidates(self, session: AsyncSession, company_id: uuid.UUID) -> List[List[uuid.UUID]]:
        """Groups of this company's contacts that share an email, for review.

        Suggests only. Two people can share a mailbox (``info@supplier``), so a
        migration that merged on this would fuse them silently — which is why
        this returns candidates and :meth:`merge` takes explicit ids.

        Deliberately plain SQL rather than ``array_agg``: that is Postgres-only,
        and a helper that cannot run on the SQLite test harness is a helper
        whose behaviour is never verified.
        """
        rows = await session.execute(
            select(LLCContact.id, LLCContact.email)
            .join(LLCContactCompanyLink, LLCContactCompanyLink.contact_id == LLCContact.id)
            .where(
                LLCContactCompanyLink.company_id == company_id,
                LLCContact.email.isnot(None),
                LLCContact.email != "",
            )
            .order_by(LLCContact.email, LLCContact.id)
        )
        by_email: Dict[str, List[uuid.UUID]] = {}
        for contact_id, email in rows.all():
            # Case-insensitive: "Ada@x" and "ada@x" are one mailbox, and leaving
            # them in separate groups would hide the duplicate this looks for.
            by_email.setdefault(email.strip().lower(), []).append(contact_id)
        return [ids for ids in by_email.values() if len(ids) > 1]
