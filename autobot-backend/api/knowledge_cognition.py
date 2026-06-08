# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cognition Store API — Issue #4679

Provides endpoints for the Cognition Store seeding layer:

  GET  /api/knowledge/cognition-store/status   — seed status per collection
  POST /api/knowledge/cognition-store/seed     — trigger (re-)seed from manifest
"""

import os

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.schemas_knowledge import (
    KnowledgeCognitionSeedResponse,
    KnowledgeCognitionStatusResponse,
    SeedRequest,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.path_constants import PATH
from services.knowledge.cognition_seeder import get_cognition_seeder

logger = get_logger(__name__)

router = APIRouter(tags=["knowledge-cognition"])

# Default manifest path relative to project root
_DEFAULT_MANIFEST = "cognition_seed.yaml"


@router.get("/cognition-store/status", response_model=KnowledgeCognitionStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cognition_store_status",
    error_code_prefix="KNOWLEDGE_COGNITION",
)
async def get_cognition_store_status():
    """Return seed status for all ChromaDB collections that contain seeded docs.

    Issue #4679: surfaces which collections are seeded, when, and how many
    documents were contributed by each source.
    """
    seeder = await get_cognition_seeder()
    statuses = await seeder.get_seed_status()
    return {
        "collections": [
            {
                "collection": s.collection,
                "seeded_at": s.seeded_at,
                "document_count": s.document_count,
                "sources": s.sources,
            }
            for s in statuses
        ],
        "total_seeded_collections": len(statuses),
    }


async def _run_seed(manifest_path: str) -> None:
    """Background task: seed from manifest and log outcome."""
    seeder = await get_cognition_seeder()
    try:
        count = await seeder.seed_from_manifest(manifest_path)
        logger.info("Background seed complete: manifest=%s chunks=%d", manifest_path, count)
    except Exception as exc:
        logger.error("Background seed failed: manifest=%s error=%s", manifest_path, exc)


@router.post("/cognition-store/seed", response_model=KnowledgeCognitionSeedResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="trigger_cognition_seed",
    error_code_prefix="KNOWLEDGE_COGNITION",
)
async def trigger_cognition_seed(
    request: SeedRequest,
    background_tasks: BackgroundTasks,
    _user=check_admin_permission,
):
    """Trigger a (re-)seed of ChromaDB from the cognition_seed.yaml manifest.

    The seed runs in the background so the response returns immediately.
    Issue #4679.
    """
    manifest_path = request.manifest_path
    # Resolve relative paths against project root
    if not os.path.isabs(manifest_path):
        manifest_path = str(PATH.PROJECT_ROOT / manifest_path)

    if not os.path.isfile(manifest_path):
        raise HTTPException(
            status_code=404,
            detail=f"Manifest not found: {request.manifest_path}",
        )

    background_tasks.add_task(_run_seed, manifest_path)
    logger.info("Cognition seed scheduled: manifest=%s", manifest_path)
    return {"status": "seeding_started", "manifest": request.manifest_path}
