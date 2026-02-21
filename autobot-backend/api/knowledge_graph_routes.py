# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Graph Pipeline API Routes.

Issue #759: ECL Pipeline endpoints for entity extraction, temporal events,
hierarchical summarization, and document processing.
"""

import logging
import re
from typing import List, Optional
from uuid import UUID

from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

_SAFE_NAME_RE = re.compile(r"^[\w .'-]{1,200}$")


# --- Request/Response Models ---


class PipelineRunRequest(BaseModel):
    """Request to run the ECL pipeline on a document."""

    document_id: str = Field(..., description="Document ID to process")
    config: Optional[dict] = Field(None, description="Pipeline configuration overrides")


class PipelineRunResponse(BaseModel):
    """Pipeline execution result."""

    document_id: str
    entities_count: int = 0
    relationships_count: int = 0
    events_count: int = 0
    summaries_count: int = 0
    chunks_count: int = 0
    stages_completed: List[str] = []
    errors: List[str] = []


class EventSearchRequest(BaseModel):
    """Temporal event search parameters."""

    start_date: Optional[str] = None
    end_date: Optional[str] = None
    event_types: Optional[List[str]] = None
    entity_name: Optional[str] = None
    limit: int = Field(100, ge=1, le=500)


# --- Pipeline Endpoints ---


@router.post("/pipeline/run", response_model=PipelineRunResponse)
async def run_pipeline(
    request: PipelineRunRequest,
    current_user: dict = Depends(get_current_user),
):
    """Run the Extract-Cognify-Load pipeline on a document."""
    try:
        from knowledge.pipeline.base import PipelineContext
        from knowledge.pipeline.config import get_default_config, load_pipeline_config
        from knowledge.pipeline.runner import PipelineRunner

        if request.config:
            config = load_pipeline_config(request.config)
        else:
            config = get_default_config()

        runner = PipelineRunner(config)
        context = PipelineContext()
        context.document_id = UUID(request.document_id)

        result = await runner.run(request.document_id, context)

        return PipelineRunResponse(
            document_id=request.document_id,
            entities_count=result.entities_count,
            relationships_count=result.relationships_count,
            events_count=result.events_count,
            summaries_count=result.summaries_count,
            chunks_count=result.chunks_count,
            stages_completed=result.stages_completed,
            errors=result.errors,
        )

    except Exception as e:
        logger.error("Pipeline execution failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Pipeline execution failed",
        )


# --- Entity Endpoints ---


@router.get("/entities")
async def list_entities(
    entity_type: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """List extracted entities with optional filters."""
    try:
        from autobot_shared.redis_client import get_redis_client

        redis_client = get_redis_client(async_client=False, database="knowledge")
        entities = _list_entities_from_redis(redis_client, entity_type, query, limit)
        return {"entities": entities, "total": len(entities)}

    except Exception as e:
        logger.error("Entity listing failed: %s", e)
        raise HTTPException(status_code=500, detail="Entity listing failed")


@router.get("/entities/{entity_id}/relationships")
async def get_entity_relationships(
    entity_id: str,
    relationship_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Get relationships for a specific entity."""
    try:
        from autobot_shared.redis_client import get_redis_client

        redis_client = get_redis_client(async_client=False, database="knowledge")
        relationships = _get_relationships_from_redis(
            redis_client, entity_id, relationship_type, limit
        )
        return {
            "entity_id": entity_id,
            "relationships": relationships,
            "total": len(relationships),
        }

    except Exception as e:
        logger.error("Relationship fetch failed for %s: %s", entity_id, e)
        raise HTTPException(status_code=500, detail="Relationship fetch failed")


# --- Temporal Event Endpoints ---


