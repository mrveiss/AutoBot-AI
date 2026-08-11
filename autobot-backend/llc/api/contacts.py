# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company-scoped contact API routes (#13969).

Route group: /llc/contacts/{company_id}
  GET    /                  — list a company's contacts
  POST   /                  — create a contact
  GET    /{contact_id}      — get one contact
  PATCH  /{contact_id}      — update contact fields
  DELETE /{contact_id}      — permanently delete a contact and its PII

A contact is a human in a process (supplier, customer) with no account and
no login path — see ``llc/models/contact.py`` module docstring. These routes
never touch ``users``, sessions, or auth.

Scoping: the {company_id} path parameter is checked against the caller's
``TenantContext.org_id`` via ``assert_company_access`` (#12238), the same
shared guard every other LLC router uses (companies.py, goals.py,
backlog.py, ...). This scopes the *view* to the requesting company — it is
not a security/tenant-isolation boundary between customers, since companies
inside one AutoBot installation are organisational units, not separate
tenants (umbrella #13935 owner correction).
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.singleton_factory import lazy_singleton
from llc.deps import assert_company_access
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..services.contact import ContactService

router = APIRouter(prefix="/contacts", tags=["llc-contacts"])

_get_svc = lazy_singleton(ContactService)


def _svc() -> ContactService:
    return _get_svc()


# ------------------------------------------------------------------ Schemas


class ContactCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=320)
    phone: Optional[str] = Field(None, max_length=64)
    role_title: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None
    actor: Optional[str] = Field(None, description="User ID performing the operation")


class ContactUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=320)
    phone: Optional[str] = Field(None, max_length=64)
    role_title: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class ContactResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    role_title: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ Routes


@router.get("/{company_id}", response_model=List[ContactResponse])
async def list_contacts(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[ContactResponse]:
    assert_company_access(ctx, company_id)
    contacts = await _svc().list_by_company(session, company_id)
    return [ContactResponse.model_validate(c) for c in contacts]


@router.post("/{company_id}", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    company_id: uuid.UUID,
    body: ContactCreate,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ContactResponse:
    assert_company_access(ctx, company_id)
    contact = await _svc().create(
        session,
        company_id,
        body.full_name,
        email=body.email,
        phone=body.phone,
        role_title=body.role_title,
        notes=body.notes,
        actor=body.actor,
    )
    await session.commit()
    return ContactResponse.model_validate(contact)


@router.get("/{company_id}/{contact_id}", response_model=ContactResponse)
async def get_contact(
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ContactResponse:
    assert_company_access(ctx, company_id)
    contact = await _svc().get(session, company_id, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return ContactResponse.model_validate(contact)


@router.patch("/{company_id}/{contact_id}", response_model=ContactResponse)
async def update_contact(
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: ContactUpdate,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ContactResponse:
    assert_company_access(ctx, company_id)
    updates = body.model_dump(exclude_unset=True)
    contact = await _svc().update(session, company_id, contact_id, **updates)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    await session.commit()
    return ContactResponse.model_validate(contact)


@router.delete("/{company_id}/{contact_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_contact(
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    actor: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    """Permanently delete the contact — its PII no longer exists at rest afterward."""
    assert_company_access(ctx, company_id)
    deleted = await _svc().delete(session, company_id, contact_id, actor=actor)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    await session.commit()
