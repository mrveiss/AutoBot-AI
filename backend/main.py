"""
AutoBot Backend Main Entry Point

This module serves as the main entry point for the AutoBot FastAPI backend application.
It creates the app instance using the application factory pattern.
"""

from backend.app_factory import create_app

# Create the FastAPI application instance
app = create_app()

if __name__ == "__main__":
    import os

    import uvicorn

    # Get configuration from environment
    host = os.getenv("AUTOBOT_BACKEND_HOST", "127.0.0.3")
    port = int(os.getenv("AUTOBOT_BACKEND_PORT", "8001"))

    # Run the server
    uvicorn.run("backend.main:app", host=host, port=port, reload=True, log_level="info")
