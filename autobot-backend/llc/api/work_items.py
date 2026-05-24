"""LLC work items API routes (GH#8213, GH#8223, GH#8232).

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
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session_factory

from ..models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from ..services.handoff import HandoffAttachment, HandoffNotAuthorized, HandoffService
from ..services.work_item_service import CheckoutConflict, InvalidTransition, WorkItemService


class HumanClaimRequest(BaseModel):
    user_id: str
    company_id: str


class HumanUnclaimRequest(BaseModel):
    user_id: str
    company_id: str

router = APIRouter(prefix="/work-items", tags=["llc-work-items"])
_get_service = lazy_singleton(WorkItemService)
_get_handoff_service = lazy_singleton(HandoffService)


def _service() -> WorkItemService:
    return _get_service()


def _handoff_service() -> HandoffService:
    return _get_handoff_service()


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


def _assignee_display(item: Any) -> Optional[Dict[str, Any]]:
    """Return structured assignee display info (GH#8223).

    display_name and name are None until user_management JOIN is implemented
    (see discovery issue filed in GH#8223 implementation).
    """
    if item.assignee_type == "user" and item.assignee_user_id:
        return {
            "type": "user",
            "id": str(item.assignee_user_id),
            "display_name": None,
            "name": None,
        }
    if item.assignee_type == "agent" and item.assignee_agent_id:
        return {
            "type": "agent",
            "id": str(item.assignee_agent_id),
            "display_name": None,
            "name": None,
        }
    return None


def _item_to_dict(item: Any) -> Dict[str, Any]:
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
        "assignee_agent_id": str(item.assignee_agent_id) if item.assignee_agent_id else None,
        "assignee_user_id": str(item.assignee_user_id) if item.assignee_user_id else None,
        "assignee_type": item.assignee_type,
        "assignee_display": _assignee_display(item),
        "checkout_run_id": item.checkout_run_id,
        "checkout_locked_at": item.checkout_locked_at.isoformat() if item.checkout_locked_at else None,
        "version": item.version,
        "created_by_agent_id": str(item.created_by_agent_id) if item.created_by_agent_id else None,
        "created_by_user_id": str(item.created_by_user_id) if item.created_by_user_id else None,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "cancelled_at": item.cancelled_at.isoformat() if item.cancelled_at else None,
        "review_brief": getattr(item, "review_brief", None),
        "has_human_handoff_context": bool(getattr(item, "review_brief", None)),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
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
    return _item_to_dict(item)


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
        limit=limit,
        offset=offset,
    )
    return [_item_to_dict(i) for i in items]


@router.get("/{work_item_id}")
async def get_work_item(
    work_item_id: str,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    item = await _service().get(session, work_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Work item not found")
    return _item_to_dict(item)


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
    return _item_to_dict(item)


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
        return _item_to_dict(item)
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
        item = await _service().release(session, work_item_id=work_item_id, agent_id=body.agent_id)
        await session.commit()
        redis = await get_async_redis_client()
        if redis is not None:
            await redis.delete(f"llc:checkout:{work_item_id}")
        return _item_to_dict(item)
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
        return _item_to_dict(item)
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
        return _item_to_dict(item)
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
        return _item_to_dict(item)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
        "author_agent_id": str(comment.author_agent_id) if comment.author_agent_id else None,
        "author_user_id": str(comment.author_user_id) if comment.author_user_id else None,
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
