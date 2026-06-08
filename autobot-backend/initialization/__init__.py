# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
App Initialization Modules

Modular initialization components for FastAPI application.
"""

from .endpoints import register_root_endpoints
from .lifespan import create_lifespan_manager
from .middleware import configure_middleware
from .routers import load_core_routers, load_optional_routers

__all__ = [
    "create_lifespan_manager",
    "configure_middleware",
    "load_core_routers",
    "load_optional_routers",
    "register_root_endpoints",
]
