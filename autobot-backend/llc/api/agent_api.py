# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC agent-facing API routes (GH#8218, GH#8232, GH#8253).

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
  POST /attachments                 — agent file upload (GH#8253)
"""

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
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
    type: str
    title: str
    content_text: Optional[str] = None
    storage_path: Optional[str] = None
    url: Optional[str] = None
    heartbeat_run_id: Optional[str] = None


@router.post("/products")
async def upload_work_product(body: WorkProduct, request: Request) -> Dict[str, Any]:
    agent_id, company_id = _agent_context(request)
    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..models.enums import WorkProductType
    from ..services.work_product_service import WorkProductService

    try:
        product_type = WorkProductType(body.type)
    except ValueError:
        from fastapi import HTTPException as _HTTPException

        raise _HTTPException(status_code=422, detail=f"Unknown product type: {body.type!r}")

    svc = lazy_singleton(WorkProductService)()
    factory = get_async_session_factory()
    async with factory() as session:
        async with session.begin():
            product = await svc.create(
                session,
                company_id=company_id,
                work_item_id=body.work_item_id,
                type=product_type,
                title=body.title,
                content_text=body.content_text,
                storage_path=body.storage_path,
                url=body.url,
                heartbeat_run_id=body.heartbeat_run_id,
            )
    return {"artifact_id": str(product.id), "recorded": True}


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


@router.post("/attachments", status_code=201)
async def agent_upload_attachment(
    work_item_id: str,
    file: UploadFile = File(...),
    request: Request = None,
) -> Dict[str, Any]:
    """Agent uploads a file attachment to a work item (GH#8253)."""
    agent_id, company_id = _agent_context(request)
    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..services.attachment_service import AttachmentService, AttachmentTooLarge

    content = await file.read()
    factory = get_async_session_factory()
    try:
        async with factory() as session:
            svc = lazy_singleton(AttachmentService)()
            row = await svc.upload(
                session,
                company_id=company_id,
                work_item_id=work_item_id,
                filename=file.filename or "upload",
                content_type=file.content_type or "application/octet-stream",
                content=content,
                uploaded_by_agent_id=agent_id,
            )
        return {
            "id": str(row.id),
            "filename": row.filename,
            "size_bytes": row.size_bytes,
            "text_extracted": row.text_extracted,
        }
    except AttachmentTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))


@router.get("/context/{item_id}")
async def get_item_context(item_id: uuid.UUID, request: Request) -> Dict[str, Any]:
    """Return agent context for a work item, including any human handoff KB notes (GH#8232)."""
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


class PeerAgent(BaseModel):
    agent_id: str
    agent_name: str
    title: str
    role: str
    capabilities: str
    manager_name: Optional[str] = None


@router.get("/peers/search")
async def search_peer_agents(
    q: str,
    limit: int = 10,
    request: Request = None,
) -> Dict[str, Any]:
    """Search peer agents by capabilities (for delegation decisions).

    Agents use this to discover peers who can handle specific work.
    Returns matching agents from the company agents KB collection.

    Args:
        q: Search query (\"who handles cloud devops?\", etc.)
        limit: Max results to return
        request: Request context injected by middleware

    Returns:
        List of matching peer agents with capability metadata.
    """
    agent_id, company_id = _agent_context(request)
    try:
        from autobot_shared.logging_manager import get_logger
        from knowledge import get_knowledge_base

        from ..kb import AgentCapabilityIndexer

        logger_inner = get_logger(__name__)
        indexer = AgentCapabilityIndexer()
        kb = await get_knowledge_base()
        collection_name = indexer._collection_name(company_id)

        try:
            collection = await kb._async_chroma_client.get_collection(collection_name)
        except Exception:
            return {"agents": [], "count": 0, "query": q}

        results = await collection.query(
            query_texts=[q],
            n_results=min(limit, 50),
            include=["documents", "metadatas"],
        )

        agents = []
        if results.get("ids") and len(results["ids"]) > 0:
            docs = results.get("documents", [[]])[0] if results.get("documents") else []
            metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
            for idx, (doc_id, metadata) in enumerate(zip(results["ids"][0], metadatas)):
                agents.append(
                    PeerAgent(
                        agent_id=metadata.get("agent_id", ""),
                        agent_name=metadata.get("agent_name", ""),
                        title=metadata.get("title", ""),
                        role=metadata.get("role", ""),
                        capabilities=docs[idx] if idx < len(docs) else "",
                        manager_name=metadata.get("manager_name"),
                    )
                )

        return {"agents": agents, "count": len(agents), "query": q, "querying_agent": agent_id}
    except Exception as e:
        from autobot_shared.logging_manager import get_logger

        logger_inner = get_logger(__name__)
        logger_inner.exception("Peer agent search failed for agent %s: %s", agent_id, str(e))
        raise HTTPException(status_code=500, detail=f"Peer search failed: {str(e)}")


# ── Agent-facing wiki routes (GH#9021) ─────────────────────────────────────
# Agents can read and write their own wiki entries via LLC bearer token.


class AgentWikiEntryIn(BaseModel):
    namespace: str = "general"
    key: str
    title: str
    body: str = ""


class AgentWikiEntryOut(BaseModel):
    id: str
    namespace: str
    key: str
    title: str
    body: str


@router.get("/wiki/entries")
async def agent_list_wiki(namespace: Optional[str] = None, request: Request = None) -> Dict[str, Any]:
    """List this agent's own wiki entries."""
    agent_id, company_id = _agent_context(request)
    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..services.agent_wiki_service import AgentWikiService

    import uuid as _uuid

    factory = get_async_session_factory()
    async with factory() as session:
        svc = lazy_singleton(AgentWikiService)()
        entries = await svc.list_entries(session, agent_id, _uuid.UUID(company_id), namespace)
    return {
        "entries": [
            AgentWikiEntryOut(
                id=str(e.id), namespace=e.namespace, key=e.key, title=e.title, body=e.body
            )
            for e in entries
        ]
    }


@router.post("/wiki/entries", status_code=201)
async def agent_create_wiki_entry(body: AgentWikiEntryIn, request: Request = None) -> Dict[str, Any]:
    """Create a wiki entry scoped to this agent."""
    agent_id, company_id = _agent_context(request)
    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..services.agent_wiki_service import AgentWikiService

    import uuid as _uuid

    factory = get_async_session_factory()
    async with factory() as session:
        svc = lazy_singleton(AgentWikiService)()
        entry = await svc.create_entry(
            session,
            agent_id=agent_id,
            company_id=_uuid.UUID(company_id),
            namespace=body.namespace,
            key=body.key,
            title=body.title,
            body=body.body,
        )
        await session.commit()
    return AgentWikiEntryOut(
        id=str(entry.id), namespace=entry.namespace, key=entry.key, title=entry.title, body=entry.body
    ).model_dump()


__all__ = ["router"]
