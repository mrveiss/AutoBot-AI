# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC Company API routes (GH#8211, GH#8223).

Route group: /llc/companies
  GET    /                       — list root companies (no parent)
  POST   /                       — create a company
  GET    /{id}                   — get a single company
  PATCH  /{id}                   — update a company
  DELETE /{id}                   — soft-delete a company
  GET    /{id}/tree              — recursive sub-company tree
  GET    /{id}/ancestry          — ancestors from root to this company
  POST   /{id}/members           — add a member (GH#8223)
  DELETE /{id}/members/{user_id} — remove a member (GH#8223)
  GET    /{id}/members           — list members (GH#8223)

All endpoints enforce company_id scoping via the org_id path or
the authenticated session's organization context.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from llc.kb.collections import KbCollectionManager
from llc.models.company import (
    CompanyAncestor,
    CompanyCreate,
    CompanyRead,
    CompanyTreeNode,
    CompanyUpdate,
)
from llc.models.enums import LLCCompanyStatus, MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.services.company import (
    CompanyBudgetError,
    CompanyCycleError,
    CompanyHasChildrenError,
    CompanyIssuePrefixConflictError,
    CompanyNotFoundError,
    CompanyService,
)
from llc.services.membership_service import (
    MemberAlreadyExistsError,
    MemberNotFoundError,
    MembershipService,
)
from user_management.database import get_async_session
from user_management.models.organization import Organization

router = APIRouter(prefix="/companies", tags=["llc-companies"])

_kb_manager = KbCollectionManager()


# ------------------------------------------------------------------
# Member management schemas (GH#8223)
# ------------------------------------------------------------------


class MemberAddRequest(BaseModel):
    user_id: uuid.UUID
    role: MembershipRole = MembershipRole.MEMBER


class MemberRead(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    user_id: uuid.UUID
    role: MembershipRole
    created_at: Any

    model_config = {"from_attributes": True}


def _to_member_read(m: LLCCompanyMembership) -> dict:
    return {
        "id": str(m.id),
        "company_id": str(m.company_id),
        "user_id": str(m.user_id),
        "role": m.role,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _get_membership_service() -> MembershipService:
    return MembershipService()


def _to_read(org: Organization) -> CompanyRead:
    return CompanyRead(
        id=org.id,
        name=org.name,
        slug=org.slug,
        description=org.description,
        issue_prefix=org.issue_prefix,
        issue_counter=org.issue_counter,
        budget_monthly_cents=org.budget_monthly_cents,
        spent_monthly_cents=org.spent_monthly_cents,
        brand_color=org.brand_color,
        require_approval_for_hires=org.require_approval_for_hires,
        parent_org_id=org.parent_org_id,
        llc_status=LLCCompanyStatus(org.llc_status),
        pause_reason=org.pause_reason,
        paused_at=org.paused_at,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


def _get_service(session: AsyncSession = Depends(get_async_session)) -> CompanyService:
    return CompanyService(session=session)


@router.get("/", response_model=List[CompanyRead])
async def list_companies(svc: CompanyService = Depends(_get_service)) -> List[CompanyRead]:
    """List top-level companies (parent_org_id IS NULL)."""
    companies = await svc.list_root_companies()
    return [_to_read(c) for c in companies]


@router.post("/", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreate,
    svc: CompanyService = Depends(_get_service),
) -> CompanyRead:
    try:
        org = await svc.create(body)
        await svc.session.commit()
        for suffix in (None, KbCollectionManager.AGENTS_SUFFIX, KbCollectionManager.DECISIONS_SUFFIX):
            await _kb_manager.ensure_collection(KbCollectionManager.COMPANY_PREFIX, org.id, suffix)
        return _to_read(org)
    except CompanyIssuePrefixConflictError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except CompanyBudgetError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except CompanyCycleError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except CompanyNotFoundError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        await svc.session.rollback()
        raise


@router.get("/{company_id}", response_model=CompanyRead)
async def get_company(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
) -> CompanyRead:
    try:
        org = await svc.get(company_id)
        return _to_read(org)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    svc: CompanyService = Depends(_get_service),
) -> CompanyRead:
    try:
        org = await svc.update(company_id, body)
        await svc.session.commit()
        return _to_read(org)
    except CompanyNotFoundError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except CompanyIssuePrefixConflictError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except CompanyBudgetError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception:
        await svc.session.rollback()
        raise


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
) -> None:
    try:
        await svc.delete(company_id)
        await svc.session.commit()
    except CompanyNotFoundError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except CompanyHasChildrenError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except Exception:
        await svc.session.rollback()
        raise


@router.get("/{company_id}/tree", response_model=CompanyTreeNode)
async def get_company_tree(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
) -> CompanyTreeNode:
    try:
        return await svc.get_sub_company_tree(company_id)
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{company_id}/ancestry", response_model=List[CompanyAncestor])
async def get_company_ancestry(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
) -> List[CompanyAncestor]:
    try:
        ancestors = await svc.get_ancestry(company_id)
        return [
            CompanyAncestor(
                id=a.id,
                name=a.name,
                slug=a.slug,
                llc_status=LLCCompanyStatus(a.llc_status),
            )
            for a in ancestors
        ]
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ------------------------------------------------------------------
# Member management routes (GH#8223)
# ------------------------------------------------------------------


@router.get("/{company_id}/members")
async def list_members(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    svc: MembershipService = Depends(_get_membership_service),
) -> List[Dict[str, Any]]:
    members = await svc.list_members(session, str(company_id))
    return [_to_member_read(m) for m in members]


@router.post("/{company_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    company_id: uuid.UUID,
    body: MemberAddRequest,
    session: AsyncSession = Depends(get_async_session),
    svc: MembershipService = Depends(_get_membership_service),
) -> Dict[str, Any]:
    try:
        membership = await svc.add_member(session, str(company_id), str(body.user_id), body.role)
        await session.commit()
        return _to_member_read(membership)
    except MemberAlreadyExistsError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete("/{company_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    svc: MembershipService = Depends(_get_membership_service),
) -> None:
    try:
        await svc.remove_member(session, str(company_id), str(user_id))
        await session.commit()
    except MemberNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
