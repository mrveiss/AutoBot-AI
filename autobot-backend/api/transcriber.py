# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Transcriber API Router Aggregator

Re-exports all transcriber routers for router registry loading.
Issue #9044, MVA-2186
"""

from fastapi import APIRouter
from transcriber.routes.ai import router as ai_router
from transcriber.routes.export import router as export_router
from transcriber.routes.kb import router as kb_router
from transcriber.routes.projects import router as projects_router
from transcriber.routes.recordings import router as recordings_router
from transcriber.routes.transcripts import router as transcripts_router

# Create main router that includes all transcriber sub-routers
router = APIRouter(prefix="/api/transcriber", tags=["transcriber"])

# Include all transcriber sub-routers
router.include_router(projects_router)
router.include_router(recordings_router)
router.include_router(transcripts_router)
router.include_router(export_router)
router.include_router(ai_router)
router.include_router(kb_router)

__all__ = ["router"]
