"""
Fast AutoBot Backend Main Entry Point

Creates a minimal FastAPI app that responds immediately while
heavy components initialize in the background.
"""

from backend.fast_app_factory import create_fast_app

# Create the fast FastAPI application instance
app = create_fast_app()

if __name__ == "__main__":
    import os
    import uvicorn

    # Get configuration from environment
    host = os.getenv("AUTOBOT_BACKEND_HOST", "127.0.0.3")
    port = int(os.getenv("AUTOBOT_BACKEND_PORT", "8001"))

    # Run the fast server
    uvicorn.run(
        "backend.fast_main:app", host=host, port=port, reload=False, log_level="info"
    )