@router.get("/events")
async def search_events(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    entity_name: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """Search temporal events with filters."""
    try:
        from datetime import datetime

        from knowledge.temporal_search import TemporalSearchService

        from autobot_shared.redis_client import get_redis_client

        redis_client = get_redis_client(async_client=False, database="knowledge")
        temporal_svc = TemporalSearchService(redis_client)

        start = datetime.fromisoformat(start_date) if start_date else datetime.min
        end = datetime.fromisoformat(end_date) if end_date else datetime.now()
        types_list = (
            [t.strip() for t in event_types.split(",")] if event_types else None
        )

        events = await temporal_svc.search_events_in_range(
            start_date=start,
            end_date=end,
            event_types=types_list,
            limit=limit,
        )
        return {"events": events, "total": len(events)}

    except Exception as e:
        logger.error("Event search failed: %s", e)
        raise HTTPException(status_code=500, detail="Event search failed")


@router.get("/events/{entity_name}/timeline")
async def get_event_timeline(
    entity_name: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Get chronological timeline of events for an entity."""
    if not _SAFE_NAME_RE.match(entity_name):
        raise HTTPException(status_code=400, detail="Invalid entity name")
    try:
        from knowledge.temporal_search import TemporalSearchService

        from autobot_shared.redis_client import get_redis_client

        redis_client = get_redis_client(async_client=False, database="knowledge")
        temporal_svc = TemporalSearchService(redis_client)

        events = await temporal_svc.get_event_timeline(
            entity_name=entity_name, limit=limit
        )
        return {
            "entity_name": entity_name,
            "events": events,
            "total": len(events),
        }

    except Exception as e:
        logger.error("Timeline fetch failed for %s: %s", entity_name, e)
        raise HTTPException(status_code=500, detail="Timeline fetch failed")


# --- Summary Endpoints ---


@router.get("/summaries/search")
async def search_summaries(
    query: str = Query(..., description="Search query"),
    level: Optional[str] = Query(
        None,
        description="Filter by level: chunk, section, document",
    ),
    top_k: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Vector search on summary embeddings."""
    try:
        from knowledge.summary_search import SummarySearchService
        from utils.async_chromadb_client import get_async_chromadb_client

        chromadb_client = await get_async_chromadb_client()
        summary_svc = SummarySearchService(chromadb_client)

        summaries = await summary_svc.search_summaries(
            query=query, level=level, top_k=top_k
        )
        return {"summaries": summaries, "total": len(summaries)}

    except Exception as e:
        logger.error("Summary search failed: %s", e)
        raise HTTPException(status_code=500, detail="Summary search failed")


@router.get("/documents/{document_id}/overview")
async def get_document_overview(
    document_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get document overview with hierarchical summaries."""
    try:
        from knowledge.summary_search import SummarySearchService
        from utils.async_chromadb_client import get_async_chromadb_client

        chromadb_client = await get_async_chromadb_client()
        summary_svc = SummarySearchService(chromadb_client)

        overview = await summary_svc.get_document_overview(UUID(document_id))
        return overview

    except Exception as e:
        logger.error("Document overview failed for %s: %s", document_id, e)
        raise HTTPException(status_code=500, detail="Document overview failed")


@router.get("/summaries/{summary_id}/drill-down")
async def drill_down_summary(
    summary_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Navigate from summary to children or source chunks."""
    try:
        from knowledge.summary_search import SummarySearchService
        from utils.async_chromadb_client import get_async_chromadb_client

        chromadb_client = await get_async_chromadb_client()
        summary_svc = SummarySearchService(chromadb_client)

        result = await summary_svc.drill_down(UUID(summary_id))
        return result

    except Exception as e:
        logger.error("Drill down failed for %s: %s", summary_id, e)
        raise HTTPException(status_code=500, detail="Drill down failed")


# --- Helper functions ---


def _list_entities_from_redis(redis_client, entity_type, query, limit) -> list:
    """List entities from Redis with optional filtering.

    Helper for list_entities endpoint (#759). Skips index keys
    like entity:<id>:relationships (#1073 SEC-4).
    """
    entities = []
    cursor = 0
    pattern = "entity:*"
    count = 0

    while count < limit:
        cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
        for key in keys:
            if count >= limit:
                break
            key_str = key.decode() if isinstance(key, bytes) else key
            if key_str.count(":") > 1:
                continue
            try:
                entity_data = redis_client.json().get(key)
                if not entity_data:
                    continue
                if entity_type and entity_data.get("entity_type") != entity_type:
                    continue
                if query:
                    name = entity_data.get("name", "").lower()
                    if query.lower() not in name:
                        continue
                entities.append(entity_data)
                count += 1
            except Exception as e:
                logger.debug("Skipping entity key: %s", e)
                continue
        if cursor == 0:
            break

    return entities


def _get_relationships_from_redis(
    redis_client, entity_id, relationship_type, limit
) -> list:
    """Get relationships for an entity from Redis.

    Helper for get_entity_relationships endpoint (#759).
    """
    relationships = []
    rel_key = f"entity:{entity_id}:relationships"

    try:
        rel_ids = redis_client.smembers(rel_key)
        for rel_id in list(rel_ids)[:limit]:
            rel_data = redis_client.json().get(f"relationship:{rel_id}")
            if not rel_data:
                continue
            if (
                relationship_type
                and rel_data.get("relationship_type") != relationship_type
            ):
                continue
            relationships.append(rel_data)
    except Exception as e:
        logger.warning("Relationship lookup failed: %s", e)

    return relationships
