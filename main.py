"""
AutoBot Main Entry Point

This is the simplified main entry point that uses the Application Factory Pattern
to create and configure the FastAPI application. The actual application logic
has been moved to backend/app_factory.py for better modularity.
"""

import os
import uvicorn
import logging
import logging.config

# Configure logging at the very beginning
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/autobot_backend.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import the application factory
from backend.app_factory import create_app
from src.config import config as global_config_manager

# Create the FastAPI application at module level for ASGI server
app = create_app()

def main():
    """Main function to start the AutoBot backend server."""
    logger.info("Starting AutoBot backend server...")
    
    # Use the module-level app
    global app
    
    # Get server configuration from centralized config
    backend_config = global_config_manager.get_backend_config()
    host = backend_config.get('server_host', '0.0.0.0')
    port = backend_config.get('server_port', 8001)
    
    # Get additional server settings
    reload = backend_config.get('reload', False)
    log_level = backend_config.get('log_level', 'info')
    
    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"Reload enabled: {reload}")
    logger.info(f"Log level: {log_level}")
    
    # Start the server
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level=log_level
    )

if __name__ == "__main__":
    main()
