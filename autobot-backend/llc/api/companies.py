# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC Company API routes (GH#8211, GH#8223, GH#8245).

Route group: /llc/companies
  GET    /                         — list root companies (no parent)
  POST   /                         — create a company
  GET    /{id}                     — get a single company
  PATCH  /{id}                     — update a company
  DELETE /{id}                     — soft-delete a company
  GET    /{id}/tree                — recursive sub-company tree
  GET    /{id}/ancestry            — ancestors from root to this company
  POST   /{id}/activate            — status transition -> ACTIVE (GH#12211)
  POST   /{id}/suspend             — status transition -> PAUSED (GH#12211)
  POST   /{id}/offboard            — status transition -> OFFBOARDING (GH#12234)
  POST   /{id}/archive             — status transition -> ARCHIVED (GH#12211)
  POST   /{id}/members             — add a member (GH#8223)
  DELETE /{id}/members/{user_id}   — remove a member (GH#8223)
  GET    /{id}/members             — list members (GH#8223)
  POST   /{id}/export/template     — export structural template, secrets scrubbed (GH#8245)
  POST   /{id}/export/snapshot     — full-state export for backup/migration (GH#8245)

All endpoints enforce company_id scoping via the org_id path or
the authenticated session's organization context.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import _parse_uuid_safe, get_current_user, require_org_context
from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.logging_manager import get_logger
from llc.deps import assert_company_access, get_session, service_dep
from llc.kb.collections import KbCollectionManager
from llc.models.company import (
    CompanyAncestor,
    CompanyCreate,
    CompanyRead,
    CompanyTreeNode,
    CompanyUpdate,
)
from llc.models.enums import ExternalPMType, LLCCompanyStatus, MembershipRole, WorkItemStatus
from llc.models.membership import LLCCompanyMembership
from llc.services.backlog import BacklogService
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
from llc.services.portability import PortabilityService
from user_management.database import get_async_session
from user_management.models.organization import Organization
from user_management.services import TenantContext

logger = get_logger(__name__)

_backlog_svc = service_dep(BacklogService)

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


def _is_platform_admin(current_user: dict) -> bool:
    """Platform-admin detection mirroring ``get_tenant_context`` (#12233).

    The collection routes (list/create) carry no ``company_id`` path param, so
    they authenticate with ``get_current_user`` (not ``require_org_context``)
    and derive admin status from the JWT the same way the tenant-context
    dependency does: an explicit ``is_platform_admin`` flag or ``role == "admin"``.
    """
    return bool(current_user.get("is_platform_admin")) or is_admin_role(current_user.get("role"))


def _current_user_id(current_user: dict) -> str:
    """Return the caller's user id, or raise 401 when absent/malformed (#12233).

    #12325: validate the JWT subject as a UUID the same way ``get_tenant_context``
    does (``_parse_uuid_safe``) — a non-UUID subject is a bad token and must yield
    a clean 401, not a 500 later when it reaches a ``uuid.UUID(user_id)`` cast in
    the membership query.
    """
    raw = current_user.get("user_id") or current_user.get("id") or current_user.get("sub")
    parsed = _parse_uuid_safe(str(raw)) if raw else None
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return str(parsed)


@router.get("/", response_model=List[CompanyRead])
async def list_companies(
    include_archived: bool = Query(
        False,
        description="Include ARCHIVED companies (hidden by default so retired entries do not clutter the list).",
    ),
    svc: CompanyService = Depends(_get_service),
    current_user: dict = Depends(get_current_user),
    membership_svc: MembershipService = Depends(_get_membership_service),
) -> List[CompanyRead]:
    """List top-level companies (parent_org_id IS NULL) visible to the caller.

    Tenant scope (#12233): previously unauthenticated and returned *every*
    tenant's root company — cross-tenant enumeration of names/budgets. Now
    authenticated; non-admins see only companies they are a member of, while
    platform admins still see all roots. Membership is the same tenant
    primitive ``get_tenant_context`` uses to authorise ``X-Organization-Id``.

    Archive visibility (#12212): ARCHIVED companies are excluded unless
    ``include_archived`` is set, keeping the default list free of retired
    companies while leaving them recoverable via the "show archived" toggle.
    """
    companies = await svc.list_root_companies(include_archived=include_archived)
    if _is_platform_admin(current_user):
        return [_to_read(c) for c in companies]
    user_id = _current_user_id(current_user)
    # #12325: one membership query for the caller, then an in-memory filter —
    # replaces an ``is_member`` round-trip per root (an N+1 that scaled with the
    # total system-wide tenant count). Non-members still match nothing.
    member_ids = await membership_svc.list_member_company_ids(svc.session, user_id)
    visible = [c for c in companies if c.id in member_ids]
    return [_to_read(c) for c in visible]


@router.post("/", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreate,
    svc: CompanyService = Depends(_get_service),
    current_user: dict = Depends(get_current_user),
    membership_svc: MembershipService = Depends(_get_membership_service),
) -> CompanyRead:
    """Create a company (root, or a sub-company under an owned parent).

    Tenant scope (#12233): previously unauthenticated — any caller could create
    a company and, by supplying ``parent_org_id``, graft one under *another*
    tenant's company. Now authenticated; a non-admin may only create a
    sub-company under a parent they belong to (cross-tenant parent → 404, so the
    parent's existence is not disclosed). Root creation (no ``parent_org_id``,
    the creation-wizard flow) is open to any authenticated user. The creator is
    recorded as the company ``OWNER`` so they can immediately access it and it
    surfaces in their tenant-scoped ``list_companies``.
    """
    user_id = _current_user_id(current_user)
    if body.parent_org_id is not None and not _is_platform_admin(current_user):
        if not await membership_svc.is_member(svc.session, str(body.parent_org_id), user_id):
            # 404 (not 403): a cross-tenant caller must not distinguish "not my
            # company" from "doesn't exist" — identical semantics to
            # assert_company_access (#12238).
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    try:
        org = await svc.create(body)
        await membership_svc.add_member(svc.session, str(org.id), user_id, MembershipRole.OWNER)
        # GH#12323: serialize the response AND ensure the KB collections BEFORE
        # commit — mirroring the #12309/#12321 "serialize before commit" invariant
        # the transition handlers use. If either step fails the except handler's
        # rollback undoes the INSERT, so a 500 never leaves a committed-but-
        # unreported company (previously commit() ran first, stranding the row).
        # ensure_collection is idempotent (get_or_create), so a rollback after a
        # partial KB pass — or a commit failure after a full one — leaves only
        # harmless empty collections that the next create call reuses. create()'s
        # INSERT populates updated_at via RETURNING, so no refresh is needed here.
        read = _to_read(org)
        for suffix in (None, KbCollectionManager.AGENTS_SUFFIX, KbCollectionManager.DECISIONS_SUFFIX):
            await _kb_manager.ensure_collection(KbCollectionManager.COMPANY_PREFIX, org.id, suffix)
        await svc.session.commit()
        return read
    except CompanyIssuePrefixConflictError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Internal server error")
    except CompanyBudgetError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Internal server error")
    except CompanyCycleError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Internal server error")
    except CompanyNotFoundError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")
    except Exception:
        await svc.session.rollback()
        raise


@router.get("/{company_id}", response_model=CompanyRead)
async def get_company(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyRead:
    # Issue #12233: tenant authz — caller's org must match company_id unless
    # platform admin. Shared guard (#12238), identical 404 semantics.
    assert_company_access(ctx, company_id)
    try:
        org = await svc.get(company_id)
        return _to_read(org)
    except CompanyNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")


@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    svc: CompanyService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyRead:
    # Issue #12233: tenant authz — caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    try:
        org = await svc.update(company_id, body)
        # GH#12309: serialize BEFORE commit so that if response building ever
        # fails the except handler's rollback still undoes the change — never
        # leave a committed-but-500 state where the DB and caller disagree.
        read = _to_read(org)
        await svc.session.commit()
        return read
    except CompanyNotFoundError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")
    except CompanyIssuePrefixConflictError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Internal server error")
    except CompanyBudgetError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Internal server error")
    except CompanyCycleError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Internal server error")
    except Exception:
        await svc.session.rollback()
        raise


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    # Issue #12233: tenant authz — caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    try:
        await svc.delete(company_id)
        await svc.session.commit()
    except CompanyNotFoundError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")
    except CompanyHasChildrenError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Internal server error")
    except Exception:
        await svc.session.rollback()
        raise


class CompanyStatusTransitionRequest(BaseModel):
    """Optional payload for a status transition (e.g. a suspend reason)."""

    reason: Optional[str] = None


@router.post("/{company_id}/activate", response_model=CompanyRead)
async def activate_company(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyRead:
    """Transition a company to ACTIVE (from ONBOARDING or PAUSED).

    Issue #12211: this is the dedicated transition the CompanyUpdate schema
    defers to (``llc_status`` is intentionally not PATCH-able) — without it a
    company was stuck in ONBOARDING forever. Tenant access is enforced the same
    way as ``get_org_chart``/``reorder_backlog``: the caller's org must match
    *company_id* unless they are a platform admin.
    """
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    try:
        org = await svc.activate(company_id)
        # GH#12309: serialize BEFORE commit so a failed response never persists
        # a partial transition (commit only lands on the success path).
        read = _to_read(org)
        await svc.session.commit()
        return read
    except CompanyNotFoundError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")
    except ValueError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except Exception:
        await svc.session.rollback()
        raise


@router.post("/{company_id}/suspend", response_model=CompanyRead)
async def suspend_company(
    company_id: uuid.UUID,
    body: Optional[CompanyStatusTransitionRequest] = None,
    svc: CompanyService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyRead:
    """Transition a company to PAUSED (from ONBOARDING or ACTIVE). Issue #12211.

    Tenant-scoped: caller's org must match *company_id* unless platform admin.
    """
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    try:
        org = await svc.suspend(company_id, reason=body.reason if body else None)
        # GH#12309: serialize BEFORE commit (commit only on the success path).
        read = _to_read(org)
        await svc.session.commit()
        return read
    except CompanyNotFoundError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")
    except ValueError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except Exception:
        await svc.session.rollback()
        raise


@router.post("/{company_id}/offboard", response_model=CompanyRead)
async def offboard_company(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyRead:
    """Transition a company to OFFBOARDING (from ACTIVE). Issue #12234.

    Completes the lifecycle started in #12211: OFFBOARDING was already a
    valid archive() source but nothing ever transitioned a company into it.
    Tenant-scoped: caller's org must match *company_id* unless platform admin.
    """
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    try:
        org = await svc.offboard(company_id)
        # GH#12309: serialize BEFORE commit (commit only on the success path).
        read = _to_read(org)
        await svc.session.commit()
        return read
    except CompanyNotFoundError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")
    except ValueError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except Exception:
        await svc.session.rollback()
        raise


@router.post("/{company_id}/archive", response_model=CompanyRead)
async def archive_company(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyRead:
    """Transition a company to ARCHIVED (from PAUSED or OFFBOARDING). Issue #12211.

    Tenant-scoped: caller's org must match *company_id* unless platform admin.
    """
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    try:
        org = await svc.archive(company_id)
        # GH#12309: serialize BEFORE commit (commit only on the success path).
        read = _to_read(org)
        await svc.session.commit()
        return read
    except CompanyNotFoundError:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")
    except ValueError as exc:
        await svc.session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except Exception:
        await svc.session.rollback()
        raise


@router.get("/{company_id}/tree", response_model=CompanyTreeNode)
async def get_company_tree(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyTreeNode:
    # Issue #12233: tenant authz — caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    try:
        return await svc.get_sub_company_tree(company_id)
    except CompanyNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")


@router.get("/{company_id}/ancestry", response_model=List[CompanyAncestor])
async def get_company_ancestry(
    company_id: uuid.UUID,
    svc: CompanyService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[CompanyAncestor]:
    # Issue #12233: tenant authz — caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
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
    except CompanyNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")


# ------------------------------------------------------------------
# KB inheritance routes (GH#8241)
# ------------------------------------------------------------------


class KbAncestryCollection(BaseModel):
    """A single entry in the KB ancestry-collection chain."""

    collection_name: str
    company_id: str
    weight: float


@router.get("/{company_id}/kb/ancestry-collections", response_model=List[KbAncestryCollection])
async def get_kb_ancestry_collections(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[KbAncestryCollection]:
    """Return the resolved KB collection chain for a company (GH#8241).

    Lists each collection in the parent hierarchy, with the weight that would
    be applied when merging search results. Useful for inspecting what context
    a sub-company agent inherits.
    """
    # Issue #12233: tenant authz — caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    from llc.kb.inheritance import KbInheritanceResolver

    # get_query_collections only needs the session; no RAG assembler required (GH#8570).
    resolver = KbInheritanceResolver()
    try:
        chain = await resolver.get_query_collections(session, str(company_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")

    return [
        KbAncestryCollection(
            collection_name=collection_name,
            # False positive: the ValueError above is caught and
            # re-raised as a generic HTTPException; no exception data flows into this response.
            company_id=collection_name.split(":")[0],
            weight=weight,
        )
        for collection_name, weight in chain
    ]


# ------------------------------------------------------------------
# Member management routes (GH#8223)
# ------------------------------------------------------------------


@router.get("/{company_id}/members")
async def list_members(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    svc: MembershipService = Depends(_get_membership_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    # Issue #12233: tenant authz — caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    from sqlalchemy import select  # noqa: PLC0415

    from user_management.models.user import User  # noqa: PLC0415

    members = await svc.list_members(session, str(company_id))
    # Resolve display names so the assignee/reviewer pickers show people, not UUIDs.
    user_ids = [m.user_id for m in members]
    names: Dict[uuid.UUID, str] = {}
    if user_ids:
        rows = (
            await session.execute(select(User.id, User.display_name, User.username).where(User.id.in_(user_ids)))
        ).all()
        names = {uid: (dn or un) for uid, dn, un in rows}
    return [{**_to_member_read(m), "display_name": names.get(m.user_id)} for m in members]


@router.post("/{company_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    company_id: uuid.UUID,
    body: MemberAddRequest,
    session: AsyncSession = Depends(get_async_session),
    svc: MembershipService = Depends(_get_membership_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    # Issue #12233: tenant authz — caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    try:
        membership = await svc.add_member(session, str(company_id), str(body.user_id), body.role)
        await session.commit()
        return _to_member_read(membership)
    except MemberAlreadyExistsError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Internal server error")


@router.delete("/{company_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    svc: MembershipService = Depends(_get_membership_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    # Issue #12233: tenant authz — caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    try:
        await svc.remove_member(session, str(company_id), str(user_id))
        await session.commit()
    except MemberNotFoundError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")


# ------------------------------------------------------------------
# External PM config (GH#8257)
# ------------------------------------------------------------------
class PMConfigSetRequest(BaseModel):
    pm_type: ExternalPMType
    credentials: Dict[str, Any]


class PMConfigRead(BaseModel):
    pm_type: Optional[str]
    configured: bool


@router.patch("/{company_id}/pm-config", response_model=PMConfigRead)
async def set_pm_config(
    company_id: uuid.UUID,
    body: PMConfigSetRequest,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> PMConfigRead:
    """Store encrypted PM credentials for a company (GH#8257)."""
    # Issue #12233: tenant authz — writing another tenant's PM credentials is a
    # cross-tenant compromise; caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    import json

    from sqlalchemy import select, update

    from autobot_shared.field_encryption import encrypt_field

    row = await session.execute(select(Organization.id).where(Organization.id == company_id))
    if row.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    encrypted = encrypt_field(json.dumps(body.credentials, ensure_ascii=False))
    await session.execute(
        update(Organization)
        .where(Organization.id == company_id)
        .values(external_pm_type=body.pm_type.value, external_pm_config=encrypted)
    )
    await session.commit()
    return PMConfigRead(pm_type=body.pm_type.value, configured=True)


@router.post("/{company_id}/pm-config/test")
async def test_pm_config(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Test connectivity to the configured external PM system (GH#8257)."""
    # Issue #12233: tenant authz — caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    import json

    from sqlalchemy import select

    from autobot_shared.field_encryption import decrypt_field

    row = await session.execute(
        select(Organization.external_pm_type, Organization.external_pm_config).where(Organization.id == company_id)
    )
    result = row.one_or_none()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    pm_type, encrypted_config = result
    if not pm_type or pm_type == "none" or not encrypted_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No PM integration configured for this company",
        )
    try:
        pm_config = json.loads(decrypt_field(encrypted_config))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt PM config",
        )
    try:
        health = await _test_pm_connectivity(pm_type, pm_config)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": health.get("ok", False), "details": health}


async def _test_pm_connectivity(pm_type: str, pm_config: Dict[str, Any]) -> Dict[str, Any]:
    from integrations.base import IntegrationConfig, IntegrationStatus
    from integrations.project_management_integration import (
        AsanaIntegration,
        JiraIntegration,
        TrelloIntegration,
    )

    if pm_type == "jira":
        cfg = IntegrationConfig(
            name="jira",
            provider="jira",
            base_url=pm_config.get("base_url", ""),
            username=pm_config.get("username", ""),
            api_key=pm_config.get("api_key", ""),
        )
        health = await JiraIntegration(cfg).test_connection()
    elif pm_type == "trello":
        cfg = IntegrationConfig(
            name="trello",
            provider="trello",
            token=pm_config.get("token", ""),
        )
        health = await TrelloIntegration(cfg).test_connection()
    elif pm_type == "asana":
        cfg = IntegrationConfig(name="asana", provider="asana", token=pm_config.get("token", ""))
        health = await AsanaIntegration(cfg).test_connection()
    else:
        return {"ok": False, "error": f"Unsupported pm_type: {pm_type}"}
    return {
        "ok": health.status == IntegrationStatus.CONNECTED,
        "status": health.status.value,
        "message": health.message,
        "details": health.details,
    }


# ------------------------------------------------------------------
# Agent search endpoints (GH#8244)
# ------------------------------------------------------------------


class AgentSearchResult(BaseModel):
    agent_id: str
    agent_name: str
    title: str
    role: str
    capabilities: str
    manager_name: Optional[str] = None


# ------------------------------------------------------------------
# Backlog reorder (GH#9861)
# ------------------------------------------------------------------


class BacklogReorderRequest(BaseModel):
    """Bulk-reorder request — ordered list of work item UUIDs.

    Positions are assigned 0..n-1 (deduplicated, preserving first occurrence)
    in the order items appear in the list.  Items belonging to a different
    company are silently skipped (tenant isolation: callers should only submit
    ids they already fetched from this company's backlog).

    ``work_item_ids`` is typed as ``List[uuid.UUID]`` so Pydantic validates
    each entry and returns a 422 for any malformed id — no manual parsing
    needed in the service.
    """

    work_item_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=500)


class BacklogReorderResponse(BaseModel):
    updated: int
    unknown_count: int


@router.post(
    "/{company_id}/backlog/reorder",
    response_model=BacklogReorderResponse,
    status_code=200,
)
async def reorder_backlog(
    company_id: uuid.UUID,
    body: BacklogReorderRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> BacklogReorderResponse:
    """Assign ``backlog_position`` 0..n-1 to the supplied ordered work item ids.

    Tenant access is enforced the same way as ``get_org_chart``: the caller's
    org must match *company_id* unless they are a platform admin.  Unknown or
    cross-tenant ids within the payload are counted in ``unknown_count`` and
    silently skipped (not an error, so that a stale UI with a partially-loaded
    backlog can still submit a reorder without receiving a 400).  A 400 is only
    raised when the entire list is empty (caught by pydantic min_length=1).
    """
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    cid = str(company_id)
    result = await _backlog_svc().bulk_reorder(
        session,
        company_id=cid,
        ordered_ids=[str(i) for i in body.work_item_ids],
    )
    await session.commit()
    return BacklogReorderResponse(**result)


# ------------------------------------------------------------------
# Org chart (GH#9861) — read-only composition of existing models
# ------------------------------------------------------------------


class OrgChartNode(BaseModel):
    """One agent node in the company org chart.

    Composed read-only from ``agent_org_nodes`` (hierarchy/title/role),
    ``llc_agent_budgets`` (budget), and the latest ``llc_heartbeat_runs`` row
    (liveness/status). No new persistence is introduced.
    """

    id: str  # logical agent_id slug (keyspace for budgets/runs/controls)
    # AgentOrgNode UUID PK — the assignment keyspace: work-item assignee_agent_id
    # / handoff target_agent_id reference THIS, not the slug (#10032). Needed so
    # the UI assignee/handoff pickers send the right id.
    node_id: str
    name: str
    title: str
    status: str  # active | idle | error | paused
    adapter_type: str
    is_human: bool
    last_heartbeat: Optional[str]
    budget_spent: float
    budget_total: float
    assigned_item_count: int
    parent_id: Optional[str]
    children: List["OrgChartNode"] = []


class OrgChartResponse(BaseModel):
    nodes: List[OrgChartNode]


def _heartbeat_status_to_org_status(run_status: Optional[str]) -> str:
    """Map an ``LLCRunStatus`` value onto the org-chart node status vocabulary."""
    if run_status == "running":
        return "active"
    # LLCRunStatus failure-ish terminal states (values, not names).
    if run_status in ("failed", "timeout", "interrupted"):
        return "error"
    # completed / cancelled / rate_limited / queued / no-run → idle
    return "idle"


@router.get("/{company_id}/org-chart", response_model=OrgChartResponse)
async def get_org_chart(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> OrgChartResponse:
    """Return the agent reporting hierarchy for a company (GH#9861).

    Read-only composition — joins the org-hierarchy, budget, and latest
    heartbeat for each agent scoped to the company, then assembles a forest
    from the self-referencing ``reports_to`` edges. Tenant access is enforced
    via :func:`require_org_context`.
    """
    from sqlalchemy import func, select

    from llc.models.budget import LLCAgentBudget
    from llc.models.heartbeat_run import LLCHeartbeatRun
    from llc.models.work_item import LLCWorkItem
    from models.agent_org import AgentOrgNode

    cid = str(company_id)
    if str(ctx.org_id) != cid and not ctx.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # 1. Hierarchy rows for the company.
    org_rows = (
        (await session.execute(select(AgentOrgNode).where(AgentOrgNode.company_id == company_id))).scalars().all()
    )

    # 2. Budgets keyed by agent_id.
    budget_rows = (
        (await session.execute(select(LLCAgentBudget).where(LLCAgentBudget.company_id == cid))).scalars().all()
    )
    budgets = {b.agent_id: b for b in budget_rows}

    # 3. Latest heartbeat run per agent (status + liveness).
    subq = (
        select(
            LLCHeartbeatRun.agent_id,
            func.max(LLCHeartbeatRun.created_at).label("latest_at"),
        )
        .where(LLCHeartbeatRun.company_id == company_id)
        .group_by(LLCHeartbeatRun.agent_id)
        .subquery()
    )
    latest_runs = (
        (
            await session.execute(
                select(LLCHeartbeatRun).join(
                    subq,
                    (LLCHeartbeatRun.agent_id == subq.c.agent_id) & (LLCHeartbeatRun.created_at == subq.c.latest_at),
                )
            )
        )
        .scalars()
        .all()
    )
    runs = {r.agent_id: r for r in latest_runs}

    # 4. Assigned work-item counts per agent — single grouped query, no N+1.
    #    "Assigned" means the item has an assignee_agent_id matching the
    #    AgentOrgNode.id (UUID PK) AND the item is not yet in a terminal state.
    #    We join through AgentOrgNode so the result is keyed by AgentOrgNode.agent_id
    #    (the logical string slug used everywhere else), not the UUID PK.  This
    #    correctly handles hire-generated slug agent_ids that differ from the PK.
    #    GH#9980: Use enum members directly so PG serialises to lowercase values
    #    (sa.cast to String was a workaround for the test harness's _rebind_enums
    #    helper — fixing production code to use enum members and letting the
    #    harness handle the rebind is the correct approach; see #9980).
    assign_q = (
        select(
            AgentOrgNode.agent_id,
            func.count(LLCWorkItem.id).label("cnt"),
        )
        .join(AgentOrgNode, AgentOrgNode.id == LLCWorkItem.assignee_agent_id)
        .where(
            LLCWorkItem.company_id == company_id,
            LLCWorkItem.assignee_agent_id.isnot(None),
            LLCWorkItem.status.notin_(
                [WorkItemStatus.DONE, WorkItemStatus.CANCELLED]
            ),  # noqa: E501 — see GH#9980 (enum NAME-vs-value drift)
        )
        .group_by(AgentOrgNode.agent_id)
    )
    assigned_counts: Dict[str, int] = {row.agent_id: row.cnt for row in (await session.execute(assign_q)).all()}

    # 5. Human members (#13936). The org chart is the native place to display the
    #    people of a company, not only its hired agents. Before this, the only
    #    OrgChartNode construction site hardcoded ``is_human=False`` and the
    #    ``llc_company_memberships`` table was never read here, so the human
    #    branch the frontend already renders (OrgTreeNode.vue) was unreachable.
    #
    #    Memberships live in a different keyspace from AgentOrgNode and carry no
    #    ``reports_to`` edge, so they are composed as sibling roots rather than
    #    joined onto the agent forest. No schema change, no migration.
    from user_management.models.user import User  # noqa: PLC0415

    member_rows = (
        (await session.execute(select(LLCCompanyMembership).where(LLCCompanyMembership.company_id == company_id)))
        .scalars()
        .all()
    )

    #    Resolve display names the same way ``list_members`` does, so a person
    #    reads as a person and never as a bare UUID.
    member_names: Dict[uuid.UUID, str] = {}
    if member_rows:
        name_rows = (
            await session.execute(
                select(User.id, User.display_name, User.username).where(User.id.in_([m.user_id for m in member_rows]))
            )
        ).all()
        member_names = {uid: (dn or un) for uid, dn, un in name_rows}

    #    Assigned work-item counts per human — keyed by assignee_user_id, the
    #    human half of the assignment keyspace delivered under #10532. Mirrors
    #    the agent query above: one grouped query, no N+1, terminal states excluded.
    human_assign_q = (
        select(
            LLCWorkItem.assignee_user_id,
            func.count(LLCWorkItem.id).label("cnt"),
        )
        .where(
            LLCWorkItem.company_id == company_id,
            LLCWorkItem.assignee_user_id.isnot(None),
            LLCWorkItem.status.notin_([WorkItemStatus.DONE, WorkItemStatus.CANCELLED]),
        )
        .group_by(LLCWorkItem.assignee_user_id)
    )
    human_counts: Dict[uuid.UUID, int] = {
        row.assignee_user_id: row.cnt for row in (await session.execute(human_assign_q)).all()
    }

    # Compose flat nodes.
    flat: Dict[str, OrgChartNode] = {}
    for row in org_rows:
        budget = budgets.get(row.agent_id)
        run = runs.get(row.agent_id)
        # Budget enrichment: expose token numbers for token-mode agents when
        # the field is populated, otherwise fall back to dollar amounts.
        b_mode = budget.budget_mode if budget else "dollars"
        if b_mode == "tokens" and budget and budget.token_limit is not None:
            b_spent = float(budget.tokens_spent)
            b_total = float(budget.token_limit)
        else:
            b_spent = float(budget.budget_spent) if budget else 0.0
            b_total = float(budget.budget_limit) if budget else 0.0
        flat[row.agent_id] = OrgChartNode(
            id=row.agent_id,
            node_id=str(row.id),  # AgentOrgNode UUID PK (assignment keyspace, #10032)
            name=row.name,
            title=row.title or row.org_role,
            status=_heartbeat_status_to_org_status(run.status if run else None),
            adapter_type=row.org_role,
            is_human=False,
            # Liveness: latest run is picked by created_at; a just-queued run
            # may have no started_at, so fall back to created_at.
            last_heartbeat=(
                (run.started_at or run.created_at).isoformat() if run and (run.started_at or run.created_at) else None
            ),
            budget_spent=b_spent,
            budget_total=b_total,
            assigned_item_count=assigned_counts.get(row.agent_id, 0),
            parent_id=row.reports_to,
            children=[],
        )

    def _chain_resolves_to_root(agent_id: str) -> bool:
        """True if following reports_to from ``agent_id`` ends at a node with no
        (or missing/self) parent without revisiting a node — i.e. no cycle."""
        seen: set[str] = set()
        cur: Optional[OrgChartNode] = flat.get(agent_id)
        while cur is not None and cur.parent_id:
            if cur.id in seen:
                return False  # cycle
            seen.add(cur.id)
            parent = flat.get(cur.parent_id)
            if parent is None or parent.id == cur.id:
                return True  # parent absent/self → effectively rooted
            cur = parent
        return True

    # Assemble the forest from reports_to edges. Attach a node to its parent
    # only when its chain is acyclic; cycle members (and nodes whose parent is
    # absent/self) become roots with no parent edge, so the output is always a
    # true forest — every agent appears exactly once, never infinitely nested.
    roots: List[OrgChartNode] = []
    for node in flat.values():
        parent = flat.get(node.parent_id) if node.parent_id else None
        if parent is not None and parent.id != node.id and _chain_resolves_to_root(node.id):
            parent.children.append(node)
        else:
            roots.append(node)

    # Human members join the forest as roots (#13936). ``id`` is namespaced with
    # a ``user:`` prefix so a person can never collide with an agent slug, while
    # ``node_id`` carries the raw user id — the keyspace ``assignee_user_id``
    # references, so the assignee picker sends the right value.
    #
    # Status is ``idle``: a person has no heartbeat, and ``idle`` is exactly what
    # ``_heartbeat_status_to_org_status`` already returns for an agent with no
    # run. It therefore asserts no liveness we do not have. Budget stays 0/0 —
    # people are not metered by LLCAgentBudget.
    for m in member_rows:
        # ``role`` is mapped through sa.Enum, so the ORM hands back the enum
        # member — str() on it yields "MembershipRole.LEAD", not "lead". Take
        # .value when present so the wire format stays the lowercase label.
        role_label = getattr(m.role, "value", m.role)
        roots.append(
            OrgChartNode(
                id=f"user:{m.user_id}",
                node_id=str(m.user_id),
                name=member_names.get(m.user_id) or str(m.user_id),
                title=str(role_label),
                status="idle",
                adapter_type=str(role_label),
                is_human=True,
                last_heartbeat=None,
                budget_spent=0.0,
                budget_total=0.0,
                assigned_item_count=human_counts.get(m.user_id, 0),
                parent_id=None,
                children=[],
            )
        )

    return OrgChartResponse(nodes=roots)


@router.get("/{company_id}/agents/search")
async def search_agents(
    company_id: uuid.UUID,
    q: str = Query(..., min_length=1, description="Search query for agent capabilities"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Search agents in company by capabilities using RAG.

    Queries the company:agents KB collection for agents matching the capability
    search query. Returns agent metadata and capability descriptions.

    Args:
        company_id: Company ID to search within
        q: Search query (\"who can do X?\", \"security audit expertise\", etc.)
        limit: Max results to return (default 10, max 100)

    Returns:
        List of matching agents with capability metadata.
    """
    # Issue #12233: tenant authz — caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    try:
        from knowledge import get_knowledge_base
        from llc.kb import AgentCapabilityIndexer

        indexer = AgentCapabilityIndexer()
        kb = await get_knowledge_base()
        collection_name = indexer._collection_name(str(company_id))

        try:
            collection = await kb._async_chroma_client.get_collection(collection_name)
        except Exception:
            return {"agents": [], "count": 0, "query": q}

        results = await collection.query(
            query_texts=[q],
            n_results=limit,
            include=["documents", "metadatas"],
        )

        agents = []
        if results.get("ids") and len(results["ids"]) > 0:
            docs = results.get("documents", [[]])[0] if results.get("documents") else []
            for idx, (doc_id, metadata) in enumerate(zip(results["ids"][0], results.get("metadatas", [[]])[0])):
                agents.append(
                    AgentSearchResult(
                        agent_id=metadata.get("agent_id", ""),
                        agent_name=metadata.get("agent_name", ""),
                        title=metadata.get("title", ""),
                        role=metadata.get("role", ""),
                        capabilities=docs[idx] if idx < len(docs) else "",
                        manager_name=metadata.get("manager_name"),
                    )
                )

        return {"agents": agents, "count": len(agents), "query": q}
    except Exception as e:
        logger.exception("Agent search failed for company %s: %s", company_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent search failed: {str(e)}",
        )


# Export endpoints (GH#8245)
def _get_portability_service(session: AsyncSession = Depends(get_async_session)) -> PortabilityService:
    return PortabilityService(session=session)


@router.post("/{company_id}/export/template")
async def export_template(
    company_id: uuid.UUID,
    svc: PortabilityService = Depends(_get_portability_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> JSONResponse:
    """Export a portable structural template for the company.

    Returns a JSON file download with company meta, agents (secrets scrubbed),
    goals, active routines, projects, portfolios, and up to 20 seed work items.
    Secret values are never exported — only ``{{SECRET_NAME}}`` placeholders.
    """
    # Issue #12233: tenant authz — exporting another tenant's structure is a
    # cross-tenant data leak; caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    payload = await svc.export_template(company_id)
    filename = f"company_{company_id}_template.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{company_id}/export/snapshot")
async def export_snapshot(
    company_id: uuid.UUID,
    svc: PortabilityService = Depends(_get_portability_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> JSONResponse:
    """Export a full-state snapshot for backup/migration.

    Extends the template export with all work items, sprint history, and KB
    collection names (not content).
    """
    # Issue #12233: tenant authz — a full-state snapshot of another tenant is a
    # cross-tenant data leak; caller's org must match company_id unless admin.
    assert_company_access(ctx, company_id)  # shared guard (#12238)
    payload = await svc.export_snapshot(company_id)
    filename = f"company_{company_id}_snapshot.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
