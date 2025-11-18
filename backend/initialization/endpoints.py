# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Root-Level API Endpoints

Registers root-level endpoints that frontend expects directly under /api
"""

import logging
from datetime import datetime

from fastapi import FastAPI

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)


def register_root_endpoints(app: FastAPI):
    """
    Register root-level API endpoints

    Adds health and version endpoints that frontend expects:
    - GET /api/health - Health check endpoint
    - GET /api/version - Version information endpoint

    Args:
        app: FastAPI application instance

    Example:
        ```python
        from backend.initialization.endpoints import register_root_endpoints

        app = FastAPI()
        register_root_endpoints(app)
        ```
    """

    @app.get("/api/health")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def root_health_check():
        """
        Root health endpoint that frontend expects

        Returns:
            dict: Health status with timestamp
        """
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "autobot-backend",
        }

    @app.get("/api/version")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def root_version():
        """
        Root version endpoint that frontend expects

        Returns:
            dict: Version information with timestamp
        """
        return {
            "version": "0.0.1",
            "build": "dev",
            "timestamp": datetime.now().isoformat(),
        }

    logger.info("✅ Root endpoints registered: /api/health, /api/version")


__all__ = ["register_root_endpoints"]
