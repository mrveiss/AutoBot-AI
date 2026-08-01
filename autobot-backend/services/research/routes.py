# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Research REST API (#12622).

``POST /research`` — the first consumer of ``ResearchOrchestrator`` (owner
decision, design doc §12). Mounted like ``services/autoresearch/routes.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger

from .models import ResearchRequest, ResearchResponse
from .orchestrator import ResearchOrchestrator

logger = get_logger(__name__)

router = APIRouter(tags=["research"])

_orchestrator: ResearchOrchestrator | None = None


def _get_orchestrator(request: Request) -> ResearchOrchestrator:
    """Get or create the process-wide ``ResearchOrchestrator`` singleton."""
    global _orchestrator
    app_orchestrator = getattr(request.app.state, "research_orchestrator", None)
    if app_orchestrator is not None:
        return app_orchestrator
    if _orchestrator is None:
        _orchestrator = ResearchOrchestrator()
    request.app.state.research_orchestrator = _orchestrator
    return _orchestrator


@router.post("", response_model=ResearchResponse)
async def run_research(
    request: Request,
    body: ResearchRequest,
    _user: dict = Depends(get_current_user),
) -> ResearchResponse:
    """Run a bounded research pass and return a grounded, cited answer.

    Findings land as quarantined KB facts (dedicated ``research`` collection,
    not visible to general chat/RAG) while the response also carries a
    directly-usable synthesized answer with inline citations.
    """
    orchestrator = _get_orchestrator(request)
    try:
        return await orchestrator.research(body.question, body.options)
    except Exception as exc:  # noqa: BLE001 — user-facing 500, never a bare stack trace
        logger.error("POST /research failed for question %.80s: %s", body.question, exc)
        raise HTTPException(status_code=500, detail="Research request failed") from exc
