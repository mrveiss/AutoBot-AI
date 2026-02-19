# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Root-Level API Endpoints

Registers root-level endpoints that frontend expects directly under /api
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, Request

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)


def _service_status(state: Any, attr: str) -> str:
    """Return 'ready' if app.state attribute is set and truthy, else 'unavailable'."""
    return "ready" if getattr(state, attr, None) else "unavailable"


def _build_services_status(state: Any) -> Dict[str, str]:
    """Build per-service status dict from app.state attributes."""
    return {
        "knowledge_base": _service_status(state, "knowledge_base"),
        "chat_workflow": _service_status(state, "chat_workflow_manager"),
        "llm_sync": _service_status(state, "background_llm_sync"),
        "ai_stack": _service_status(state, "ai_stack_client"),
        "ai_stack_agents": _service_status(state, "ai_stack_agents"),
        "graph_rag": _service_status(state, "graph_rag_service"),
    }


def _build_capabilities(ai_stack_ready: bool, ai_agents_ready: bool) -> Dict[str, bool]:
    """Build capabilities dict from AI readiness flags."""
    return {
        "rag_enhanced_search": ai_stack_ready,
        "multi_agent_coordination": ai_agents_ready,
        "knowledge_extraction": ai_stack_ready,
        "enhanced_chat": ai_stack_ready,
        "npu_acceleration": ai_agents_ready,
    }


def _get_agent_count(state: Any) -> int:
    """Return number of initialized AI agents, or 0."""
    ai_agents = getattr(state, "ai_stack_agents", None)
    if not ai_agents:
        return 0
    return len(ai_agents.get("agents", []))


async def _ai_stack_health_response(state: Any) -> Dict[str, Any]:
    """Return AI Stack health from client or unavailable fallback."""
    ai_client = getattr(state, "ai_stack_client", None)
    if ai_client:
        return await ai_client.health_check()
    return {
        "status": "unavailable",
        "message": "AI Stack client not initialized",
        "timestamp": time.time(),
    }


def register_root_endpoints(app: FastAPI) -> None:
    """
    Register root-level API endpoints.

    Adds health and version endpoints that frontend expects:
    - GET /api/health        - Rich health check with per-service status
    - GET /api/health/ai-stack - Dedicated AI Stack health endpoint
    - GET /api/version       - Version information endpoint

    Args:
        app: FastAPI application instance
    """

    @app.get("/api/health")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def root_health_check(request: Request):
        """Health endpoint with per-service breakdown and capabilities."""
        state = request.app.state
        services = _build_services_status(state)
        ai_stack_ready = services.get("ai_stack") == "ready"
        ai_agents_ready = services.get("ai_stack_agents") == "ready"
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "autobot-backend",
            "services": services,
            "ai_enhanced": ai_stack_ready,
            "agent_count": _get_agent_count(state),
            "capabilities": _build_capabilities(ai_stack_ready, ai_agents_ready),
        }

    @app.get("/api/health/ai-stack")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def ai_stack_health(request: Request):
        """Dedicated AI Stack health endpoint."""
        return await _ai_stack_health_response(request.app.state)

    @app.get("/api/version")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def root_version():
        """Version endpoint."""
        return {
            "version": "0.0.1",
            "build": "dev",
            "timestamp": datetime.now().isoformat(),
        }

    # Issue #961: A2A canonical discovery endpoint (spec §3.1)
    # Served at /.well-known/agent.json as required by the A2A protocol.
    # The /api/a2a/agent-card endpoint also serves this for API clients.
    @app.get("/.well-known/agent.json", include_in_schema=False)
    async def well_known_agent_card(request: Request):
        """A2A canonical Agent Card discovery endpoint."""
        try:
            from a2a.agent_card import build_agent_card

            base_url = str(request.base_url).rstrip("/")
            card = build_agent_card(base_url)
            return card.to_dict()
        except Exception as exc:
            logger.warning("A2A agent card unavailable: %s", exc)
            return {"error": "agent card unavailable"}

    logger.info(
        "✅ Root endpoints registered: /api/health, /api/health/ai-stack, "
        "/api/version, /.well-known/agent.json"
    )


__all__ = ["register_root_endpoints"]
