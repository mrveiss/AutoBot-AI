# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Transcriber API Router
Issue #9044, MVA-2186

Aggregates all transcriber sub-routers into a single router for registration.
"""

from fastapi import APIRouter

from transcriber.routes.ai import router as ai_router
from transcriber.routes.export import router as export_router
from transcriber.routes.kb import router as kb_router
from transcriber.routes.projects import router as projects_router
from transcriber.routes.providers import router as providers_router
from transcriber.routes.recordings import router as recordings_router
from transcriber.routes.transcripts import router as transcripts_router

router = APIRouter(prefix="/transcriber", tags=["transcriber"])

# Include all transcriber sub-routers
router.include_router(ai_router)
router.include_router(export_router)
router.include_router(kb_router)
router.include_router(projects_router)
router.include_router(providers_router)
router.include_router(recordings_router)
router.include_router(transcripts_router)
