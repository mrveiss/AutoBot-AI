# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Main Entry Point

This is the simplified main entry point that uses the Application Factory Pattern
to create and configure the FastAPI application. The actual application logic
has been moved to backend/app_factory.py for better modularity.
"""

import uvicorn

# Import the application factory
from backend.app_factory import create_app
from config import config as global_config_manager

# Configure logging using centralized logging manager
from utils.logging_manager import get_backend_logger, setup_logging

setup_logging()
logger = get_backend_logger(__name__)

# Create the FastAPI application at module level for ASGI server
app = create_app()


def main():
    """Main function to start the AutoBot backend server."""
    logger.info("Starting AutoBot backend server...")

    # Get server configuration from centralized config
    backend_config = global_config_manager.get_backend_config()
    host = backend_config.get("server_host", "0.0.0.0")
    port = backend_config.get("server_port", 8001)

    # Get additional server settings
    reload = backend_config.get("reload", False)
    log_level = backend_config.get("log_level", "info")

    logger.info("Starting server on %s:%s", host, port)
    logger.info("Reload enabled: %s", reload)
    logger.info("Log level: %s", log_level)

    # Start the server
    uvicorn.run(app, host=host, port=port, reload=reload, log_level=log_level)


if __name__ == "__main__":
    main()
