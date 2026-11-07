# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Main Entry Point

This is the simplified main entry point that uses the Application Factory Pattern
to create and configure the FastAPI application. The actual application logic
has been moved to backend/app_factory.py for better modularity.
"""

import sys
from pathlib import Path

import uvicorn

# #14518: the first-party imports below carried a stale ``backend.`` package
# prefix -- no ``backend`` package exists -- and autobot-backend was never on
# sys.path, so this script raised ModuleNotFoundError on its own import block
# before doing any work. Add the directory the way the other operator entry
# points in this tree do (#14129).
# A backend tool (#18289): it also puts the repository root on the path (for `autobot_shared`), so it
# runs from any directory with no PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

# Import the application factory
from app_factory import create_app  # noqa: E402

from config import config as global_config_manager  # noqa: E402

# Configure logging using centralized logging manager
# #14518: ``utils.logging_manager`` does not exist under autobot-backend either;
# get_backend_logger/setup_logging live in autobot_shared.logging_manager.
from autobot_shared.logging_manager import get_backend_logger, setup_logging  # noqa: E402

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
