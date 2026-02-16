# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

# Add the project root to Python path for absolute imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.constants.network_constants import (  # noqa: F401 - used in docstring example
    NetworkConstants,
)
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Issue #697: OpenTelemetry distributed tracing
from autobot_shared.tracing import init_tracing, instrument_fastapi

# Import initialization modules
from backend.initialization import (
    configure_middleware,
    create_lifespan_manager,
    load_core_routers,
    load_optional_routers,
    register_root_endpoints,
)

# Store logger for app usage
logger = logging.getLogger(__name__)


def _register_routers(app: FastAPI) -> None:
    """
    Register core and optional routers with the FastAPI app.

    Issue #665: Extracted from create_fastapi_app to reduce function length.

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
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def create_fastapi_app(
        title: str = "AutoBot - Distributed Autonomous Agent",
        description: str = "AI-powered autonomous Linux administration with distributed VMs",
        version: str = "1.5.0",
        allow_origins: Optional[List[str]] = None,
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


# Create app instance for uvicorn
app = create_app()

# For direct usage in main.py or testing
if __name__ == "__main__":
    logger.info("✅ AutoBot Backend application ready")
