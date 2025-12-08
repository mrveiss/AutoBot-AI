# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced FastAPI Application Factory with AI Stack Integration

This module extends the existing app factory with comprehensive AI Stack
integration capabilities, including RAG, enhanced chat, knowledge extraction,
and multi-agent coordination.

Refactored to reduce coupling by:
- Using centralized router loading from backend.initialization.routers
- Extracting AI Stack initialization to backend.initialization.ai_stack_init
- Extracting background tasks to backend.initialization.background_tasks
- Extracting health endpoints to backend.initialization.health_endpoints
"""

import asyncio
import os
import time
import traceback
from contextlib import asynccontextmanager
from enum import Enum
from typing import List, Union

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Import centralized router loading
from backend.initialization.routers import load_core_routers, load_optional_routers

# Import AI Stack integration routers (not in core/optional loaders)
from backend.api.ai_stack_integration import router as ai_stack_router
from backend.api.chat_enhanced import router as chat_enhanced_router
from backend.api.knowledge_enhanced import router as knowledge_enhanced_router
from backend.api.knowledge_advanced_rag import router as knowledge_advanced_rag_router
from backend.api.websockets import router as websocket_router

# Import initialization modules
from backend.initialization.background_tasks import enhanced_background_init
from backend.initialization.health_endpoints import register_health_endpoints

# Import AI Stack client cleanup
from backend.services.ai_stack_client import close_ai_stack_client

# Import API registry
from src.api_registry import APIRegistry

# Import logging
from src.utils.logging_manager import get_logger

# Get centralized logger
logger = get_logger(__name__, "backend")

# Lock for thread-safe access to background_init_status
_init_status_lock = asyncio.Lock()

# Enhanced initialization tracking including AI Stack and distributed tracing
background_init_status = {
    "redis_pools": "pending",
    "knowledge_base": "pending",
    "chat_workflow": "pending",
    "llm_sync": "pending",
    "ai_stack": "pending",
    "ai_stack_agents": "pending",
    "distributed_tracing": "pending",
    "errors": [],
}


async def update_init_status(key: str, value: str) -> None:
    """Thread-safe update of background_init_status."""
    async with _init_status_lock:
        background_init_status[key] = value


async def append_init_error(error: str) -> None:
    """Thread-safe append to background_init_status errors."""
    async with _init_status_lock:
        background_init_status["errors"].append(error)


async def get_init_status(key: str = None) -> dict:
    """Thread-safe read of background_init_status."""
    async with _init_status_lock:
        if key is None:
            return dict(background_init_status)  # Return copy
        return background_init_status.get(key)


# Initialization functions moved to backend.initialization modules
# - AI Stack init: backend.initialization.ai_stack_init
# - Background tasks: backend.initialization.background_tasks
# - Health endpoints: backend.initialization.health_endpoints


@asynccontextmanager
async def enhanced_lifespan(app: FastAPI):
    """Enhanced application lifespan with AI Stack cleanup."""
    # Startup
    logger.info("🚀 Enhanced AutoBot Backend starting up with AI Stack integration...")

    # Start background initialization with status management functions
    asyncio.create_task(
        enhanced_background_init(
            app, update_init_status, append_init_error, get_init_status
        )
    )

    yield

    # Shutdown
    logger.info("🔄 Enhanced AutoBot Backend shutting down...")

    # Cleanup AI Stack client
    try:
        await close_ai_stack_client()
        logger.info("✅ AI Stack client closed successfully")
    except Exception as e:
        logger.error(f"❌ Error closing AI Stack client: {e}")

    # Shutdown distributed tracing
    try:
        # Lazy import to avoid circular dependency
        from backend.services.tracing_service import get_tracing_service

        tracing = get_tracing_service()
        tracing.shutdown()
        logger.info("✅ Distributed tracing shutdown complete")
    except Exception as e:
        logger.error(f"❌ Error shutting down distributed tracing: {e}")

    # REFACTORED: Removed redis_pools cleanup - using centralized Redis client management
    # Redis connections are automatically managed by get_redis_client()
    logger.info(
        "✅ Redis connections managed by centralized client (src.utils.redis_client)"
    )

    logger.info("✅ Enhanced AutoBot Backend shutdown complete")


def create_enhanced_app() -> FastAPI:
    """
    Create enhanced FastAPI application with AI Stack integration.

    This function extends the original create_app with AI Stack capabilities
    while maintaining full backward compatibility.
    """
    # Create FastAPI app with enhanced lifespan
    app = FastAPI(
        title="AutoBot Enhanced Backend API with AI Stack Integration",
        description=(
            "Comprehensive AI-powered automation platform with advanced RAG,"
            "multi-agent coordination, and NPU acceleration"
        ),
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=enhanced_lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add distributed tracing middleware (Issue #57)
    # This adds custom AutoBot attributes to traces created by OpenTelemetry
    try:
        # Lazy import to avoid circular dependency
        from backend.middleware.tracing_middleware import TracingMiddleware

        app.add_middleware(TracingMiddleware, service_name="autobot-backend")
    except Exception as e:
        logger.warning(f"Distributed tracing middleware not available: {e}")

    # NOTE: AuthenticationMiddleware is a utility class, not ASGI middleware
    # It's accessed via auth_middleware singleton and get_current_user dependency
    # Do NOT use app.add_middleware() - it expects ASGI middleware interface

    # Configure enhanced API routes
    configure_enhanced_api_routes(app)

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        """Handle uncaught exceptions with logging and JSON response."""
        logger.error(f"Global exception: {exc}\n{traceback.format_exc()}")
        # Thread-safe access to init status
        ai_stack_status = await get_init_status("ai_stack")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "path": str(request.url.path),
                "timestamp": time.time(),
                "ai_stack_available": ai_stack_status == "ready",
            },
        )

    # Register health endpoints from centralized module
    register_health_endpoints(app, get_init_status)

    # Add static files
    add_static_files(app)

    logger.info("✅ Enhanced FastAPI application configured successfully")
    return app


def configure_enhanced_api_routes(app: FastAPI) -> None:
    """
    Configure all API routes including enhanced AI Stack endpoints.

    Uses centralized router loading from backend.initialization.routers
    to reduce coupling and improve maintainability.
    """
    # Create API registry for tracking endpoints
    api_registry = APIRegistry()

    # Create main API router
    api_router = APIRouter()

    # Load core routers from centralized loader
    core_routers_config = load_core_routers()

    # Enhanced AI Stack routers (not in core loader)
    ai_enhanced_routers_config = [
        (ai_stack_router, "/ai-stack", ["ai-stack"], "ai_stack_integration"),
        (chat_enhanced_router, "/chat/enhanced", ["chat-enhanced"], "chat_enhanced"),
        (
            knowledge_enhanced_router,
            "/knowledge/enhanced",
            ["knowledge-enhanced"],
            "knowledge_enhanced",
        ),
        (
            knowledge_advanced_rag_router,
            "/knowledge_base/rag",
            ["knowledge-advanced-rag"],
            "knowledge_advanced_rag",
        ),
    ]

    # Register core routers
    for router, prefix, tags, name in core_routers_config:
        try:
            router_tags: List[Union[str, Enum]] = list(tags) if tags else []
            api_router.include_router(router, prefix=prefix, tags=router_tags)
            api_registry.register_router(name, router, f"/api{prefix}")
            logger.info(f"✅ Registered core router: {name} at /api{prefix}")
        except Exception as e:
            logger.error(f"❌ Failed to register core router {name}: {e}")

    # Register AI Stack enhanced routers
    for router, prefix, tags, name in ai_enhanced_routers_config:
        try:
            router_tags: List[Union[str, Enum]] = list(tags) if tags else []
            api_router.include_router(router, prefix=prefix, tags=router_tags)
            api_registry.register_router(name, router, f"/api{prefix}")
            logger.info(f"✅ Registered AI Stack router: {name} at /api{prefix}")
        except Exception as e:
            logger.error(f"❌ Failed to register AI Stack router {name}: {e}")

    # Load optional routers from centralized loader
    optional_routers = load_optional_routers()

    # Register optional routers
    for router, prefix, tags, name in optional_routers:
        try:
            router_tags: List[Union[str, Enum]] = list(tags) if tags else []
            api_router.include_router(router, prefix=prefix, tags=router_tags)
            api_registry.register_router(name, router, f"/api{prefix}")
            logger.info(
                f"✅ Successfully registered optional router: {name} at /api{prefix}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to register optional router {name}: {e}")

    # Register utility endpoints
    api_registry.register_router("utility", api_router, "/api")

    # Include the API router in the main app
    app.include_router(api_router, prefix="/api")

    # Include WebSocket router (not in core/optional loaders)
    app.include_router(websocket_router)

    logger.info("✅ Enhanced API routes configured with AI Stack integration")


def add_static_files(app: FastAPI) -> None:
    """Mount static file serving."""
    static_dir = "static"
    if os.path.exists(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
        logger.info(f"Static files mounted from {static_dir}")


# Backward compatibility: create_app function
def create_app() -> FastAPI:
    """Create standard app (backward compatibility)."""
    return create_enhanced_app()


# Export the factory functions
__all__ = [
    "create_app",
    "create_enhanced_app",
]
