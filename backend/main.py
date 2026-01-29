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
from pathlib import Path

# Load environment variables from .env file BEFORE any other imports
# This ensures AUTOBOT_SECRETS_KEY is available for SecretsService
from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# CRITICAL: Disable HuggingFace tokenizers parallelism BEFORE any imports
# This prevents deadlocks when using run_in_executor() with forked processes
# See: https://github.com/huggingface/tokenizers/issues/1062
os.environ["TOKENIZERS_PARALLELISM"] = "false"

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

    # TLS Configuration - Issue #725
    tls_enabled = os.getenv("AUTOBOT_BACKEND_TLS_ENABLED", "false").lower() == "true"
    ssl_keyfile = None
    ssl_certfile = None

    if tls_enabled:
        cert_dir = os.getenv("AUTOBOT_TLS_CERT_DIR", "certs")
        project_root = Path(__file__).parent.parent
        ssl_keyfile = str(project_root / cert_dir / "main-host" / "server-key.pem")
        ssl_certfile = str(project_root / cert_dir / "main-host" / "server-cert.pem")
        # Override port to TLS port when enabled
        port = int(os.getenv("AUTOBOT_BACKEND_TLS_PORT", "8443"))
        logger.info("🔒 TLS enabled - using HTTPS on port %s", port)

    # Log configuration
    logger.info("📡 Host: %s", host)
    logger.info("🔌 Port: %s", port)
    logger.info("🔄 Reload: %s", reload)
    logger.info("🛠️  Dev Mode: %s", dev_mode)
    logger.info("🔐 TLS Enabled: %s", tls_enabled)

    try:
        # Build uvicorn config
        uvicorn_config = {
            "app": "backend.main:app",
            "host": host,
            "port": port,
            "reload": reload,
            "log_level": "info",
            "access_log": True,
            "workers": 1 if reload else None,  # Single worker in dev mode
            "loop": "auto",  # Use best available event loop
            "http": "auto",  # Use best available HTTP implementation
        }

        # Add TLS configuration if enabled
        if tls_enabled and ssl_keyfile and ssl_certfile:
            uvicorn_config["ssl_keyfile"] = ssl_keyfile
            uvicorn_config["ssl_certfile"] = ssl_certfile

        # Run the server with optimized settings
        uvicorn.run(**uvicorn_config)
    except KeyboardInterrupt:
        logger.info("👋 AutoBot Backend shutdown by user")
    except Exception as e:
        logger.error("❌ AutoBot Backend failed to start: %s", e)
        sys.exit(1)
