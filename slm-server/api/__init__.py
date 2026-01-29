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
from .stateful import router as stateful_router
from .updates import router as updates_router
from .websocket import router as websocket_router
from .services import router as services_router, fleet_router as fleet_services_router
from .maintenance import router as maintenance_router
from .monitoring import router as monitoring_router
from .blue_green import router as blue_green_router

__all__ = [
    "auth_router",
    "nodes_router",
    "deployments_router",
    "settings_router",
    "health_router",
    "stateful_router",
    "updates_router",
    "websocket_router",
    "services_router",
    "fleet_services_router",
    "maintenance_router",
    "monitoring_router",
    "blue_green_router",
]
