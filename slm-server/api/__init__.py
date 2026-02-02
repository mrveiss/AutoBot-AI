# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM API Package

FastAPI routers for the SLM backend.
"""

from .agents import router as agents_router
from .auth import router as auth_router
from .blue_green import router as blue_green_router
from .code_sync import router as code_sync_router
from .config import node_config_router
from .config import router as config_router
from .deployments import router as deployments_router
from .discovery import router as discovery_router
from .health import router as health_router
from .maintenance import router as maintenance_router
from .monitoring import router as monitoring_router
from .nodes import router as nodes_router
from .orchestration import router as orchestration_router
from .security import router as security_router
from .services import fleet_router as fleet_services_router
from .services import router as services_router
from .settings import router as settings_router
from .stateful import router as stateful_router
from .tls import node_tls_router, tls_router
from .updates import router as updates_router
from .vnc import node_vnc_router, vnc_router
from .websocket import router as websocket_router

__all__ = [
    "agents_router",
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
    "node_vnc_router",
    "vnc_router",
    "node_tls_router",
    "tls_router",
    "security_router",
    "code_sync_router",
    "orchestration_router",
    "config_router",
    "node_config_router",
    "discovery_router",
]
