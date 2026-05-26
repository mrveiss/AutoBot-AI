"""LLC work items API routes (GH#8213, GH#8223, GH#8231, GH#8232, GH#8252, GH#8253).
Routes:
  POST   /api/llc/work-items
  GET    /api/llc/work-items
  GET    /api/llc/work-items/{work_item_id}
  PATCH  /api/llc/work-items/{work_item_id}
  DELETE /api/llc/work-items/{work_item_id}
  POST   /api/llc/work-items/{work_item_id}/checkout
  POST   /api/llc/work-items/{work_item_id}/release
  POST   /api/llc/work-items/{work_item_id}/transition
  POST   /api/llc/work-items/{work_item_id}/comments
  POST   /api/llc/work-items/{work_item_id}/claim    (human claim — GH#8223)
  POST   /api/llc/work-items/{work_item_id}/unclaim  (human unclaim — GH#8223)
  POST   /api/llc/work-items/{work_item_id}/handoff/to-agent  (GH#8232)
  POST   /api/llc/work-items/{work_item_id}/handoff/to-human   (GH#8231)
  POST   /api/llc/work-items/{work_item_id}/review/approve     (GH#8231)
  POST   /api/llc/work-items/{work_item_id}/review/request-changes (GH#8231)
  GET    /api/llc/work-items/{work_item_id}/handoff-brief       (GH#8231)
  POST   /api/llc/work-items/{work_item_id}/coworker   (set/clear co-worker — GH#8230)
  POST   /api/llc/work-items/{work_item_id}/attachments         (GH#8253)
  GET    /api/llc/work-items/{work_item_id}/attachments         (GH#8253)
  GET    /api/llc/work-items/{work_item_id}/attachments/{attachment_id}/download (GH#8253)
  GET    /api/llc/work-items/{work_item_id}/attachments/{attachment_id}/text     (GH#8253)
  DELETE /api/llc/work-items/{work_item_id}/attachments/{attachment_id}          (GH#8253)
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.singleton_factory import lazy_singleton
from models.agent_org import AgentOrgNode
from user_management.database import get_async_session_factory
from user_management.models.user import User

from ..kb.collections import KbCollectionManager
from ..models.enums import (
    WorkItemPriority,
    WorkItemRelationType,
    WorkItemStatus,
    WorkItemType,
)
from ..services.attachment_service import (
    AttachmentNotFound,
    AttachmentService,
    AttachmentTooLarge,
)
from ..services.handoff import (
    HandoffAttachment,
    HandoffNotAllowed,
    HandoffNotAuthorized,
    HandoffService,
)
from ..services.work_item_relations import RelationConflict, WorkItemRelationService
from ..services.work_item_service import (
    CheckoutConflict,
    CoWorkingPermissionError,
    InvalidTransition,
    WorkItemService,
    resolve_actor_role,
)
from ..services.work_product_service import WorkProductService


class HumanClaimRequest(BaseModel):
    user_id: str
    company_id: str


class HumanUnclaimRequest(BaseModel):
    user_id: str
    company_id: str


class CoworkerRequest(BaseModel):
    """Set or clear a co-worker on a work item (GH#8230).
    To clear the co-worker, omit co_worker_type (or send null).
    The caller's role is resolved server-side from the auth context — not supplied
    by the client (GH#8516: removed client-supplied caller_role to prevent privilege escalation).
    """

    company_id: str
    co_worker_type: Optional[str] = None
    co_worker_agent_id: Optional[str] = None
    co_worker_user_id: Optional[str] = None
    actor_agent_id: Optional[str] = None
    actor_user_id: Optional[str] = None


router = APIRouter(prefix="/work-items", tags=["llc-work-items"])
_get_service = lazy_singleton(WorkItemService)
_get_product_service = lazy_singleton(WorkProductService)
_get_handoff_service = lazy_singleton(HandoffService)
_kb_manager = KbCollectionManager()
_get_relation_service = lazy_singleton(WorkItemRelationService)
_get_attachment_service = lazy_singleton(AttachmentService)


def _service() -> WorkItemService:
    return _get_service()


def _handoff_service() -> HandoffService:
    return _get_handoff_service()


def _relation_service() -> WorkItemRelationService:
    return _get_relation_service()


def _attachment_service() -> AttachmentService:
    return _get_attachment_service()


async def get_session() -> AsyncSession:
    factory = get_async_session_factory()
    async with factory() as session:
        yield session


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class WorkItemCreate(BaseModel):
    company_id: str
    type: WorkItemType
    title: str
    description: Optional[str] = None
    acceptance_criteria: Optional[List[str]] = None
    priority: WorkItemPriority = WorkItemPriority.MEDIUM
    story_points: Optional[int] = None
    parent_id: Optional[str] = None
    project_id: Optional[str] = None
    sprint_id: Optional[str] = None
    goal_id: Optional[str] = None
    assignee_agent_id: Optional[str] = None
    assignee_user_id: Optional[str] = None
    created_by_agent_id: Optional[str] = None
    created_by_user_id: Optional[str] = None
    labels: Optional[List[str]] = None


class WorkItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    acceptance_criteria: Optional[List[str]] = None
    priority: Optional[WorkItemPriority] = None
    story_points: Optional[int] = None
    labels: Optional[List[str]] = None
    parent_id: Optional[str] = None
    sprint_id: Optional[str] = None
    goal_id: Optional[str] = None
    assignee_agent_id: Optional[str] = None
    assignee_user_id: Optional[str] = None


class CheckoutRequest(BaseModel):
    agent_id: str
    run_id: Optional[str] = None


class ReleaseRequest(BaseModel):
    agent_id: str


class TransitionRequest(BaseModel):
    status: WorkItemStatus


class CommentCreate(BaseModel):
    company_id: str
    body: str
    author_agent_id: Optional[str] = None
    author_user_id: Optional[str] = None


class HandoffAttachmentRequest(BaseModel):
    attachment_id: str
    filename: str
    content: str
    mime_type: Optional[str] = None


class HandoffToAgentRequest(BaseModel):
    user_id: str
    company_id: str
    target_agent_id: str
    human_notes: str
    user_display: str = ""
    attachments: Optional[List[HandoffAttachmentRequest]] = None


class HandoffToHumanRequest(BaseModel):
    agent_id: str
    reviewer_user_id: str
    company_id: str
    agent_notes: Optional[str] = None


class ReviewApproveRequest(BaseModel):
    reviewer_user_id: str
    company_id: str


class ReviewChangesRequest(BaseModel):
    reviewer_user_id: str
    company_id: str
    change_request: str
    return_to_agent_id: Optional[str] = None


class RelationCreate(BaseModel):
    company_id: str
    target_id: str
    relation_type: WorkItemRelationType
    created_by_agent_id: Optional[str] = None
    created_by_user_id: Optional[str] = None


class RelationDelete(BaseModel):
    actor_agent_id: Optional[str] = None
    actor_user_id: Optional[str] = None


async def _assignee_display(
    item: Any, session: AsyncSession
) -> Optional[Dict[str, Any]]:
    """Return structured assignee display info resolved from user_management.users (GH#8476)."""
    if item.assignee_type == "user" and item.assignee_user_id:
        row = (
            await session.execute(
                select(User.display_name, User.username).where(
                    User.id == item.assignee_user_id
                )
            )
        ).one_or_none()
        name = (row.display_name or row.username) if row else None
        return {
            "type": "user",
            "id": str(item.assignee_user_id),
            "display_name": name,
            "name": name,
        }
    if item.assignee_type == "agent" and item.assignee_agent_id:
        row = (
            await session.execute(
                select(AgentOrgNode.name).where(
                    AgentOrgNode.id == item.assignee_agent_id
                )
            )
        ).one_or_none()
        name = row.name if row else None
        return {
            "type": "agent",
            "id": str(item.assignee_agent_id),
            "display_name": name,
            "name": name,
        }
    return None


def _coworker_display(item: Any) -> Optional[Dict[str, Any]]:
    """Return structured co-worker display info (GH#8230)."""
    if not item.co_working_enabled:
        return None
    if item.co_worker_type == "human" and item.co_worker_user_id:
        return {
            "type": "human",
            "id": str(item.co_worker_user_id),
            "display_name": None,
            "name": None,
        }
    if item.co_worker_type == "agent" and item.co_worker_agent_id:
        return {
            "type": "agent",
            "id": str(item.co_worker_agent_id),
            "display_name": None,
            "name": None,
        }
    return None


def _relations_to_list(item: Any) -> List[Dict[str, Any]]:
    """Serialize outgoing + incoming relations for GET response (GH#8252)."""
    rows = []
    for rel in getattr(item, "outgoing_relations", []) or []:
        tgt = rel.target
        rows.append(
            {
                "id": str(rel.id),
                "type": rel.relation_type,
                "target_id": str(rel.target_id),
                "target_identifier": tgt.identifier if tgt else None,
                "target_title": tgt.title if tgt else None,
                "target_status": tgt.status if tgt else None,
            }
        )
    return rows


async def _item_to_dict(item: Any, session: AsyncSession) -> Dict[str, Any]:
    return {
        "id": str(item.id),
        "company_id": str(item.company_id),
        "identifier": item.identifier,
        "type": item.type,
        "title": item.title,
        "description": item.description,
        "acceptance_criteria": item.acceptance_criteria,
        "status": item.status,
        "priority": item.priority,
        "story_points": item.story_points,
        "labels": item.labels,
        "parent_id": str(item.parent_id) if item.parent_id else None,
        "project_id": str(item.project_id) if item.project_id else None,
        "sprint_id": str(item.sprint_id) if item.sprint_id else None,
        "goal_id": str(item.goal_id) if item.goal_id else None,
        "assignee_agent_id": (
            str(item.assignee_agent_id) if item.assignee_agent_id else None
        ),
        "assignee_user_id": (
            str(item.assignee_user_id) if item.assignee_user_id else None
        ),
        "assignee_type": item.assignee_type,
        "assignee_display": await _assignee_display(item, session),
        "checkout_run_id": item.checkout_run_id,
        "checkout_locked_at": (
            item.checkout_locked_at.isoformat() if item.checkout_locked_at else None
        ),
        "version": item.version,
        "created_by_agent_id": (
            str(item.created_by_agent_id) if item.created_by_agent_id else None
        ),
        "created_by_user_id": (
            str(item.created_by_user_id) if item.created_by_user_id else None
        ),
        "reviewer_user_id": (
            str(item.reviewer_user_id) if item.reviewer_user_id else None
        ),
        "reviewer_agent_id": (
            str(item.reviewer_agent_id) if item.reviewer_agent_id else None
        ),
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "cancelled_at": item.cancelled_at.isoformat() if item.cancelled_at else None,
        "review_brief": getattr(item, "review_brief", None),
        "has_human_handoff_context": bool(getattr(item, "review_brief", None)),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "relations": _relations_to_list(item),
    }


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@router.post("", status_code=201)
async def create_work_item(
    body: WorkItemCreate,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    item = await _service().create(
        session,
        company_id=body.company_id,
        type=body.type,
        title=body.title,
        description=body.description,
        acceptance_criteria=body.acceptance_criteria,
        priority=body.priority,
        story_points=body.story_points,
        parent_id=body.parent_id,
        project_id=body.project_id,
        sprint_id=body.sprint_id,
        goal_id=body.goal_id,
        assignee_agent_id=body.assignee_agent_id,
        assignee_user_id=body.assignee_user_id,
        created_by_agent_id=body.created_by_agent_id,
        created_by_user_id=body.created_by_user_id,
        labels=body.labels,
    )
    await session.commit()
    await _kb_manager.ensure_collection(KbCollectionManager.WORK_ITEM_PREFIX, item.id)
    return await _item_to_dict(item, session)


@router.get("")
async def list_work_items(
    company_id: str = Query(...),
    project_id: Optional[str] = Query(None),
    type: Optional[WorkItemType] = Query(None),
    status: Optional[WorkItemStatus] = Query(None),
    assignee: Optional[str] = Query(None),
    sprint_id: Optional[str] = Query(None),
    parent_id: Optional[str] = Query(None),
    top_level_only: bool = Query(False),
    co_worker_agent_id: Optional[str] = Query(None),
    co_worker_user_id: Optional[str] = Query(None),
    label_ids: Optional[List[str]] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> List[Dict[str, Any]]:
    items = await _service().list_by_project(
        session,
        company_id=company_id,
        project_id=project_id,
        type=type,
        status=status,
        assignee_agent_id=assignee,
        sprint_id=sprint_id,
        parent_id=parent_id,
        top_level_only=top_level_only,
        co_worker_agent_id=co_worker_agent_id,
        co_worker_user_id=co_worker_user_id,
        label_ids=label_ids,
        limit=limit,
        offset=offset,
    )
    return [await _item_to_dict(i, session) for i in items]


@router.get("/{work_item_id}")
async def get_work_item(
    work_item_id: str,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    item = await _service().get(session, work_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found")
    return await _item_to_dict(item, session)


@router.patch("/{work_item_id}")
async def update_work_item(
    work_item_id: str,
    body: WorkItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    fields = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    item = await _service().update(session, work_item_id, **fields)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found")
    await session.commit()
    return await _item_to_dict(item, session)


@router.delete("/{work_item_id}", status_code=204)
async def delete_work_item(
    work_item_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    item = await _service().get(session, work_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found")
    await session.delete(item)
    await session.commit()


@router.post("/{work_item_id}/checkout")
async def checkout_work_item(
    work_item_id: str,
    body: CheckoutRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        item = await _service().checkout(
            session,
            work_item_id=work_item_id,
            agent_id=body.agent_id,
            run_id=body.run_id,
        )
        await session.commit()
        return await _item_to_dict(item, session)
    except CheckoutConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{work_item_id}/release")
async def release_work_item(
    work_item_id: str,
    body: ReleaseRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        item = await _service().release(
            session, work_item_id=work_item_id, agent_id=body.agent_id
        )
        await session.commit()
        redis = await get_async_redis_client()
        if redis is not None:
            await redis.delete(f"llc:checkout:{work_item_id}")
        return await _item_to_dict(item, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{work_item_id}/transition")
async def transition_work_item(
    work_item_id: str,
    body: TransitionRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        item = await _service().transition_status(session, work_item_id, body.status)
        await session.commit()
        if item.status == WorkItemStatus.DONE:
            await _kb_manager.archive_collection(
                KbCollectionManager.WORK_ITEM_PREFIX, item.id
            )
        return await _item_to_dict(item, session)
    except InvalidTransition as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{work_item_id}/claim")
async def claim_work_item(
    work_item_id: str,
    body: HumanClaimRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        item = await _service().claim_human(
            session,
            work_item_id=work_item_id,
            user_id=body.user_id,
            company_id=body.company_id,
        )
        await session.commit()
        return await _item_to_dict(item, session)
    except CheckoutConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{work_item_id}/unclaim")
async def unclaim_work_item(
    work_item_id: str,
    body: HumanUnclaimRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        item = await _service().unclaim_human(
            session,
            work_item_id=work_item_id,
            user_id=body.user_id,
            company_id=body.company_id,
        )
        await session.commit()
        return await _item_to_dict(item, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class CoWorkerSetRequest(BaseModel):
    """Set co-worker on a work item (GH#8230).

    caller_role is resolved server-side from auth context — not supplied
    by the client (GH#8583: removed client-supplied caller_role to prevent privilege escalation).
    """

    co_worker_type: str
    company_id: str
    co_worker_agent_id: Optional[str] = None
    co_worker_user_id: Optional[str] = None
    actor_id: Optional[str] = None


class CoWorkerClearRequest(BaseModel):
    company_id: str
    actor_id: Optional[str] = None


@router.post("/{work_item_id}/coworker", status_code=200)
async def set_coworker(
    work_item_id: str,
    body: CoWorkerSetRequest,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Set co-worker fields for a work item (GH#8230, GH#8517, GH#8583).

    Returns 404 when the work item is not found, 403 when the caller lacks
    permission, and 422 for invalid co-worker identity values.
    """
    actor_id = (
        current_user.get("user_id")
        or current_user.get("agent_id")
        or current_user.get("id")
    )
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        caller_role = await resolve_actor_role(session, actor_id, body.company_id)
        item = await _service().enable_coworking(
            session,
            work_item_id=work_item_id,
            co_worker_type=body.co_worker_type,
            company_id=body.company_id,
            co_worker_agent_id=body.co_worker_agent_id,
            co_worker_user_id=body.co_worker_user_id,
            actor_id=actor_id,
            caller_role=caller_role,
        )
        await session.commit()
        return await _item_to_dict(item, session)
    except CoWorkingPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        msg = str(exc)
        # "not found" errors → 404; identity/type validation errors → 422
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)


@router.post("/{work_item_id}/comments", status_code=201)
async def add_comment(
    work_item_id: str,
    body: CommentCreate,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    comment = await _service().add_comment(
        session,
        work_item_id=work_item_id,
        company_id=body.company_id,
        body=body.body,
        author_agent_id=body.author_agent_id,
        author_user_id=body.author_user_id,
    )
    await session.commit()
    return {
        "id": str(comment.id),
        "work_item_id": str(comment.work_item_id),
        "company_id": str(comment.company_id),
        "body": comment.body,
        "author_agent_id": (
            str(comment.author_agent_id) if comment.author_agent_id else None
        ),
        "author_user_id": (
            str(comment.author_user_id) if comment.author_user_id else None
        ),
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


@router.post("/{work_item_id}/handoff/to-agent", status_code=200)
async def handoff_to_agent(
    work_item_id: str,
    body: HandoffToAgentRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Human→Agent handoff: ingest notes into KB, reassign to agent (GH#8232)."""
    atts = [
        HandoffAttachment(
            attachment_id=a.attachment_id,
            filename=a.filename,
            content=a.content,
            mime_type=a.mime_type,
        )
        for a in (body.attachments or [])
    ]
    try:
        result = await _handoff_service().human_to_agent(
            session,
            work_item_id=work_item_id,
            target_agent_id=body.target_agent_id,
            user_id=body.user_id,
            company_id=body.company_id,
            human_notes=body.human_notes,
            user_display=body.user_display,
            attachments=atts,
        )
        await session.commit()
        return {
            "work_item_id": result.work_item_id,
            "target_agent_id": result.target_agent_id,
            "kb_doc_ids": result.kb_doc_ids,
            "review_brief": result.review_brief,
        }
    except HandoffNotAuthorized as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ------------------------------------------------------------------
# Handoff routes (GH#8231)
# ------------------------------------------------------------------


@router.post("/{work_item_id}/handoff/to-human")
async def handoff_to_human(
    work_item_id: str,
    body: HandoffToHumanRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        item = await _handoff_service().agent_to_human(
            session,
            work_item_id=work_item_id,
            agent_id=body.agent_id,
            reviewer_user_id=body.reviewer_user_id,
            company_id=body.company_id,
            agent_notes=body.agent_notes,
        )
        await session.commit()
        return await _item_to_dict(item, session)
    except HandoffNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{work_item_id}/review/approve")
async def review_approve(
    work_item_id: str,
    body: ReviewApproveRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        item = await _handoff_service().approve(
            session,
            work_item_id=work_item_id,
            reviewer_user_id=body.reviewer_user_id,
            company_id=body.company_id,
        )
        await session.commit()
        return await _item_to_dict(item, session)
    except HandoffNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{work_item_id}/review/request-changes")
async def review_request_changes(
    work_item_id: str,
    body: ReviewChangesRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        item = await _handoff_service().request_changes(
            session,
            work_item_id=work_item_id,
            reviewer_user_id=body.reviewer_user_id,
            company_id=body.company_id,
            change_request=body.change_request,
            return_to_agent_id=body.return_to_agent_id,
        )
        await session.commit()
        return await _item_to_dict(item, session)
    except HandoffNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{work_item_id}/handoff-brief")
async def get_handoff_brief(
    work_item_id: str,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        brief = await _handoff_service().get_brief(session, work_item_id)
        return {"work_item_id": work_item_id, "brief": brief}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{work_item_id}/coworker", status_code=200)
async def set_or_clear_coworker(
    work_item_id: str,
    body: CoworkerRequest,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Set or clear co-worker on a work item (GH#8230, GH#8516).

    Omit or null co_worker_type to clear the co-worker.
    caller_role is resolved server-side; it is no longer accepted from the
    client (GH#8516: removed to prevent privilege escalation).
    """
    actor_id = body.actor_agent_id or body.actor_user_id
    actor_type = "agent" if body.actor_agent_id else "user"
    try:
        if body.co_worker_type:
            item = await _service().enable_coworking(
                session,
                work_item_id=work_item_id,
                co_worker_type=body.co_worker_type,
                company_id=body.company_id,
                co_worker_agent_id=body.co_worker_agent_id,
                co_worker_user_id=body.co_worker_user_id,
                actor_id=actor_id,
                actor_type=actor_type,
                caller_role="owner",
            )
        else:
            item = await _service().disable_coworking(
                session,
                work_item_id=work_item_id,
                company_id=body.company_id,
                actor_id=actor_id,
                actor_type=actor_type,
                caller_role="owner",
            )
        await session.commit()
        return _item_to_dict(item)
    except CoWorkingPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)


@router.get("/{work_item_id}/products")
async def list_work_products(
    work_item_id: str,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List all work products for a work item (GH#8242)."""
    products = await _get_product_service().list_by_work_item(
        session,
        work_item_id=work_item_id,
        limit=limit,
        offset=offset,
    )
    return {
        "work_item_id": work_item_id,
        "products": [
            {
                "id": str(p.id),
                "type": p.type if isinstance(p.type, str) else p.type.value,
                "title": p.title,
                "content_text": p.content_text,
                "storage_path": p.storage_path,
                "url": p.url,
                "kb_indexed": p.kb_indexed,
                "heartbeat_run_id": (
                    str(p.heartbeat_run_id) if p.heartbeat_run_id else None
                ),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in products
        ],
        "total": len(products),
    }


# ------------------------------------------------------------------
# Relation endpoints (GH#8252)
# ------------------------------------------------------------------


@router.post("/{work_item_id}/relations", status_code=201)
async def add_relation(
    work_item_id: str,
    body: RelationCreate,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        rel = await _relation_service().add(
            company_id=body.company_id,
            source_id=work_item_id,
            target_id=body.target_id,
            relation_type=body.relation_type,
            created_by_agent_id=body.created_by_agent_id,
            created_by_user_id=body.created_by_user_id,
        )
        await session.commit()
        return {
            "id": str(rel.id),
            "source_id": work_item_id,
            "target_id": body.target_id,
            "relation_type": rel.relation_type,
        }
    except RelationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{work_item_id}/relations/{relation_id}", status_code=204)
async def remove_relation(
    work_item_id: str,
    relation_id: str,
    company_id: str = Query(...),
    actor_agent_id: Optional[str] = Query(None),
    actor_user_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await _relation_service().remove(
            company_id=company_id,
            relation_id=relation_id,
            actor_agent_id=actor_agent_id,
            actor_user_id=actor_user_id,
        )
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Attachment routes (GH#8253)
# ---------------------------------------------------------------------------


def _attachment_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "work_item_id": str(row.work_item_id),
        "company_id": str(row.company_id),
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "text_extracted": row.text_extracted,
        "uploaded_by_agent_id": (
            str(row.uploaded_by_agent_id) if row.uploaded_by_agent_id else None
        ),
        "uploaded_by_user_id": (
            str(row.uploaded_by_user_id) if row.uploaded_by_user_id else None
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("/{work_item_id}/attachments", status_code=201)
async def upload_attachment(
    work_item_id: str,
    company_id: str = Query(...),
    file: UploadFile = File(...),
    uploaded_by_agent_id: Optional[str] = Query(None),
    uploaded_by_user_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    try:
        content = await file.read()
        row = await _attachment_service().upload(
            session,
            work_item_id=work_item_id,
            company_id=company_id,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            content=content,
            uploaded_by_agent_id=uploaded_by_agent_id,
            uploaded_by_user_id=uploaded_by_user_id,
        )
    except AttachmentTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    return _attachment_to_dict(row)


@router.get("/{work_item_id}/attachments")
async def list_attachments(
    work_item_id: str,
    company_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    rows = await _attachment_service().list_attachments(
        session, work_item_id=work_item_id, company_id=company_id
    )
    return {"attachments": [_attachment_to_dict(r) for r in rows]}


@router.get("/{work_item_id}/attachments/{attachment_id}/download")
async def download_attachment(
    work_item_id: str,
    attachment_id: str,
    company_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        row, content = await _attachment_service().download(
            session,
            attachment_id=attachment_id,
            work_item_id=work_item_id,
            company_id=company_id,
        )
    except AttachmentNotFound:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return Response(
        content=content,
        media_type=row.content_type,
        headers={"Content-Disposition": f'attachment; filename="{row.filename}"'},
    )


@router.get("/{work_item_id}/attachments/{attachment_id}/text")
async def get_attachment_text(
    work_item_id: str,
    attachment_id: str,
    company_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    text = await _attachment_service().get_text(
        session,
        attachment_id=attachment_id,
        work_item_id=work_item_id,
        company_id=company_id,
    )
    return {
        "attachment_id": attachment_id,
        "text": text,
        "text_extracted": text is not None,
    }


@router.delete("/{work_item_id}/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    work_item_id: str,
    attachment_id: str,
    company_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await _attachment_service().delete(
            session,
            attachment_id=attachment_id,
            work_item_id=work_item_id,
            company_id=company_id,
        )
    except AttachmentNotFound:
        raise HTTPException(status_code=404, detail="Attachment not found")
