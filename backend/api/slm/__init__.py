# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM API Package

REST and WebSocket API endpoints for Service Lifecycle Manager.
"""

from backend.api.slm.nodes import router as nodes_router
from backend.api.slm.heartbeats import router as heartbeats_router
from backend.api.slm.deployments import router as deployments_router
from backend.api.slm.websockets import (
    router as websockets_router,
    get_ws_manager,
    create_reconciler_callbacks,
    get_health_update_callback,
)

__all__ = [
    "nodes_router",
    "heartbeats_router",
    "deployments_router",
    "websockets_router",
    "get_ws_manager",
    "create_reconciler_callbacks",
    "get_health_update_callback",
]
