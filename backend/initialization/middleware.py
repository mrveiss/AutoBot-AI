# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
FastAPI Middleware Configuration

Configures all middleware for FastAPI application:
- CORS (Cross-Origin Resource Sharing)
- GZip compression
- Service authentication
"""

import logging
from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.constants.network_constants import NetworkConstants  # noqa: F401 - used in docstring example
from src.config import UnifiedConfigManager

logger = logging.getLogger(__name__)


def configure_cors(app: FastAPI, allow_origins: Optional[List[str]] = None):
    """
    Configure CORS middleware

    Args:
        app: FastAPI application instance
        allow_origins: List of allowed origins (default: load from config)

    Example:
        ```python
        configure_cors(app)
        configure_cors(app, allow_origins=[f"http://localhost:{NetworkConstants.FRONTEND_PORT}"])
        ```
    """
    # Generate from centralized configuration if not provided
    if allow_origins is None:
        config = UnifiedConfigManager()
        allow_origins = config.get_cors_origins()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger.info(
        f"✅ CORS middleware configured with {len(allow_origins)} allowed origins"
    )


def configure_gzip(app: FastAPI, minimum_size: int = 1000):
    """
    Configure GZip compression middleware

    Args:
        app: FastAPI application instance
        minimum_size: Minimum response size to compress (default: 1000 bytes)

    Example:
        ```python
        configure_gzip(app)
        configure_gzip(app, minimum_size=500)
        ```
    """
    app.add_middleware(GZipMiddleware, minimum_size=minimum_size)
    logger.info("✅ GZip middleware configured (minimum size: %s bytes)", minimum_size)


def configure_service_auth(app: FastAPI):
    """
    Configure service authentication middleware

    Attempts to enable ENFORCEMENT MODE first, falls back to LOGGING MODE.
    If neither available, logs warning and continues without auth middleware.

    Args:
        app: FastAPI application instance

    Example:
        ```python
        configure_service_auth(app)
        ```
    """
    # Try ENFORCEMENT MODE
    try:
        from backend.middleware.service_auth_enforcement import (
            enforce_service_auth,
            log_enforcement_status,
        )

        app.add_middleware(BaseHTTPMiddleware, dispatch=enforce_service_auth)
        log_enforcement_status()
        logger.info("✅ Service Authentication Middleware (ENFORCEMENT MODE) enabled")
        return

    except ImportError as e:
        logger.warning("⚠️ Service auth enforcement middleware not available: %s", e)

    # Fallback to LOGGING MODE
    try:
        from backend.middleware.service_auth_logging import ServiceAuthLoggingMiddleware

        app.add_middleware(ServiceAuthLoggingMiddleware)
        logger.info(
            "✅ Service Authentication Middleware (LOGGING MODE - fallback) enabled"
        )
        return

    except ImportError as e2:
        logger.warning("⚠️ Service auth middleware not available: %s", e2)


def configure_middleware(
    app: FastAPI,
    allow_origins: Optional[List[str]] = None,
    gzip_minimum_size: int = 1000,
    enable_service_auth: bool = True,
):
    """
    Configure all middleware for FastAPI application

    Args:
        app: FastAPI application instance
        allow_origins: List of allowed CORS origins (default: load from config)
        gzip_minimum_size: Minimum size for GZip compression (default: 1000 bytes)
        enable_service_auth: Enable service authentication middleware (default: True)

    Example:
        ```python
        from backend.initialization.middleware import configure_middleware

        app = FastAPI()
        configure_middleware(app)
        ```
    """
    logger.info("⚙️ Configuring middleware...")

    # Configure CORS
    configure_cors(app, allow_origins)

    # Configure GZip compression
    configure_gzip(app, gzip_minimum_size)

    # Configure Service Authentication (optional)
    if enable_service_auth:
        configure_service_auth(app)

    logger.info("✅ All middleware configured successfully")


__all__ = [
    "configure_middleware",
    "configure_cors",
    "configure_gzip",
    "configure_service_auth",
]
