# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Mesh Brain health and status API endpoints for Neural Mesh RAG (#1994, #2120)."""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mesh/brain", tags=["mesh-brain"])

# Module-level scheduler reference set during app startup via set_scheduler().
_scheduler = None


def set_scheduler(scheduler) -> None:
    """Register the MeshBrainScheduler instance used by this router."""
    global _scheduler
    _scheduler = scheduler
    logger.info("MeshBrainScheduler registered with API router")


@router.get("/status")
async def get_mesh_brain_status() -> dict:
    """Return the full job-by-job status of the Mesh Brain scheduler."""
    if _scheduler is None:
        return {"running": False, "jobs": {}, "message": "Mesh Brain not initialized"}
    return _scheduler.get_status()


@router.get("/health")
async def get_mesh_brain_health() -> dict:
    """Return a concise health summary — healthy when no jobs have last_result='failed'.

    Deprecated: This router is not registered and will be removed in a future release.
    Use /api/system/health for system-wide health checks. (#3333)
    """
    logger.warning(
        "Deprecated health endpoint called: /api/mesh/brain/health — "
        "this router is unregistered and will be removed (#3333)"
    )
    if _scheduler is None:
        return {"healthy": False, "reason": "not_initialized"}
    return _build_health_response(_scheduler.get_status())


def _build_health_response(status: dict) -> dict:
    """Derive a health dict from a scheduler status snapshot."""
    failed_jobs = [
        name for name, job in status["jobs"].items() if job["last_result"] == "failed"
    ]
    return {
        "healthy": len(failed_jobs) == 0,
        "running": status["running"],
        "failed_jobs": failed_jobs,
    }
