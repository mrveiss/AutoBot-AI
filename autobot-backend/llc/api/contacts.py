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

DELETE /{contact_id} delegates to ``ContactDirectoryService.delete`` (#14464
review), the same guard the shared-directory route ``/{company_id}/directory/
{contact_id}`` uses. The directory is installation-wide, so a delete here is
global — it must refuse while the contact still holds a role in *any*
company, not only this one, or a plain member of this company could
hard-delete someone another company still depends on.

Scoping: the {company_id} path parameter is checked against the caller's
``TenantContext.org_id`` via ``assert_company_access`` (#12238), the same
shared guard every other LLC router uses (companies.py, goals.py,
backlog.py, ...). This scopes the *view* to the requesting company — it is
not a security/tenant-isolation boundary between customers, since companies
inside one AutoBot installation are organisational units, not separate
tenants (umbrella #13935 owner correction).
"""

import re
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.singleton_factory import lazy_singleton
from llc.deps import assert_company_access
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..services.authz import NotAuthorisedError
from ..services.contact import ContactService
from ..services.contact_directory import ContactDirectoryService, ContactInUseError

router = APIRouter(prefix="/contacts", tags=["llc-contacts"])

_get_svc = lazy_singleton(ContactService)
_get_directory = lazy_singleton(ContactDirectoryService)

# Conservative allow-list — digits, leading +, spaces, and the punctuation a
# phone number legitimately contains. Never free text: a contact's phone
# field must not become a place to smuggle arbitrary strings.
_PHONE_PATTERN = re.compile(r"^\+?[0-9()\-.\s]{3,64}$")
_NOTES_MAX_LENGTH = 2000


def _svc() -> ContactService:
    return _get_svc()


def _actor_id(current_user: dict) -> uuid.UUID:
    """Derive the acting user's id from the authenticated session, never the
    client-supplied body/query (#13969 review M1 — a client-supplied ``actor``
    let the audit trail's actor identity and USER/SYSTEM discriminator be
    whatever the caller typed, and an unparseable value was an unhandled 500
    in ``ActivityLogService.record``)."""
    raw = current_user.get("id") or current_user.get("user_id")
    return uuid.UUID(str(raw))


def _strip_full_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("full_name must not be blank")
    return stripped


# ------------------------------------------------------------------ Schemas


class ContactCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = Field(None, max_length=320)
    phone: Optional[str] = Field(None, pattern=_PHONE_PATTERN.pattern, max_length=64)
    role_title: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=_NOTES_MAX_LENGTH)

    _strip_full_name = field_validator("full_name")(_strip_full_name)


class ContactUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = Field(None, max_length=320)
    phone: Optional[str] = Field(None, pattern=_PHONE_PATTERN.pattern, max_length=64)
    role_title: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=_NOTES_MAX_LENGTH)

    _strip_full_name = field_validator("full_name")(lambda v: _strip_full_name(v) if v is not None else v)


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


class ContactMergeRequest(BaseModel):
    """Which duplicate folds into which survivor. Both named explicitly."""

    keep_id: uuid.UUID
    merge_id: uuid.UUID


# NOTE ON ROUTE ORDER: every path below is declared BEFORE "/{company_id}".
# That parameter is a `uuid.UUID`, so "directory" would be parsed as one and
# rejected with a 422 rather than falling through — a literal segment placed
# after a typed catch-all is unreachable, and the failure looks like a broken
# endpoint rather than a routing mistake.


@router.get("/directory", response_model=List[ContactResponse])
async def list_directory(
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    _ctx: TenantContext = Depends(require_org_context),
) -> List[ContactResponse]:
    """The shared people directory (#13998).

    Company OS companies are departments of one real company, and people belong
    to the business rather than to a department — so this takes no company id.
    Authentication is still required; a shared directory is not a public one.
    """
    contacts = await _get_directory().list_directory(session)
    return [ContactResponse.model_validate(c) for c in contacts]


@router.get("/directory/duplicates", response_model=List[List[uuid.UUID]])
async def list_duplicate_candidates(
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    _ctx: TenantContext = Depends(require_org_context),
) -> List[List[uuid.UUID]]:
    """Groups of contacts sharing a mailbox — suggestions for a human to review.

    Ids only, and nothing is changed: two people can legitimately share
    ``info@supplier``, so merging is always an explicit act (see below).
    """
    return await _get_directory().find_duplicate_candidates(session)


@router.post("/{company_id}/merge", response_model=ContactResponse)
async def merge_contacts(
    company_id: uuid.UUID,
    body: ContactMergeRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ContactResponse:
    """Fold one contact into another, moving its role tenures.

    Company-scoped because the *authority* to merge is a department admin's,
    even though the directory itself is shared.
    """
    assert_company_access(ctx, company_id)
    try:
        survivor = await _get_directory().merge(
            session,
            company_id=company_id,
            keep_id=body.keep_id,
            merge_id=body.merge_id,
            actor_user_id=_actor_id(current_user),
        )
    except NotAuthorisedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await session.commit()
    return ContactResponse.model_validate(survivor)


async def _delete_via_directory(
    *,
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    session: AsyncSession,
    current_user: dict,
) -> None:
    """Shared body for both delete routes (#14464 review — one guard, two doors).

    ``ContactDirectoryService.delete`` is the only path that consults
    ``companies_for_contact`` and refuses while a role is held anywhere — so
    every route that deletes a contact must call it rather than
    ``ContactService.delete``, which only ever knew about one company.
    """
    try:
        deleted = await _get_directory().delete(
            session,
            company_id=company_id,
            contact_id=contact_id,
            actor_user_id=_actor_id(current_user),
        )
    except ContactInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "company_ids": [str(c) for c in exc.company_ids]},
        ) from exc
    except NotAuthorisedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    await session.commit()


@router.delete("/{company_id}/directory/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_from_directory(
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    """Remove a person from the shared directory.

    409, not 400, when they still hold a role: the request is valid and the
    caller is authorised — the obstacle is state elsewhere, and the response
    names which departments still depend on them.
    """
    assert_company_access(ctx, company_id)
    await _delete_via_directory(
        company_id=company_id,
        contact_id=contact_id,
        session=session,
        current_user=current_user,
    )


class DepartmentContacts(BaseModel):
    """A department's people, split by whether a role explains their presence."""

    with_role: List[ContactResponse]
    unassigned: List[ContactResponse]


@router.get("/{company_id}/involved", response_model=DepartmentContacts)
async def list_involved_contacts(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> DepartmentContacts:
    """Contacts on this department's org chart (#13998).

    Two groups rather than one list: people whose presence a role explains, and
    people carrying the legacy per-company stamp with no role yet. Merging them
    would assert involvement nobody recorded; hiding the second group would make
    people vanish from a department already using them.
    """
    assert_company_access(ctx, company_id)
    groups = await _get_directory().list_for_department(session, company_id)
    return DepartmentContacts(
        with_role=[ContactResponse.model_validate(c) for c in groups["with_role"]],
        unassigned=[ContactResponse.model_validate(c) for c in groups["unassigned"]],
    )


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
        actor=_actor_id(_current_user),
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
    contact = await _svc().update(session, company_id, contact_id, actor=_actor_id(_current_user), **updates)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    await session.commit()
    return ContactResponse.model_validate(contact)


@router.delete("/{company_id}/{contact_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_contact(
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    """Permanently delete the contact — its PII no longer exists at rest afterward.

    Delegates to :meth:`ContactDirectoryService.delete` (#14464 review) rather
    than ``ContactService.delete``. The directory is shared across companies, so
    a delete here is global — routing it through the same guard as
    ``/{company_id}/directory/{contact_id}`` is what stops a plain member of the
    contact's legacy company from hard-deleting someone who still holds a role
    (and therefore permissions) in a company they were never a member of.
    """
    assert_company_access(ctx, company_id)
    await _delete_via_directory(
        company_id=company_id,
        contact_id=contact_id,
        session=session,
        current_user=current_user,
    )
