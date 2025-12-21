# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Consolidated AutoBot Backend Main Entry Point

This module serves as the main entry point for the AutoBot FastAPI backend application.
It creates the app instance using the consolidated application factory pattern with
the best features from all previous implementations:
- Fast startup with background initialization
- Redis timeout fixes
- Comprehensive error handling
- Full router support
- Production-ready configuration
"""

import os
import sys

from backend.app_factory import create_app
from src.constants.network_constants import NetworkConstants
from src.utils.logging_manager import get_logger

# Get centralized logger (respects AUTOBOT_LOG_LEVEL environment variable)
logger = get_logger(__name__, "backend")
logger.info("📊 Log level configured via centralized logging manager")

# Create the consolidated FastAPI application instance
logger.info("🚀 Initializing AutoBot Backend with consolidated factory...")
app = create_app()
logger.info("✅ AutoBot Backend application ready")

if __name__ == "__main__":
    import uvicorn

    logger.info("🌟 Starting AutoBot Backend in standalone mode...")

    # Get configuration from environment with intelligent defaults
    host = os.getenv(
        "AUTOBOT_BACKEND_HOST", NetworkConstants.BIND_ALL_INTERFACES
    )  # Bind to all interfaces for network access
    port = int(os.getenv("AUTOBOT_BACKEND_PORT", str(NetworkConstants.BACKEND_PORT)))

    # Determine if we're in development mode
    dev_mode = os.getenv("AUTOBOT_DEV_MODE", "false").lower() == "true"
    reload = dev_mode or "--reload" in sys.argv

    # Log configuration
    logger.info("📡 Host: %s", host)
    logger.info("🔌 Port: %s", port)
    logger.info("🔄 Reload: %s", reload)
    logger.info("🛠️  Dev Mode: %s", dev_mode)

    try:
        # Run the server with optimized settings
        uvicorn.run(
            "backend.main:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info",
            access_log=True,
            workers=(
                1 if reload else None
            ),  # Single worker in dev mode, auto-detect in production
            loop="auto",  # Use best available event loop
            http="auto",  # Use best available HTTP implementation
        )
    except KeyboardInterrupt:
        logger.info("👋 AutoBot Backend shutdown by user")
    except Exception as e:
        logger.error("❌ AutoBot Backend failed to start: %s", e)
        sys.exit(1)
