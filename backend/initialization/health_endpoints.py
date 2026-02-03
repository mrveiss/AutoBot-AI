# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Health Endpoints Module

This module provides health check endpoints for the AutoBot backend,
including enhanced health checks with AI Stack status.
"""

import time

from fastapi import FastAPI

from src.utils.error_boundaries import ErrorCategory, with_error_handling


def register_health_endpoints(app: FastAPI, get_status_fn) -> None:
    """
    Register health check endpoints for the application.

    Args:
        app: FastAPI application instance
        get_status_fn: Function to get initialization status
    """

    # Enhanced health check endpoint
    @app.get("/api/health")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def enhanced_health_check():
        """Enhanced health check endpoint with AI Stack status."""
        # Thread-safe snapshot of init status
        init_status = await get_status_fn()
        ai_stack_ready = init_status.get("ai_stack") == "ready"
        ai_agents_ready = init_status.get("ai_stack_agents") == "ready"

        return {
            "status": "healthy",
            "timestamp": time.time(),
            "background_init": init_status,
            "services": {
                "redis_pools": init_status.get("redis_pools", "unknown"),
                "knowledge_base": init_status.get("knowledge_base", "unknown"),
                "chat_workflow": init_status.get("chat_workflow", "unknown"),
                "llm_sync": init_status.get("llm_sync", "unknown"),
                "ai_stack": init_status.get("ai_stack", "unknown"),
                "ai_stack_agents": init_status.get("ai_stack_agents", "unknown"),
                "distributed_tracing": init_status.get(
                    "distributed_tracing", "unknown"
                ),
            },
            "ai_enhanced": ai_stack_ready,
            "agent_count": len(
                getattr(app.state, "ai_stack_agents", {}).get("agents", [])
            ),
            "capabilities": {
                "rag_enhanced_search": ai_stack_ready,
                "multi_agent_coordination": ai_agents_ready,
                "knowledge_extraction": ai_stack_ready,
                "enhanced_chat": ai_stack_ready,
                "npu_acceleration": ai_agents_ready,
            },
        }

    # AI Stack specific health endpoint
    @app.get("/api/health/ai-stack")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def ai_stack_health():
        """Dedicated AI Stack health endpoint."""
        if hasattr(app.state, "ai_stack_client"):
            ai_client = app.state.ai_stack_client
            health_status = await ai_client.health_check()
            return health_status
        else:
            return {
                "status": "unavailable",
                "message": "AI Stack client not initialized",
                "timestamp": time.time(),
            }
