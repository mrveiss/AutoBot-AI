# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM API Package

DEPRECATED: This entire package should be deleted as part of Issue #729 layer separation.
All SLM functionality has been moved to slm-server at 172.16.168.19.

REST and WebSocket API endpoints for Service Lifecycle Manager.
"""

# TODO: DELETE THIS ENTIRE DIRECTORY - Part of Issue #729 layer separation
# backend/services/slm/ has been removed, making these routers non-functional
# SLM server at 172.16.168.19 provides these endpoints

# COMMENTED OUT - Non-functional after backend/services/slm/ removal
# from backend.api.slm.nodes import router as nodes_router
# from backend.api.slm.heartbeats import router as heartbeats_router
# from backend.api.slm.deployments import router as deployments_router
# from backend.api.slm.stateful import router as stateful_router
# from backend.api.slm.websockets import (
#     router as websockets_router,
#     get_ws_manager,
#     create_reconciler_callbacks,
#     get_health_update_callback,
# )

# Placeholder to prevent import errors
nodes_router = None
heartbeats_router = None
deployments_router = None
stateful_router = None
websockets_router = None

def get_ws_manager():
    """Deprecated: Use SLM server WebSocket."""
    raise RuntimeError("SLM moved to slm-server (Issue #729)")

def create_reconciler_callbacks():
    """Deprecated: Use SLM server reconciler."""
    raise RuntimeError("SLM moved to slm-server (Issue #729)")

def get_health_update_callback():
    """Deprecated: Use SLM server health updates."""
    raise RuntimeError("SLM moved to slm-server (Issue #729)")

__all__ = [
    "nodes_router",
    "heartbeats_router",
    "deployments_router",
    "stateful_router",
    "websockets_router",
    "get_ws_manager",
    "create_reconciler_callbacks",
    "get_health_update_callback",
]
