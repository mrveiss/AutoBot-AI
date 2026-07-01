# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Root-Level API Endpoints

Registers root-level endpoints that frontend expects directly under /api
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, Request

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import ConnectionStatus
from circuit_breaker import get_circuit_breaker_manager

logger = get_logger(__name__)


def _get_circuit_breaker_states() -> Dict[str, Any]:
    """Return all registered circuit breaker states for health reporting."""
    try:
        return get_circuit_breaker_manager().get_all_states()
    except Exception:
        logger.debug("Could not retrieve circuit breaker states", exc_info=True)
        return {}


def _service_status(state: Any, attr: str) -> str:
    """Return 'ready' if app.state attribute is set and truthy, else 'unavailable'."""
    return "ready" if getattr(state, attr, None) else "unavailable"


def _ai_stack_status(state: Any) -> str:
    """Return AI Stack status from client's connection_status property."""
    client = getattr(state, "ai_stack_client", None)
    if not client:
        return "unavailable"
    status = getattr(client, "connection_status", ConnectionStatus.UNKNOWN)
    if status == ConnectionStatus.CONNECTED:
        return ConnectionStatus.CONNECTED.value
    if status == ConnectionStatus.ERROR:
        return ConnectionStatus.ERROR.value
    return ConnectionStatus.UNKNOWN.value


def _build_services_status(state: Any) -> Dict[str, str]:
    """Build per-service status dict from app.state attributes."""
    return {
        "knowledge_base": _service_status(state, "knowledge_base"),
        "chat_workflow": _service_status(state, "chat_workflow_manager"),
        "llm_sync": _service_status(state, "background_llm_sync"),
        "ai_stack": _ai_stack_status(state),
        "ai_stack_agents": _service_status(state, "ai_stack_agents"),
        "graph_rag": _service_status(state, "graph_rag_service"),
    }


def _build_capabilities(ai_stack_ready: bool, ai_agents_ready: bool, npu_ready: bool) -> Dict[str, bool]:
    """Build capabilities dict from AI readiness flags."""
    return {
        "rag_enhanced_search": ai_stack_ready,
        "multi_agent_coordination": ai_agents_ready,
        "knowledge_extraction": ai_stack_ready,
        "ai_stack_chat_available": ai_stack_ready,
        "npu_acceleration": npu_ready,
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


async def _build_agent_card_response(request: Request) -> dict:
    """Helper for register_root_endpoints. Ref: #1088.

    Build A2A agent card dict from the request base URL, or return an
    error fallback when the a2a package is unavailable.
    """
    try:
        from a2a.agent_card import build_agent_card

        base_url = str(request.base_url).rstrip("/")
        card = build_agent_card(base_url)
        return card.to_dict()
    except Exception as exc:
        logger.warning("A2A agent card unavailable: %s", exc)
        return {"error": "agent card unavailable"}


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

    def _health_payload(state: Any) -> Dict[str, Any]:
        """Build the /api/health response body (shared by GET and HEAD)."""
        services = _build_services_status(state)
        ai_stack_ready = services.get("ai_stack") == "connected"
        ai_agents_ready = services.get("ai_stack_agents") == "ready"
        npu_ready = bool(getattr(state, "npu_worker_ready", False))
        return {
            "status": "healthy",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "service": "autobot-backend",
            "services": services,
            "ai_enhanced": ai_stack_ready,
            # `_get_agent_count` only counts AI Stack agents, not the local
            # backend agent registry. Renamed to make the semantic explicit so
            # consumers don't conflate this with the (much larger) total in
            # /api/agents/registry. (#6749 follow-up — Chrome-plugin TODO #8.)
            "ai_stack_agent_count": _get_agent_count(state),
            "capabilities": _build_capabilities(ai_stack_ready, ai_agents_ready, npu_ready),
            "circuit_breakers": _get_circuit_breaker_states(),
        }

    @app.get("/api/health", operation_id="root_health_check_get")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def root_health_check_get(request: Request):
        """Health endpoint with per-service breakdown and capabilities."""
        return _health_payload(request.app.state)

    @app.head("/api/health", operation_id="root_health_check_head", include_in_schema=False)
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def root_health_check_head(request: Request):
        """HEAD variant for liveness probes — FastAPI strips the body automatically."""
        return _health_payload(request.app.state)

    @app.get("/api/health/ai-stack")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def ai_stack_health(request: Request):
        """Dedicated AI Stack health endpoint."""
        return await _ai_stack_health_response(request.app.state)

    @app.get("/api/health/circuit-breakers")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def circuit_breakers_health():
        """Detailed circuit breaker states for all registered services."""
        states = _get_circuit_breaker_states()
        open_count = sum(1 for s in states.values() if s.get("state") == "open")
        return {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "total": len(states),
            "open": open_count,
            "circuit_breakers": states,
        }

    @app.get("/api/health/feature-routers")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def feature_routers_health():
        """Cross-worker feature-router load status (#6797, #6808).

        Returns the structured load-results registry populated by
        ``load_feature_routers()``. Until this endpoint existed, the
        graceful-fallback pattern from #281 silently dropped failed routers
        (boot succeeded with /api/* endpoints absent — see #6583, #6664-6667).

        #6808: results are now aggregated across all uvicorn workers via Redis
        so a poll is not subject to per-worker sampling variance. Divergent
        worker states (one worker missing a router) are visible with
        worker-PID provenance in the ``workers`` field.
        """
        from initialization.router_registry.feature_routers import (
            FEATURE_ROUTER_CONFIGS,
            get_cross_worker_load_results,
        )

        cross = get_cross_worker_load_results()
        aggregated = cross["aggregated"]
        loaded_count = sum(1 for r in aggregated if r["loaded"])
        expected = len(FEATURE_ROUTER_CONFIGS)
        return {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "expected": expected,
            "loaded": loaded_count,
            "failed": expected - loaded_count,
            "all_loaded": loaded_count == expected,
            "worker_count": cross["worker_count"],
            "redis_available": cross["redis_available"],
            "routers": aggregated,
            "workers": cross["workers"],
        }

    @app.get("/api/version")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def root_version():
        """Version endpoint."""
        return {
            "version": "0.0.1",
            "build": "dev",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    # Issue #961: A2A canonical discovery endpoint (spec §3.1)
    # Served at /.well-known/agent.json as required by the A2A protocol.
    # The /api/a2a/agent-card endpoint also serves this for API clients.
    @app.get("/.well-known/agent.json", include_in_schema=False)
    async def well_known_agent_card(request: Request):
        """A2A canonical Agent Card discovery endpoint."""
        return await _build_agent_card_response(request)

    logger.info(
        "Root endpoints registered: /api/health, /api/health/ai-stack, "
        "/api/health/circuit-breakers, /api/version, /.well-known/agent.json"
    )


__all__ = ["register_root_endpoints"]
