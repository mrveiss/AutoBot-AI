# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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

from autobot_shared.ssot_config import config

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# CRITICAL: Disable HuggingFace tokenizers parallelism BEFORE any imports
# This prevents deadlocks when using run_in_executor() with forked processes
# See: https://github.com/huggingface/tokenizers/issues/1062
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # ssot-config-exempt: runtime env mutation for HuggingFace

from app_factory import create_app
from autobot_shared.logging_manager import get_logger

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
    host = config.vm.main  # Bind to all interfaces for network access
    port = config.port.backend

    # Determine if we're in development mode
    dev_mode = bool(config.misc.dev_mode)
    reload = dev_mode or "--reload" in sys.argv

    # TLS Configuration - Issue #725, #164
    tls_enabled = config.tls.backend_tls_enabled
    ssl_keyfile = None
    ssl_certfile = None

    if tls_enabled:
        # Check for explicit cert/key paths first (set by SLM enable-tls playbook)
        ssl_certfile = config.misc.tls_cert_path or None
        ssl_keyfile = config.misc.tls_key_path or None

        # Fallback to cert_dir + main-host pattern for legacy compatibility
        if not ssl_certfile or not ssl_keyfile:
            cert_dir = config.tls.cert_dir
            project_root = Path(__file__).parent.parent
            ssl_keyfile = str(project_root / cert_dir / "main-host" / "server-key.pem")
            ssl_certfile = str(project_root / cert_dir / "main-host" / "server-cert.pem")

        # Override port to TLS port when enabled
        port = config.tls.backend_tls_port
        logger.info("🔒 TLS enabled - using HTTPS on port %s", port)
        logger.info("🔒 TLS cert: %s", ssl_certfile)
        logger.info("🔒 TLS key: %s", ssl_keyfile)  # codeql[py/clear-text-logging-sensitive-data]

    # Log configuration
    logger.info("📡 Host: %s", host)
    logger.info("🔌 Port: %s", port)
    logger.info("🔄 Reload: %s", reload)
    logger.info("🛠️  Dev Mode: %s", dev_mode)
    logger.info("🔐 TLS Enabled: %s", tls_enabled)

    try:
        # Build uvicorn config
        uvicorn_config = {
            "app": "main:app",
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
