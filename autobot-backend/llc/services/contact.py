# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company-scoped contact service (#13969).

CRUD for ``LLCContact`` — humans in a process (suppliers, customers) who have
no account and must never be able to log in. Deliberately does NOT import
``knowledge``, ``llc.kb``, or ``utils.async_chromadb_client`` anywhere in this
module: a contact's PII must never reach the vector store, because an
embedding cannot be revoked and that would create a deletion request this
service could not honour (#13935). See
``llc/tests/test_contacts_no_embedding.py`` for the guard that proves it.

``delete()`` performs a hard DELETE, not the soft ``revoked_at`` pattern
``SecretService`` uses — the acceptance criterion is that deleting a contact
"removes its PII", and a soft-revoked row would still hold the plaintext
name/email/phone/notes at rest.
"""

import uuid
from typing import List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.activity import ActorType
from ..models.contact import LLCContact
from .base import LLCServiceBase


class ContactService(LLCServiceBase):
    """Company-scoped CRUD for contacts. Every method takes company_id explicitly
    and filters on it — callers (API routes) are responsible for verifying the
    caller may act for that company before invoking these methods."""

    async def create(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        full_name: str,
        *,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        role_title: Optional[str] = None,
        notes: Optional[str] = None,
        actor: Optional[uuid.UUID] = None,
    ) -> LLCContact:
        contact = LLCContact(
            id=uuid.uuid4(),
            company_id=company_id,
            full_name=full_name,
            email=email,
            phone=phone,
            role_title=role_title,
            notes=notes,
        )
        session.add(contact)
        await session.flush()
        await session.refresh(contact)

        if self.activity_log:
            await self.activity_log.record(
                session=session,
                company_id=str(company_id),
                actor_type=ActorType.USER if actor else ActorType.SYSTEM,
                actor_id=actor,
                event_type="contact.created",
                entity_type="llc_contact",
                entity_id=str(contact.id),
                # Never log PII (name/email/phone/notes) — id only.
                after={"id": str(contact.id)},
            )
        return contact

    async def get(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        contact_id: uuid.UUID,
    ) -> Optional[LLCContact]:
        result = await session.execute(
            select(LLCContact).where(
                LLCContact.id == contact_id,
                LLCContact.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_company(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[LLCContact]:
        result = await session.execute(
            select(LLCContact).where(LLCContact.company_id == company_id).order_by(LLCContact.full_name)
        )
        return list(result.scalars().all())

    async def update(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        contact_id: uuid.UUID,
        *,
        actor: Optional[uuid.UUID] = None,
        **fields,
    ) -> Optional[LLCContact]:
        contact = await self.get(session, company_id, contact_id)
        if contact is None:
            return None
        allowed = {"full_name", "email", "phone", "role_title", "notes"}
        changed_fields = sorted(key for key in fields if key in allowed)
        for key, value in fields.items():
            if key in allowed:
                setattr(contact, key, value)
        await session.flush()

        if self.activity_log and changed_fields:
            await self.activity_log.record(
                session=session,
                company_id=str(company_id),
                actor_type=ActorType.USER if actor else ActorType.SYSTEM,
                actor_id=actor,
                event_type="contact.updated",
                entity_type="llc_contact",
                entity_id=str(contact.id),
                # Field names only — never the new PII values themselves.
                after={"fields_changed": changed_fields},
            )
        return contact

    async def delete(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        contact_id: uuid.UUID,
        *,
        actor: Optional[uuid.UUID] = None,
    ) -> bool:
        """Hard-delete a contact so its PII no longer exists at rest.

        Returns True if a row was deleted, False if no matching contact
        existed for this company (mirrors ``GoalService.delete``'s bool
        return so the route can 404 without a second lookup). The audit
        record is written only after ``rowcount`` confirms a row actually
        matched — a 404 (no matching row) must never emit a
        ``contact.deleted`` event.
        """
        result = await session.execute(
            sa_delete(LLCContact).where(
                LLCContact.id == contact_id,
                LLCContact.company_id == company_id,
            )
        )
        deleted = result.rowcount > 0

        if deleted and self.activity_log:
            await self.activity_log.record(
                session=session,
                company_id=str(company_id),
                actor_type=ActorType.USER if actor else ActorType.SYSTEM,
                actor_id=actor,
                event_type="contact.deleted",
                entity_type="llc_contact",
                entity_id=str(contact_id),
                after=None,
            )
        return deleted


__all__ = ["ContactService"]
