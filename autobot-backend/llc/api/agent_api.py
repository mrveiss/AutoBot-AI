# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from autobot_shared.logging_manager import get_logger

from ._common import agent_node_uuid

logger = get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["llc-agent"])


def _agent_context(request: Request) -> tuple[str, str]:
    """Extract agent_id and company_id from middleware-injected state."""
    agent_id = getattr(request.state, "agent_id", None)
    company_id = getattr(request.state, "company_id", None)
    if not agent_id or not company_id:
        raise HTTPException(status_code=401, detail="Agent context not injected")
    return agent_id, company_id


async def _assert_item_in_company(item_id: str, company_id: str) -> None:
    """GH#12156: 404 unless the work item belongs to the caller's company.

    KB collections are keyed by work_item_id alone, so tenant isolation must be
    enforced at the handler by verifying ownership before any KB read.
    """
    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..services.work_item_service import WorkItemService

    factory = get_async_session_factory()
    async with factory() as session:
        svc = lazy_singleton(WorkItemService)()
        item = await svc.get(session, item_id)
    if item is None or str(item.company_id) != str(company_id):
        raise HTTPException(status_code=404, detail="Work item not found")


@router.get("/work-items/next")
async def get_next_work_item(request: Request) -> Dict[str, Any]:
    """Claim the next work item for this agent, or report that there is none (#15905).

    "Next" is not a new opinion: `checkout_next` reuses the ordering
    `BacklogService.list` already applies, so the item handed to an agent is the
    one a human sees at the top of the same backlog.

    `{"work_item": None}` with `checked_out: False` is an ordinary answer, not a
    failure — an agent asking for work when there is none is the common case.
    The field is kept distinct from the #15859 stub marker so a caller can tell
    "nothing to do" from "this route does nothing", which is exactly the
    distinction the stub response existed to make.
    """
    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..services.work_item_queue import checkout_next
    from ..services.work_item_service import WorkItemService

    agent_id, company_id = _agent_context(request)

    # The slug is not the assignee key. `checkout` writes
    # `assignee_agent_id = uuid.UUID(agent_id)` against a UUID column, so
    # handing it the middleware's slug raises ValueError -- a 500 for a
    # condition that is not a server fault.
    node_uuid = await agent_node_uuid(agent_id, company_id)
    if node_uuid is None:
        # Deliberately NOT "no eligible work". An agent whose org node is missing
        # would otherwise be told there is nothing to do, forever, in the same
        # words used when the backlog is simply empty.
        raise HTTPException(status_code=404, detail=f"No agent node for {agent_id} in this company")

    factory = get_async_session_factory()
    async with factory() as session:
        svc = lazy_singleton(WorkItemService)()
        item = await checkout_next(session, svc, agent_id=str(node_uuid), company_id=company_id)
        await session.commit()

    if item is None:
        return {"work_item": None, "checked_out": False, "message": "No eligible work item"}

    return {
        "work_item": {
            "id": str(item.id),
            "identifier": item.identifier,
            "title": item.title,
            "status": item.status,
            "priority": item.priority,
        },
        "checked_out": True,
        "run_id": item.checkout_run_id,
    }


class StatusUpdate(BaseModel):
    status: str
    comment: Optional[str] = None


