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
import logging
from backend.app_factory import create_app

# Configure logging for main entry point
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create the consolidated FastAPI application instance
logger.info("🚀 Initializing AutoBot Backend with consolidated factory...")
app = create_app()
logger.info("✅ AutoBot Backend application ready")

if __name__ == "__main__":
    import uvicorn

    logger.info("🌟 Starting AutoBot Backend in standalone mode...")

    # Get configuration from environment with intelligent defaults
    host = os.getenv("AUTOBOT_BACKEND_HOST", "0.0.0.0")  # Use 0.0.0.0 for network access
    port = int(os.getenv("AUTOBOT_BACKEND_PORT", "8001"))

    # Determine if we're in development mode
    dev_mode = os.getenv("AUTOBOT_DEV_MODE", "false").lower() == "true"
    reload = dev_mode or "--reload" in sys.argv

    # Log configuration
    logger.info(f"📡 Host: {host}")
    logger.info(f"🔌 Port: {port}")
    logger.info(f"🔄 Reload: {reload}")
    logger.info(f"🛠️  Dev Mode: {dev_mode}")

    try:
        # Run the server with optimized settings
        uvicorn.run(
            "backend.main:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info",
            access_log=True,
            workers=1 if reload else None,  # Single worker in dev mode, auto-detect in production
            loop="auto",  # Use best available event loop
            http="auto",  # Use best available HTTP implementation
        )
    except KeyboardInterrupt:
        logger.info("👋 AutoBot Backend shutdown by user")
    except Exception as e:
        logger.error(f"❌ AutoBot Backend failed to start: {e}")
        sys.exit(1)