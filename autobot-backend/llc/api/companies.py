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
  GET    /{id}/teams               — list teams + their member user ids (GH#13938)
  POST   /{id}/export/template     — export structural template, secrets scrubbed (GH#8245)
  POST   /{id}/export/snapshot     — full-state export for backup/migration (GH#8245)

All endpoints enforce company_id scoping via the org_id path or
the authenticated session's organization context.
"""

import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import _parse_uuid_safe, get_current_user, require_org_context
from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.models.user import resolve_display_name
from llc.deps import assert_company_access, get_session, service_dep
from llc.kb.collections import KbCollectionManager
from llc.models.company import (
    CompanyAncestor,
    CompanyCreate,
    CompanyRead,
    CompanyTreeNode,
    CompanyUpdate,
)
from llc.models.enums import (
    AssigneeType,
    ExternalPMType,
    LLCAgentStatus,
    LLCCompanyStatus,
    MembershipRole,
    WorkItemStatus,
)
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
from llc.services.org_chart_placement import apply_reporting_lines, assemble_forest
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
        # #13920: drop the three collections create_company's ensure_collection
        # loop makes (base, agents, decisions). Derived from the same constants
        # rather than restated, so a fourth suffix cannot be created and then
        # silently never cleaned up.
        for suffix in (None, KbCollectionManager.AGENTS_SUFFIX, KbCollectionManager.DECISIONS_SUFFIX):
            await _kb_manager.drop_collection(KbCollectionManager.COMPANY_PREFIX, company_id, suffix)
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
    # #13956: whether each member may still be given work. Carried, not
    # filtered -- see `_person_is_active`. The picker needs both facts: who is
    # a member, and which of them can take an assignment.
    active: Dict[uuid.UUID, bool] = {}
    if user_ids:
        # #13957: ``User.full_name`` is a hybrid property, so the canonical
        # "display_name, else username" rule is selected in SQL here rather than
        # re-spelled in the comprehension below. This is an inner select on
        # ``users``, so a returned row always has the NOT NULL ``username`` to
        # fall back to and the two-rung rule is complete.
        rows = (
            await session.execute(
                select(User.id, User.full_name, User.is_active, User.deleted_at).where(User.id.in_(user_ids))
            )
        ).all()
        names = {uid: name for uid, name, _ia, _da in rows}
        active = {uid: _person_is_active(ia, da) for uid, _name, ia, da in rows}
    return [
        {
            **_to_member_read(m),
            "display_name": names.get(m.user_id),
            # A membership whose user row is missing entirely resolves to
            # False: nothing is known about them, and unknown must not read as
            # available.
            "is_active": active.get(m.user_id, False),
        }
        for m in members
    ]


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

if TYPE_CHECKING:
    # Only for `_compose_agent_node`'s type hints (#14184) — `get_org_chart`
    # imports these lazily at call time for the actual query code, and this
    # block costs nothing at runtime, so that import-lazing is unaffected.
    from llc.models.budget import LLCAgentBudget
    from llc.models.heartbeat_run import LLCHeartbeatRun
    from models.agent_org import AgentOrgNode


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
    status: str  # active | idle | error | paused | terminated
    adapter_type: str
    is_human: bool
    # #13956: whether this person can still be given work. `None` for agents,
    # which have their own liveness in `status` and are not deactivated by the
    # user-management lifecycle at all -- so a bare `False` default would
    # quietly assert every agent is inactive.
    is_active: Optional[bool] = None
    last_heartbeat: Optional[str]
    budget_spent: float
    budget_total: float
    assigned_item_count: int
    parent_id: Optional[str]
    children: List["OrgChartNode"] = []


class OrgChartResponse(BaseModel):
    nodes: List[OrgChartNode]


def _person_is_active(is_active: Optional[bool], deleted_at: Optional[Any]) -> bool:
    """Whether a person may still be given work (#13956).

    Both the members picker and the org chart ask this, and the issue is
    explicit that they must not diverge -- so neither computes it inline.

    Deliberately *not* a filter. The org chart is where a company reads its own
    structure, and dropping someone who has left rewrites that structure
    silently: their work items stay behind (they are only reassigned
    explicitly), the role they held stays behind, and a chart that omits them
    cannot explain who those items belong to. Precedent in this module already
    chose the same way -- ``_compose_human_nodes`` uses an outer join
    specifically so "a membership whose user row is gone still yields a node
    instead of vanishing silently".

    So the answer is rendered, not applied: the surfaces show the person and
    mark them, and the picker refuses them as an assignee.

    A user row that is missing entirely (outer join miss) is inactive: nothing
    is known about them, and "unknown" must never read as "available".
    """
    if deleted_at is not None:
        return False
    # `None` reaches here from an outer-join miss, not from a real column value.
    return bool(is_active)


def _heartbeat_status_to_org_status(run_status: Optional[str]) -> str:
    """Map an ``LLCRunStatus`` value onto the org-chart node status vocabulary."""
    if run_status == "running":
        return "active"
    # LLCRunStatus failure-ish terminal states (values, not names).
    if run_status in ("failed", "timeout", "interrupted"):
        return "error"
    # completed / cancelled / rate_limited / queued / no-run → idle
    return "idle"


# Persisted ``LLCAgentStatus`` values that must win over the heartbeat-derived
# status (#14108). Both are terminal *from the org chart's point of view*: an
# agent an operator paused or terminated must read that way even while a
# stale/queued heartbeat run would otherwise derive ``active`` or ``idle``.
_STOP_STATUSES = frozenset({LLCAgentStatus.PAUSED.value, LLCAgentStatus.TERMINATED.value})


def _resolve_org_status(persisted_status: Optional[str], run_status: Optional[str]) -> str:
    """Combine ``agent_org_nodes.status`` with the derived heartbeat status.

    Precedence rule (#14108): an explicit *stop* lifecycle state — ``paused``
    or ``terminated`` — always wins over the heartbeat-derived liveness. A
    terminated agent must never read as ``active``/``idle`` merely because a
    stale ``llc_heartbeat_runs`` row exists; the same is true of ``paused``.
    ``controls_service.py`` sets exactly these two values as terminal writes
    (pause/terminate); resume restores ``pre_pause_status`` or ``available``,
    neither of which is a stop state, so control returns to the heartbeat
    derivation on the very next org-chart read after a resume.

    Every other ``LLCAgentStatus`` member (``available``, ``assigned``,
    ``in_sprint``, ``on_leave``, ``onboarding``, ``offboarding``,
    ``inactive``) describes work assignment, not liveness — it has no
    dedicated slot in the org chart's 5-member display vocabulary
    (``active`` / ``idle`` / ``error`` / ``paused`` / ``terminated``,
    ``AgentDisplayStatus`` in ``llcStatus.ts``) and falls through to the
    heartbeat-derived value exactly as before this fix. Per #13485, this is a
    mapping onto the existing vocabulary — not a tenth status vocabulary.
    """
    if persisted_status in _STOP_STATUSES:
        return persisted_status
    return _heartbeat_status_to_org_status(run_status)


# ``adapter_type`` is agent vocabulary; for a person the honest value is the kind,
# not an adapter. The frontend suppresses the "Adapter" row for human nodes.
_HUMAN_ADAPTER_TYPE = "human"


async def _compose_human_nodes(session: AsyncSession, company_id: uuid.UUID) -> List[OrgChartNode]:
    """Return the company's people as org-chart nodes (#13936).

    The org chart is the native place to display the people of a company, not
    only its hired agents. Before this, the only ``OrgChartNode`` construction
    site hardcoded ``is_human=False`` and ``llc_company_memberships`` was never
    read here, so the human branch the frontend already renders
    (``OrgTreeNode.vue``) was structurally unreachable.

    Two queries at most, and none at all beyond the first when the company has
    no members. No schema change, no migration.
    """
    from sqlalchemy import func, select  # noqa: PLC0415

    from llc.models.work_item import LLCWorkItem  # noqa: PLC0415
    from user_management.models.user import User  # noqa: PLC0415

    # One outer join rather than membership-then-names: both models sit on the
    # same declarative Base, and selecting the four columns avoids loading full
    # ORM entities for two fields. LEFT join so a membership whose user row is
    # gone still yields a node instead of vanishing silently.
    member_rows = (
        await session.execute(
            select(
                LLCCompanyMembership.user_id,
                LLCCompanyMembership.role,
                User.display_name,
                User.username,
                User.is_active,
                User.deleted_at,
            )
            .outerjoin(User, User.id == LLCCompanyMembership.user_id)
            .where(LLCCompanyMembership.company_id == company_id)
            .order_by(LLCCompanyMembership.created_at, LLCCompanyMembership.user_id)
        )
    ).all()

    if not member_rows:
        return []

    # Assigned work-item counts per person — keyed by ``assignee_user_id``, the
    # human half of the assignment keyspace delivered under #10532. Mirrors the
    # agent query: one grouped statement, no N+1, terminal states excluded.
    count_rows = (
        await session.execute(
            select(LLCWorkItem.assignee_user_id, func.count(LLCWorkItem.id).label("cnt"))
            .where(
                LLCWorkItem.company_id == company_id,
                LLCWorkItem.assignee_user_id.isnot(None),
                LLCWorkItem.status.notin_([WorkItemStatus.DONE, WorkItemStatus.CANCELLED]),
            )
            .group_by(LLCWorkItem.assignee_user_id)
        )
    ).all()
    human_counts: Dict[uuid.UUID, int] = {row.assignee_user_id: row.cnt for row in count_rows}

    nodes: List[OrgChartNode] = []
    for user_id, role, display_name, username, is_active, deleted_at in member_rows:
        # ``role`` is mapped through sa.Enum, so the ORM hands back the enum
        # member — str() on it yields "MembershipRole.LEAD", not "lead". Take
        # .value when present so the wire format stays the lowercase label.
        role_label = str(getattr(role, "value", role))
        nodes.append(
            OrgChartNode(
                # ``id`` is namespaced so a person can never collide with an
                # agent slug; ``node_id`` keeps the raw user id, the keyspace
                # ``assignee_user_id`` references.
                id=f"user:{user_id}",
                node_id=str(user_id),
                # #13957: the canonical rule plus the third rung this site
                # needs -- the join below is a LEFT OUTER JOIN, so a membership
                # whose user row is gone yields NULL for both names and must
                # still render something the caller can key on.
                name=resolve_display_name(display_name, username, str(user_id)),
                title=role_label,
                # ``idle`` is exactly what ``_heartbeat_status_to_org_status``
                # returns for an agent with no run, so it asserts no liveness we
                # do not have. Budget stays 0/0 — people are not metered by
                # LLCAgentBudget.
                status="idle",
                adapter_type=_HUMAN_ADAPTER_TYPE,
                is_human=True,
                is_active=_person_is_active(is_active, deleted_at),
                last_heartbeat=None,
                budget_spent=0.0,
                budget_total=0.0,
                assigned_item_count=human_counts.get(user_id, 0),
                parent_id=None,
                children=[],
            )
        )
    return nodes


def _resolve_agent_budget(budget: "Optional[LLCAgentBudget]") -> "tuple[float, float]":
    """Resolve one agent's ``(budget_spent, budget_total)`` from its budget
    row, if any (#14184's split of ``_compose_agent_node`` — a second,
    self-contained extraction to bring the composer under the 51-line
    "must refactor before merge" threshold, CLAUDE_RULES.md rule 3).

    Byte-identical to the block this replaces: expose token numbers for
    token-mode agents when the field is populated, otherwise fall back to
    dollar amounts. No source expression changed in the move.
    """
    b_mode = budget.budget_mode if budget else "dollars"
    if b_mode == "tokens" and budget and budget.token_limit is not None:
        b_spent = float(budget.tokens_spent)
        b_total = float(budget.token_limit)
    else:
        b_spent = float(budget.budget_spent) if budget else 0.0
        b_total = float(budget.budget_limit) if budget else 0.0
    return b_spent, b_total


def _compose_agent_node(
    row: "AgentOrgNode",
    budget: "Optional[LLCAgentBudget]",
    run: "Optional[LLCHeartbeatRun]",
    assigned_item_count: int,
) -> OrgChartNode:
    """Compose one agent's ``OrgChartNode`` from its hierarchy row, its budget
    row (if any), and its latest heartbeat run (if any) (#14184).

    Extracted verbatim out of ``get_org_chart``'s per-row loop — a pure move,
    the precedent being the already-extracted human branch,
    ``_compose_human_nodes``. No field's source expression changed: every
    right-hand side below is byte-for-byte the same expression that used to
    sit inline in the loop (budget resolution now lives in
    ``_resolve_agent_budget``), and the existing org-chart test suite
    (``test_llc_org_chart.py``, ``test_org_chart_enrichment.py``) exercises
    every one of them unchanged as the behaviour-preservation evidence.
    """
    b_spent, b_total = _resolve_agent_budget(budget)
    return OrgChartNode(
        id=row.agent_id,
        node_id=str(row.id),  # AgentOrgNode UUID PK (assignment keyspace, #10032)
        name=row.name,
        title=row.title or row.org_role,
        # #14108: an explicit pause/terminate must win over a derived
        # heartbeat status — see `_resolve_org_status` for the precedence
        # rule and why every other lifecycle value falls through to it.
        status=_resolve_org_status(row.status, run.status if run else None),
        # #14109: the real ``adapter_type`` column, not ``org_role``. Falls
        # back to "" (not the role) when NULL: the hire flow
        # (agent_hires.py) always sets a concrete adapter — "claude_code"
        # by default — so a NULL here means a legacy/manually-seeded row
        # with genuinely no configured adapter, and reusing ``org_role``
        # is exactly the dishonest substitution this fix removes.
        adapter_type=row.adapter_type or "",
        is_human=False,
        # Liveness: latest run is picked by created_at; a just-queued run
        # may have no started_at, so fall back to created_at.
        last_heartbeat=(
            (run.started_at or run.created_at).isoformat() if run and (run.started_at or run.created_at) else None
        ),
        budget_spent=b_spent,
        budget_total=b_total,
        assigned_item_count=assigned_item_count,
        parent_id=row.reports_to,
        children=[],
    )


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

    # Compose flat nodes — per-row composition lives in `_compose_agent_node`
    # (#14184's extraction), mirroring the human branch's `_compose_human_nodes`.
    flat: Dict[str, OrgChartNode] = {
        row.agent_id: _compose_agent_node(
            row,
            budgets.get(row.agent_id),
            runs.get(row.agent_id),
            assigned_counts.get(row.agent_id, 0),
        )
        for row in org_rows
    }

    # People are part of the hierarchy, not siblings of it (#15763). They were
    # appended as roots because memberships carried no reporting edge, so a
    # company with twenty people rendered twenty roots beside the agent tree.
    for human in await _compose_human_nodes(session, company_id):
        flat[human.id] = human

    await apply_reporting_lines(session, company_id, flat)

    return OrgChartResponse(nodes=assemble_forest(flat))


# ------------------------------------------------------------------
# Executor rollup (#13942) — work items counted by assignee class and status
# ------------------------------------------------------------------

# The value ``unassigned`` in ``ExecutorRollupCell.executor_class`` — not an
# ``AssigneeType`` member (that enum only names the two *typed* assignees), but
# the third state ``assignee_type`` can legitimately hold: absent. Kept as a
# literal string constant, not a new enum member, per #13970: the axis already
# forked once under different member names, and adding a member here would be
# a third fork of the same concept rather than a value the column ever needs
# to store — no work item row is ever written with assignee_type="unassigned".
_UNASSIGNED_EXECUTOR_CLASS = "unassigned"

# A work item whose assignee id is present but no longer resolves to a live
# member/agent of *this* company (#14222) — the membership was deleted
# (`membership_service`) or the agent was terminated (`controls_service`),
# and neither reassigns the work it left behind. Kept distinct from
# ``unassigned`` rather than folded into it: "never assigned" and "the
# assignee is gone" are different facts about the row, and the second is the
# one that tells an operator a handover was missed (#14221's owner framing —
# "work items remain behind when someone leaves — they still need someone to
# work on them"). Same literal-constant convention as
# ``_UNASSIGNED_EXECUTOR_CLASS`` above: a third value on the existing
# executor axis, never a fourth ``AssigneeType``/``CoWorkerType`` fork
# (#13970).
_ORPHANED_EXECUTOR_CLASS = "orphaned"


class ExecutorRollupCell(BaseModel):
    """One (executor_class, status) count — one bar of the rollup panel.

    ``executor_class`` is one of ``AssigneeType.USER.value`` / ``.AGENT.value``
    / ``_UNASSIGNED_EXECUTOR_CLASS`` / ``_ORPHANED_EXECUTOR_CLASS`` — never a
    value invented for this endpoint (#13942's "no parallel executor enum"
    constraint). ``status`` is a ``WorkItemStatus`` value.
    """

    executor_class: str
    status: str
    count: int


class ExecutorRollupResponse(BaseModel):
    cells: List[ExecutorRollupCell]


def _executor_class_case(work_item_model):
    """SQL ``CASE`` classifying a work item's assignee (#13942, #14222).

    Four branches, evaluated in order:

    1. ``AssigneeType.USER`` — typed "user", a non-NULL ``assignee_user_id``,
       AND that user is a *current* member of *this* company
       (``llc_company_memberships``, scoped by ``company_id`` — a member of a
       *different* company must not count here; that row-level scope has had
       to be pinned independently three times already: #13936, #13969,
       #13942).
    2. ``AssigneeType.AGENT`` — typed "agent", a non-NULL ``assignee_agent_id``,
       AND that id resolves to an ``AgentOrgNode`` of *this* company whose
       ``status`` is not ``LLCAgentStatus.TERMINATED``. A paused/on-leave/
       inactive agent still counts as existing — those are recoverable
       states the agent can return from, so the work stays "owned, agent
       temporarily unavailable" rather than orphaned. Terminated is the one
       status that is final for this purpose (#14221's owner framing): the
       work still needs an owner, so it must not be reported as covered.
    3. ``orphaned`` — the discriminator and id column agree (so branch 1/2's
       *shape* matched — this is a real, non-dangling id) but the existence
       check failed: the id is present yet does not resolve inside this
       company. This is #14222's defect — the id existing was previously
       treated as sufficient to call the item owned.
    4. ``unassigned`` — nothing above matched: no assignee was ever set, or
       the discriminator/id pair is dangling in the pre-existing #13942
       sense (mis-typed discriminator, or a typed row with a NULL id
       column).

    ``work_item_model`` is passed in (not imported at module scope) to match
    this file's existing convention of importing ``LLCWorkItem`` locally
    inside each endpoint function (see ``get_org_chart``, ``_compose_human_nodes``).
    """
    from sqlalchemy import and_, case, or_, select  # noqa: PLC0415

    from models.agent_org import AgentOrgNode  # noqa: PLC0415

    user_assigned = and_(
        work_item_model.assignee_type == AssigneeType.USER.value,
        work_item_model.assignee_user_id.isnot(None),
    )
    agent_assigned = and_(
        work_item_model.assignee_type == AssigneeType.AGENT.value,
        work_item_model.assignee_agent_id.isnot(None),
    )

    user_exists = (
        select(LLCCompanyMembership.id)
        .where(
            LLCCompanyMembership.company_id == work_item_model.company_id,
            LLCCompanyMembership.user_id == work_item_model.assignee_user_id,
        )
        .exists()
    )
    agent_exists = (
        select(AgentOrgNode.id)
        .where(
            AgentOrgNode.id == work_item_model.assignee_agent_id,
            AgentOrgNode.company_id == work_item_model.company_id,
            # NULL-safe: `status != 'terminated'` evaluates to NULL — not TRUE —
            # for a NULL status, which would fail the EXISTS and mark EVERY
            # agent's work orphaned. The column is NOT NULL on a migrated
            # database, but #14189 records that we do not yet know whether it
            # pre-existed out-of-band, and 20260812_073 uses
            # ADD COLUMN IF NOT EXISTS — so a nullable variant is possible in
            # the field and invisible to tests (the SQLite harness builds the
            # NOT NULL column from the model).
            or_(
                AgentOrgNode.status.is_(None),
                AgentOrgNode.status != LLCAgentStatus.TERMINATED.value,
            ),
        )
        .exists()
    )

    return case(
        (and_(user_assigned, user_exists), AssigneeType.USER.value),
        (and_(agent_assigned, agent_exists), AssigneeType.AGENT.value),
        (or_(user_assigned, agent_assigned), _ORPHANED_EXECUTOR_CLASS),
        else_=_UNASSIGNED_EXECUTOR_CLASS,
    )


@router.get("/{company_id}/work-items/executor-rollup", response_model=ExecutorRollupResponse)
async def get_work_item_executor_rollup(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ExecutorRollupResponse:
    """Company-wide work-item counts by executor class and status (#13942, #14222).

    Executor class is derived from the *item's own assignee* — ``assignee_type``
    (typed via ``AssigneeType``, #13937) plus the matching id column, plus (#14222)
    whether that id still resolves to a live member/agent of this company —
    never a new discriminator. There is no ``PersonKind``-style provenance
    derivation here (unlike ``composables/llc/orgPeople.ts``): ``assignee_type``
    is already a backend-typed value, not something only knowable from the
    frontend, so counting it server-side introduces no honesty gap.

    Grouped in SQL rather than paginated to the frontend and counted there:
    ``GET /work-items`` caps at 500 rows per page, and a company can hold far
    more than that — a client-side count over one page would silently be
    a lie about companies past the cap. ``COUNT(*) ... GROUP BY`` has no such
    ceiling.
    """
    from sqlalchemy import func, select  # noqa: PLC0415

    from llc.models.work_item import LLCWorkItem  # noqa: PLC0415

    assert_company_access(ctx, company_id)  # #12184 canonical tenant guard

    executor_class = _executor_class_case(LLCWorkItem).label("executor_class")
    rows = (
        await session.execute(
            select(executor_class, LLCWorkItem.status, func.count(LLCWorkItem.id).label("item_count"))
            .where(LLCWorkItem.company_id == company_id)
            .group_by(executor_class, LLCWorkItem.status)
        )
    ).all()

    return ExecutorRollupResponse(
        cells=[
            ExecutorRollupCell(executor_class=row.executor_class, status=row.status, count=row.item_count)
            for row in rows
        ]
    )


# ------------------------------------------------------------------
# Company teams (#13938) — read-only projection of existing team data
# ------------------------------------------------------------------


class CompanyTeam(BaseModel):
    """One team of a company, with the user ids that belong to it.

    Read-only projection of ``teams`` / ``team_memberships`` — the team data
    plane that already exists (#6042). No new table, no migration, and no new
    vocabulary: a company inside AutoBot *is* an ``Organization`` (see
    ``CompanyService.delete``, which soft-deletes ``Organization.deleted_at``),
    so ``Team.org_id == company_id`` is the company's own team list.

    Only ``member_user_ids`` is returned because teams cover exactly one of the
    three person kinds the Org Chart shows: account holders. Hired agents
    (``agent_org_nodes``) and contacts (``llc_contacts``) carry no team column,
    so inventing a team for them would be fabricated grouping. The frontend
    renders them under an explicit "not in a team" bucket instead.
    """

    id: str
    name: str
    member_user_ids: List[str]


class CompanyTeamsResponse(BaseModel):
    teams: List[CompanyTeam]


# ------------------------------------------------------------------
# Process nodes (#13963) — where the absorbed automation module is entered
# ------------------------------------------------------------------


class ProcessNode(BaseModel):
    """One workflow a role runs, as an org-chart-adjacent node.

    Owner decision on #13963, option 3: automation is entered from inside
    Company OS **contextually**, through the org chart, rather than by a
    sidebar entry. A process node is the link between the two surfaces — the
    role that owns the work, and the workflow that performs it.

    Derived read-only from ``llc_role_workflows`` (#14221 step 5). No new
    table and no new vocabulary: the attachment binding a role to a workflow
    already exists, so a process node is a projection of it rather than a
    second place to record the same fact.

    ``role_id`` is included so the canvas can draw the node against the role it
    belongs to; ``workflow_id`` is what the automation route opens.
    """

    role_id: str
    role_name: str
    workflow_id: str


class ProcessNodesResponse(BaseModel):
    nodes: List[ProcessNode]


@router.get("/{company_id}/process-nodes", response_model=ProcessNodesResponse)
async def get_process_nodes(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ProcessNodesResponse:
    """Return the workflows this company's roles run (#13963).

    Company-scoped through the same shared :func:`assert_company_access` guard
    the rest of this router uses, and pinned again in the query itself — the
    role must belong to this company *and* the attachment must, so losing
    either predicate cannot widen the result.

    Read-only: this composes existing rows and creates nothing.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from llc.models.role_workflow import LLCRoleWorkflow  # noqa: PLC0415
    from user_management.models.role import Role  # noqa: PLC0415

    assert_company_access(ctx, company_id)

    result = await session.execute(
        select(Role.id, Role.name, LLCRoleWorkflow.workflow_id)
        .join(LLCRoleWorkflow, LLCRoleWorkflow.role_id == Role.id)
        .where(
            Role.org_id == company_id,
            LLCRoleWorkflow.company_id == company_id,
        )
        .order_by(Role.name, LLCRoleWorkflow.workflow_id)
    )
    return ProcessNodesResponse(
        nodes=[
            ProcessNode(role_id=str(role_id), role_name=name, workflow_id=workflow_id)
            for role_id, name, workflow_id in result.all()
        ]
    )


# ------------------------------------------------------------------
# Tool nodes (#14597) — which tools this company's roles depend on
# ------------------------------------------------------------------


class ToolNode(BaseModel):
    """One tool made available to one role, as an org-chart-adjacent node.

    Derived read-only from ``llc_role_tools`` (#14221 step 4) — the same
    projection shape ``ProcessNode`` above uses for ``llc_role_workflows``. A
    tool attached to several roles produces one row per role here; the canvas
    (``buildToolCanvasNodes``) folds the rows that share a ``tool_name`` into
    a single node, so "one tool used by several roles" stays one node rather
    than one per role.

    ``role_id``/``role_name`` are included so the canvas can draw which roles
    a tool belongs to; ``tool_name`` is the tool's registry identity.
    """

    role_id: str
    role_name: str
    tool_name: str


class ToolNodesResponse(BaseModel):
    nodes: List[ToolNode]


@router.get("/{company_id}/tool-nodes", response_model=ToolNodesResponse)
async def get_tool_nodes(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ToolNodesResponse:
    """Return the tools this company's roles carry (#14597).

    Company-scoped through the same shared :func:`assert_company_access` guard
    the rest of this router uses, and pinned again in the query itself — the
    role must belong to this company *and* the attachment must, so losing
    either predicate cannot widen the result. Mirrors ``get_process_nodes``
    above exactly, for the sibling attachment (tools rather than workflows).

    Read-only: this composes existing rows and creates nothing.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from llc.models.role_tool import LLCRoleTool  # noqa: PLC0415
    from user_management.models.role import Role  # noqa: PLC0415

    assert_company_access(ctx, company_id)

    result = await session.execute(
        select(Role.id, Role.name, LLCRoleTool.tool_name)
        .join(LLCRoleTool, LLCRoleTool.role_id == Role.id)
        .where(
            Role.org_id == company_id,
            LLCRoleTool.company_id == company_id,
        )
        .order_by(Role.name, LLCRoleTool.tool_name)
    )
    return ToolNodesResponse(
        nodes=[
            ToolNode(role_id=str(role_id), role_name=name, tool_name=tool_name)
            for role_id, name, tool_name in result.all()
        ]
    )


@router.get("/{company_id}/teams", response_model=CompanyTeamsResponse)
async def get_company_teams(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyTeamsResponse:
    """Return the company's teams and their member user ids (#13938).

    Company-scoped by path parameter through the same shared
    :func:`assert_company_access` guard the rest of the LLC router uses, rather
    than by the ambient org context that ``/teams`` relies on — a platform
    admin viewing another company's Org Chart must see that company's teams,
    not their own.

    Two queries, both bounded by the company: teams, then the memberships of
    those teams. Soft-deleted teams are excluded, matching every other team
    listing.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from user_management.models.team import Team, TeamMembership  # noqa: PLC0415

    assert_company_access(ctx, company_id)

    team_rows = (
        (
            await session.execute(
                select(Team).where(Team.org_id == company_id, Team.deleted_at.is_(None)).order_by(Team.name)
            )
        )
        .scalars()
        .all()
    )
    if not team_rows:
        return CompanyTeamsResponse(teams=[])

    team_ids = [team.id for team in team_rows]
    membership_rows = (
        await session.execute(
            select(TeamMembership.team_id, TeamMembership.user_id)
            .where(TeamMembership.team_id.in_(team_ids))
            .order_by(TeamMembership.joined_at)
        )
    ).all()

    members_by_team: Dict[uuid.UUID, List[str]] = {team_id: [] for team_id in team_ids}
    for team_id, user_id in membership_rows:
        members_by_team[team_id].append(str(user_id))

    return CompanyTeamsResponse(
        teams=[
            CompanyTeam(id=str(team.id), name=team.name, member_user_ids=members_by_team[team.id]) for team in team_rows
        ]
    )


# Capability-search result bounds. These literals predate #13936; they were named
# when the hardcoded-values gate flagged them on this PR. (#13950 has since made
# that gate line-scoped, so the original file-scoped rationale no longer applies —
# the constants are kept because naming them is right, not because a gate forces it.)
_AGENT_SEARCH_DEFAULT_LIMIT = 10
_AGENT_SEARCH_MAX_LIMIT = 100


@router.get("/{company_id}/agents/search")
async def search_agents(
    company_id: uuid.UUID,
    q: str = Query(..., min_length=1, description="Search query for agent capabilities"),
    limit: int = Query(
        _AGENT_SEARCH_DEFAULT_LIMIT,
        ge=1,
        le=_AGENT_SEARCH_MAX_LIMIT,
        description="Max results",
    ),
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
