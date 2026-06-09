# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
FastAPI application factory for the AutoBot backend.

Builds and configures the FastAPI app, registers all routers, middleware,
and startup/shutdown lifecycle hooks. Entry point for all HTTP/WebSocket requests.
"""

import os
import sys
from pathlib import Path
from typing import List

from autobot_shared.logging_manager import get_logger

# Add the project root to Python path for absolute imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Issue #697: OpenTelemetry distributed tracing
from autobot_shared.tracing import init_tracing, instrument_fastapi
from constants.network_constants import (  # noqa: F401 - used in docstring example
    NetworkConstants,
)

# Import initialization modules
from initialization import (
    configure_middleware,
    create_lifespan_manager,
    load_core_routers,
    load_optional_routers,
    register_root_endpoints,
)

# Store logger for app usage
logger = get_logger(__name__)


def _register_exception_handlers(app: FastAPI) -> None:
    """
    Register global exception handlers to prevent stack trace leakage.

    Issue #1733: CodeQL py/stack-trace-exposure — catch unhandled exceptions
    and return generic error responses instead of leaking internal details.
    """

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )


def _register_routers(app: FastAPI) -> None:
    """
    Register core and optional routers with the FastAPI app.

    Issue #665: Extracted from create_fastapi_app to reduce function length.
    Issue #4447: Also registers OpenAI-compatible router under /v1.

    Args:
        app: FastAPI application instance
    """
    core_routers = load_core_routers()
    optional_routers = load_optional_routers()

    for router, prefix, tags, name in core_routers:
        try:
            app.include_router(router, prefix=f"/api{prefix}", tags=tags)
            logger.info("✅ Registered core router: %s at /api%s", name, prefix)
        except Exception as e:
            logger.error("❌ Failed to register core router %s: %s", name, e)

    for router, prefix, tags, name in optional_routers:
        try:
            app.include_router(router, prefix=f"/api{prefix}", tags=tags)
            logger.info("✅ Registered optional router: %s at /api%s", name, prefix)
        except Exception as e:
            logger.warning("⚠️ Failed to register optional router %s: %s", name, e)

    # Issue #4447: OpenAI-compatible endpoints at /v1 (not /api/v1) so that
    # third-party clients (Cursor, Continue, LibreChat, etc.) can point directly
    # at AutoBot without any path rewriting.
    try:
        from api.openai_compat import router as openai_compat_router

        app.include_router(openai_compat_router, prefix="/v1")
        logger.info("✅ Registered OpenAI-compat router at /v1")
    except Exception as e:
        logger.warning("⚠️ Failed to register OpenAI-compat router: %s", e)

    # Issue #6591: Anthropic-compatible /v1/messages endpoint so Anthropic-SDK
    # consumers can point base_url at AutoBot without changing integration code.
    try:
        from api.anthropic_compat import router as anthropic_compat_router

        app.include_router(anthropic_compat_router, prefix="/v1")
        logger.info("✅ Registered Anthropic-compat router at /v1")
    except Exception as e:
        logger.warning("⚠️ Failed to register Anthropic-compat router: %s", e)

    logger.info("✅ API routes configured with optional AI Stack integration")


def _mount_static_files(app: FastAPI) -> None:
    """
    Mount static files directory if it exists.

    Issue #665: Extracted from create_fastapi_app to reduce function length.

    Args:
        app: FastAPI application instance
    """
    try:
        static_dir = Path("static")
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory="static"), name="static")
            logger.info("Static files mounted from static")
        else:
            logger.info("No static directory found, skipping static file mounting")
    except Exception as e:
        logger.warning("Could not mount static files: %s", e)


class AppFactory:
    """Application factory for creating FastAPI instances with comprehensive configuration"""

    def __init__(self):
        """Initialize app factory with logger instance."""
        self.logger = get_logger(__name__)

    @staticmethod
    def create_fastapi_app(
        title: str = "AutoBot - Distributed Autonomous Agent",
        description: str = "AI-powered autonomous Linux administration with distributed VMs",
        version: str = "1.5.0",
        allow_origins: List[str] | None = None,
    ) -> FastAPI:
        """
        Create and configure FastAPI application with optimal performance settings.

        Issue #665: Refactored to use _register_routers and _mount_static_files helpers.

        Args:
            title: Application title
            description: Application description
            version: Application version
            allow_origins: List of allowed CORS origins (default: load from config)

        Returns:
            FastAPI: Configured FastAPI application instance
        """
        app = FastAPI(
            title=title,
            description=description,
            version=version,
            lifespan=create_lifespan_manager(),
            redoc_url=None,
        )

        # Issue #697: Initialize OpenTelemetry tracing before middleware
        init_tracing(service_name="autobot-backend")
        instrument_fastapi(app)

        # Issue #1733: Global exception handler — prevent stack traces in responses
        _register_exception_handlers(app)

        configure_middleware(app, allow_origins=allow_origins)
        register_root_endpoints(app)

        # Issue #665: Use helpers for router registration and static files
        _register_routers(app)
        _mount_static_files(app)

        logger.info("✅ FastAPI application configured successfully")
        return app


def create_app(**kwargs) -> FastAPI:
    """
    Factory function to create the FastAPI application

    Args:
        **kwargs: Arguments passed to AppFactory.create_fastapi_app()

    Returns:
        FastAPI: Configured FastAPI application instance

    Example:
        ```python
        app = create_app()
        app = create_app(title="My App", version="2.0.0")
        ```
    """
    factory = AppFactory()
    return factory.create_fastapi_app(**kwargs)


# For direct usage in main.py or testing
if __name__ == "__main__":
    logger.info("✅ AutoBot Backend application ready")
