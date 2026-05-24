# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC agent-facing API routes (GH#8218, GH#8232).

All routes require a valid LLC bearer token (injected by LLCAgentAuthMiddleware).
Phase 1 stubs — real implementations land in subsequent phases.

Routes (all under /llc/agent):
  GET  /work-items/next             — next assigned item (atomic checkout)
  POST /work-items/{id}/status      — status update
  POST /cost-events                 — cost ingestion
  POST /comments                    — comment on work item
  POST /products                    — upload work product artifact
  POST /heartbeat/report            — heartbeat run completion
  GET  /context/{item_id}           — pre-assembled context + KB handoff notes (GH#8232)
"""

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/agent", tags=["llc-agent"])


def _agent_context(request: Request) -> tuple[str, str]:
    """Extract agent_id and company_id from middleware-injected state."""
    agent_id = getattr(request.state, "agent_id", None)
    company_id = getattr(request.state, "company_id", None)
    if not agent_id or not company_id:
        raise HTTPException(status_code=401, detail="Agent context not injected")
    return agent_id, company_id


@router.get("/work-items/next")
async def get_next_work_item(request: Request) -> Dict[str, Any]:
    agent_id, company_id = _agent_context(request)
    # Phase 5: delegate to WorkItemService.checkout_next(agent_id, company_id)
    return {"work_item": None, "message": "No items available (Phase 1 stub)"}


class StatusUpdate(BaseModel):
    status: str
    comment: Optional[str] = None


@router.post("/work-items/{item_id}/status")
async def update_work_item_status(item_id: uuid.UUID, body: StatusUpdate, request: Request) -> Dict[str, Any]:
    agent_id, company_id = _agent_context(request)
    # Phase 2+: delegate to WorkItemService.transition()
    return {"updated": True, "item_id": str(item_id), "status": body.status}


class CostEvent(BaseModel):
    model: str
    tokens_in: int
    tokens_out: int
    work_item_id: Optional[str] = None


@router.post("/cost-events")
async def ingest_cost_event(body: CostEvent, request: Request) -> Dict[str, Any]:
    agent_id, company_id = _agent_context(request)
    # Phase 1+: delegate to BudgetService.ingest_cost_event()
    return {"recorded": True}


class CommentBody(BaseModel):
    work_item_id: str
    body: str


@router.post("/comments")
async def post_comment(body: CommentBody, request: Request) -> Dict[str, Any]:
    agent_id, company_id = _agent_context(request)
    # Phase 2+: full comment storage
    return {"comment_id": None, "recorded": True}


class WorkProduct(BaseModel):
    work_item_id: str
    artifact_type: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


@router.post("/products")
async def upload_work_product(body: WorkProduct, request: Request) -> Dict[str, Any]:
    agent_id, company_id = _agent_context(request)
    # Phase 5: KB storage + RAG indexing
    return {"artifact_id": None, "recorded": True}


class HeartbeatReport(BaseModel):
    run_id: str
    work_item_id: Optional[str] = None
    status: str
    duration_seconds: Optional[float] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    model: Optional[str] = None


@router.post("/heartbeat/report")
async def report_heartbeat(body: HeartbeatReport, request: Request) -> Dict[str, Any]:
    agent_id, company_id = _agent_context(request)
    # Phase 3+: full heartbeat recording
    return {"recorded": True, "run_id": body.run_id}


@router.get("/context/{item_id}")
async def get_item_context(item_id: uuid.UUID, request: Request) -> Dict[str, Any]:
    """Return agent context for a work item, including any human handoff KB notes (GH#8232)."""
    agent_id, company_id = _agent_context(request)
    from ..kb.work_item_kb import WorkItemKB

    kb = WorkItemKB()
    handoff_chunks = await kb.get_context(str(item_id))
    return {
        "item_id": str(item_id),
        "handoff_notes": handoff_chunks,
        "has_human_handoff_context": bool(handoff_chunks),
        "context": {},
        "message": "Handoff KB notes included; full RAG context available in Phase 5",
    }


__all__ = ["router"]
