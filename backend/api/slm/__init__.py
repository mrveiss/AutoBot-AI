# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM API Package

REST API endpoints for Service Lifecycle Manager.
"""

from backend.api.slm.nodes import router as nodes_router
from backend.api.slm.heartbeats import router as heartbeats_router

__all__ = ["nodes_router", "heartbeats_router"]