@router.post("/work-items/{item_id}/status")
async def update_work_item_status(item_id: uuid.UUID, body: StatusUpdate, request: Request) -> Dict[str, Any]:
    """Transition a work item, enforcing the state machine (#15859).

    This used to echo the requested status back with ``{"updated": True}``
    without performing the transition, so a caller reading the response saw its
    own input and concluded the write had happened.

    The company check is not incidental: ``transition_status`` takes
    ``company_id`` and this route is reached with an agent's context, so an
    item belonging to another company must 404 rather than transition.
    """
    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..models.enums import WorkItemStatus
    from ..services.work_item_service import WorkItemService

    _, company_id = _agent_context(request)
    try:
        new_status = WorkItemStatus(body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown work item status {body.status!r}") from exc

    factory = get_async_session_factory()
    async with factory() as session:
        try:
            item = await lazy_singleton(WorkItemService)().transition_status(
                session,
                work_item_id=str(item_id),
                new_status=new_status,
                company_id=str(company_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await session.commit()
        resulting = str(item.status)

    return {"updated": True, "item_id": str(item_id), "status": resulting}


class CostEvent(BaseModel):
    model: str
    tokens_in: int
    tokens_out: int
    work_item_id: Optional[str] = None


@router.post("/cost-events")
async def ingest_cost_event(body: CostEvent, request: Request) -> Dict[str, Any]:
    """Record an agent's token cost against its budget (#15859).

    This used to return ``{"recorded": True}`` without calling anything. A
    budget that is never charged is never exceeded, so the hard stop could not
    fire -- and the response carried no marker, so a caller could not tell
    "recorded" from "discarded".

    ``BudgetExhausted`` is propagated as 402 rather than swallowed: the whole
    point of ingesting the event is that exceeding the limit stops the agent.
    ``UnpricedModel`` is 422 -- the event is well-formed but its cost cannot be
    computed, and charging zero is what #15860 was.
    """
    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..exceptions import BudgetExhausted, UnpricedModel
    from ..services.budget import BudgetService

    agent_id, company_id = _agent_context(request)
    factory = get_async_session_factory()
    try:
        async with factory() as session:
            cost = await lazy_singleton(BudgetService)().ingest_cost_event(
                session,
                agent_id=agent_id,
                company_id=company_id,
                tokens_in=body.tokens_in,
                tokens_out=body.tokens_out,
                model=body.model,
            )
            await session.commit()
    except BudgetExhausted as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except UnpricedModel as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"recorded": True, "cost": str(cost)}


class CommentBody(BaseModel):
    work_item_id: str
    body: str


@router.post("/comments")
async def post_comment(body: CommentBody, request: Request) -> Dict[str, Any]:
    """Store an agent's comment on a work item (#15905).

    The company check is not incidental. `add_comment` writes `company_id` from
    its argument without reading the item, so without `_assert_item_in_company`
    an agent could comment on another company's work item and the comment would
    be stored under its OWN company — readable by neither side and attached to
    an item its company does not own.
    """
    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..services.work_item_service import WorkItemService

    agent_id, company_id = _agent_context(request)
    await _assert_item_in_company(body.work_item_id, company_id)
    author_uuid = await agent_node_uuid(agent_id, company_id)

    factory = get_async_session_factory()
    async with factory() as session:
        svc = lazy_singleton(WorkItemService)()
        comment = await svc.add_comment(
            session,
            work_item_id=body.work_item_id,
            company_id=company_id,
            body=body.body,
            author_agent_id=str(author_uuid) if author_uuid else None,
        )
        comment_id = str(comment.id)
        await session.commit()

    return {"comment_id": comment_id, "recorded": True}


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
    """Record an agent's completion of a heartbeat run (#15905).

    Updates the existing `llc_heartbeat_runs` row rather than inserting one. The
    scheduler creates the run when it dispatches (`_create_run`, status
    `queued`); this route is the agent reporting how it ended. Inserting here
    would produce two rows for one run and make every count of runs wrong.

    A `run_id` that names no row is a 404, not a silent no-op. The stub echoed
    the caller's own `run_id` back, so a client reading the response saw its
    input and concluded the write had happened — the same defect #15859 fixed on
    two other routes, and the reason `recorded` is now the result of an UPDATE's
    rowcount rather than a constant.

    Scoped by company as well as by id: `run_id` is a UUID, but an agent must
    not be able to close out another company's run by guessing or replaying one.
    """
    from sqlalchemy import update
    from user_management.database import get_async_session_factory

    from ..models.enums import LLCRunStatus
    from ..models.heartbeat_run import LLCHeartbeatRun

    agent_id, company_id = _agent_context(request)

    try:
        status = LLCRunStatus(body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown run status {body.status!r}") from exc

    try:
        run_uuid = uuid.UUID(body.run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"run_id {body.run_id!r} is not a UUID") from exc

    if body.work_item_id is not None:
        await _assert_item_in_company(body.work_item_id, company_id)

    values: Dict[str, Any] = {
        "status": status.value,
        "finished_at": datetime.now(tz=timezone.utc),
    }
    if body.work_item_id is not None:
        values["work_item_id"] = uuid.UUID(body.work_item_id)

    factory = get_async_session_factory()
    async with factory() as session:
        # Core `update`, not `text()`. The raw form needed `CAST(:id AS uuid)`,
        # which is PostgreSQL-only -- correct in production and unrunnable
        # against the SQLite the LLC tests use, so the route could not be tested
        # at all. Core renders the UUID comparison per dialect.
        result = await session.execute(
            update(LLCHeartbeatRun)
            .where(
                LLCHeartbeatRun.id == run_uuid,
                LLCHeartbeatRun.company_id == uuid.UUID(company_id),
                LLCHeartbeatRun.agent_id == agent_id,
            )
            .values(**values)
        )
        if result.rowcount == 0:
            # No row matched. Distinguishable from "recorded" on purpose: a run
            # belonging to another company, another agent, or to nothing at all
            # must not read as a successful report.
            raise HTTPException(status_code=404, detail=f"Heartbeat run {body.run_id} not found for this agent")
        await session.commit()

    return {"recorded": True, "run_id": body.run_id, "status": status.value}


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
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=413, detail="Internal server error")


@router.get("/context/{item_id}")
async def get_item_context(item_id: uuid.UUID, request: Request) -> Dict[str, Any]:
    """Return agent context for a work item, including any human handoff KB notes (GH#8232)."""
    _, company_id = _agent_context(request)  # GH#12148: authenticated agent context
    await _assert_item_in_company(str(item_id), company_id)  # GH#12156: tenant scope
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
    import uuid as _uuid

    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..services.agent_wiki_service import AgentWikiService

    factory = get_async_session_factory()
    async with factory() as session:
        svc = lazy_singleton(AgentWikiService)()
        entries = await svc.list_entries(session, agent_id, _uuid.UUID(company_id), namespace)
    return {
        "entries": [
            AgentWikiEntryOut(id=str(e.id), namespace=e.namespace, key=e.key, title=e.title, body=e.body)
            for e in entries
        ]
    }


@router.post("/wiki/entries", status_code=201)
async def agent_create_wiki_entry(body: AgentWikiEntryIn, request: Request = None) -> Dict[str, Any]:
    """Create a wiki entry scoped to this agent."""
    agent_id, company_id = _agent_context(request)
    import uuid as _uuid

    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..services.agent_wiki_service import AgentWikiService

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
