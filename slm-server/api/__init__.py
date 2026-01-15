# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM API Package

FastAPI routers for the SLM backend.
"""

from .auth import router as auth_router
from .nodes import router as nodes_router
from .deployments import router as deployments_router
from .settings import router as settings_router
from .health import router as health_router

__all__ = [
    "auth_router",
    "nodes_router",
    "deployments_router",
    "settings_router",
    "health_router",
]
