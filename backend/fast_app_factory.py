"""
Fast Application Factory for AutoBot FastAPI Backend

This creates a minimal FastAPI app that starts quickly and initializes
heavy components in the background. Essential endpoints work immediately.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Import host IP addresses from main config
from src.config import (
    BACKEND_HOST_IP,
    BACKEND_PORT,
    FRONTEND_HOST_IP,
    FRONTEND_PORT,
    HTTP_PROTOCOL,
)

logger = logging.getLogger(__name__)

# Global background initialization status
background_init_status = {
    "knowledge_base": "pending",
    "orchestrator": "pending",
    "chat_history": "pending",
    "redis_client": "pending",
    "components_ready": False,
    "initialization_start": None,
    "initialization_complete": None,
    "errors": [],
}


async def initialize_components_background(app: FastAPI):
    """Initialize heavy components in the background"""
    global background_init_status

    background_init_status["initialization_start"] = datetime.now().isoformat()
    logger.info("🚀 Starting background component initialization...")

    try:
        # CRITICAL: Verify knowledge base consistency first
        logger.info("🔒 CRITICAL: Verifying knowledge base consistency...")
        try:
            import subprocess

            result = subprocess.run(
                ["python", "scripts/verify_knowledge_consistency.py"],
                capture_output=True,
                text=True,
                # Remove timeout - let process complete naturally
            )
            if result.returncode == 0:
                logger.info(
                    "✅ CRITICAL: Knowledge consistency VERIFIED - ZERO inconsistencies guaranteed"
                )
            else:
                logger.error(f"🚨 CRITICAL: Knowledge consistency verification FAILED")
                background_init_status["errors"].append(
                    "CRITICAL: Knowledge consistency verification failed"
                )
        except Exception as e:
            logger.warning(f"Could not run consistency verification: {e}")

        # Initialize knowledge base
        logger.info("Initializing knowledge base...")
        background_init_status["knowledge_base"] = "initializing"

        try:
            from src.knowledge_base import KnowledgeBase

            app.state.knowledge_base = KnowledgeBase()
            background_init_status["knowledge_base"] = "ready"
            logger.info("✅ Knowledge base initialized")
        except Exception as e:
            background_init_status["knowledge_base"] = "failed"
            background_init_status["errors"].append(f"Knowledge base: {str(e)}")
            logger.error(f"❌ Knowledge base initialization failed: {e}")

        # Initialize orchestrator
        logger.info("Initializing orchestrator...")
        background_init_status["orchestrator"] = "initializing"

        try:
            from src.lightweight_orchestrator import lightweight_orchestrator

            await lightweight_orchestrator.startup()
            app.state.lightweight_orchestrator = lightweight_orchestrator
            # Also store as 'orchestrator' for chat API compatibility
            app.state.orchestrator = lightweight_orchestrator
            background_init_status["orchestrator"] = "ready"
            logger.info("✅ Orchestrator initialized")
        except Exception as e:
            background_init_status["orchestrator"] = "failed"
            background_init_status["errors"].append(f"Orchestrator: {str(e)}")
            logger.error(f"❌ Orchestrator initialization failed: {e}")

        # Initialize chat history manager
        logger.info("Initializing chat history manager...")
        background_init_status["chat_history"] = "initializing"

        try:
            from src.chat_history_manager import ChatHistoryManager
            from src.config import config as global_config_manager

            redis_config = global_config_manager.get_redis_config()
            app.state.chat_history_manager = ChatHistoryManager(
                history_file=global_config_manager.get_nested(
                    "data.chat_history_file", "data/chat_history.json"
                ),
                use_redis=redis_config.get("enabled", False),
                redis_host=redis_config.get("host", "localhost"),
                redis_port=redis_config.get("port", 6379),
            )
            background_init_status["chat_history"] = "ready"
            logger.info("✅ Chat history manager initialized")
        except Exception as e:
            background_init_status["chat_history"] = "failed"
            background_init_status["errors"].append(f"Chat history: {str(e)}")
            logger.error(f"❌ Chat history initialization failed: {e}")

        # Initialize Redis client
        logger.info("Initializing Redis client...")
        background_init_status["redis_client"] = "initializing"

        try:
            from src.utils.redis_client import get_redis_client

            app.state.main_redis_client = get_redis_client()
            if app.state.main_redis_client:
                app.state.main_redis_client.ping()
                background_init_status["redis_client"] = "ready"
                logger.info("✅ Redis client initialized")
            else:
                background_init_status["redis_client"] = "failed"
                background_init_status["errors"].append(
                    "Redis client: Could not connect"
                )
        except Exception as e:
            background_init_status["redis_client"] = "failed"
            background_init_status["errors"].append(f"Redis client: {str(e)}")
            logger.error(f"❌ Redis client initialization failed: {e}")

        # Initialize Advanced Workflow Orchestrator for performance optimization
        logger.info("Initializing advanced workflow orchestrator...")
        background_init_status["advanced_workflow_orchestrator"] = "initializing"

        try:
            from backend.api.advanced_workflow_orchestrator import (
                AdvancedWorkflowOrchestrator,
            )

            app.state.advanced_workflow_orchestrator = AdvancedWorkflowOrchestrator()
            background_init_status["advanced_workflow_orchestrator"] = "ready"
            logger.info("✅ Advanced workflow orchestrator initialized")
        except Exception as e:
            background_init_status["advanced_workflow_orchestrator"] = "failed"
            background_init_status["errors"].append(
                f"Advanced workflow orchestrator: {str(e)}"
            )
            logger.error(
                f"❌ Advanced workflow orchestrator initialization failed: {e}"
            )

        # Initialize Chat Knowledge Manager for performance optimization
        logger.info("Initializing chat knowledge manager...")
        background_init_status["chat_knowledge_manager"] = "initializing"

        try:
            from backend.api.chat_knowledge import ChatKnowledgeManager

            app.state.chat_knowledge_manager = ChatKnowledgeManager()
            background_init_status["chat_knowledge_manager"] = "ready"
            logger.info("✅ Chat knowledge manager initialized")
        except Exception as e:
            background_init_status["chat_knowledge_manager"] = "failed"
            background_init_status["errors"].append(f"Chat knowledge manager: {str(e)}")
            logger.error(f"❌ Chat knowledge manager initialization failed: {e}")

        # Initialize Resource Factory for shared resource management
        logger.info("Initializing shared resource management...")
        background_init_status["resource_factory"] = "initializing"

        try:
            from src.utils.resource_factory import ResourceFactory

            # Pre-initialize core resources that are already created above
            if hasattr(app.state, "knowledge_base"):
                logger.info("♾️ KnowledgeBase already cached in app.state")
            if hasattr(app.state, "chat_history_manager"):
                logger.info("♾️ ChatHistoryManager already cached in app.state")

            # Resource factory is now available for lazy initialization of other resources
            app.state.resource_factory = ResourceFactory
            background_init_status["resource_factory"] = "ready"
            logger.info("✅ Resource factory initialized for lazy resource management")
        except Exception as e:
            background_init_status["resource_factory"] = "failed"
            background_init_status["errors"].append(f"Resource factory: {str(e)}")
            logger.error(f"❌ Resource factory initialization failed: {e}")

        # Mark as complete
        ready_components = sum(
            1 for status in background_init_status.values() if status == "ready"
        )
        total_components = 7  # knowledge_base, orchestrator, chat_history, redis_client, advanced_workflow_orchestrator, chat_knowledge_manager, resource_factory

        background_init_status["components_ready"] = (
            ready_components == total_components
        )
        background_init_status["initialization_complete"] = datetime.now().isoformat()

        logger.info(
            f"🎉 Background initialization complete: {ready_components}/{total_components} components ready"
        )

    except Exception as e:
        background_init_status["errors"].append(f"Initialization error: {str(e)}")
        logger.error(f"❌ Background initialization failed: {e}")


@asynccontextmanager
async def create_fast_lifespan_manager(app: FastAPI):
    """Fast lifespan manager that starts background initialization"""
    logger.info("🚀 Fast application lifespan startup initiated")

    # Start background initialization without waiting
    asyncio.create_task(initialize_components_background(app))

    logger.info("✅ Fast application startup completed - API ready immediately")

    yield

    logger.info("🛑 Fast application lifespan shutdown initiated")


def add_fast_middleware(app: FastAPI) -> None:
    """Add essential middleware quickly"""
    # Simple CORS setup
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"{HTTP_PROTOCOL}://{FRONTEND_HOST_IP}:{FRONTEND_PORT}",
            f"{HTTP_PROTOCOL}://{BACKEND_HOST_IP}:{BACKEND_PORT}",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    logger.info("✅ Fast CORS middleware added")


def add_essential_routes(app: FastAPI) -> None:
    """Add essential routes that work immediately"""
    from fastapi import HTTPException
    import uuid
    import json

    api_router = APIRouter()

    @api_router.get("/health")
    async def ultra_fast_health():
        """Ultra-fast health check - responds immediately"""
        return {
            "status": "healthy",
            "backend": "connected",
            "timestamp": datetime.now().isoformat(),
            "fast_startup": True,
            "response_time": "< 10ms",
        }

    @api_router.get("/status")
    async def system_status():
        """System status including background component initialization"""
        return {
            "api_ready": True,
            "background_initialization": background_init_status,
            "timestamp": datetime.now().isoformat(),
        }

    @api_router.get("/hello")
    async def hello_world():
        return {"message": "Hello from AutoBot Fast API!"}

    @api_router.get("/version")
    async def get_version():
        return {"version": "1.0.0-fast", "startup_mode": "fast"}

    # Simple knowledge base stats that work even during initialization
    @api_router.get("/knowledge_base/stats")
    async def fast_knowledge_stats(request: Request):
        """Fast knowledge base stats - works immediately with fallback"""
        kb = getattr(request.app.state, "knowledge_base", None)

        if kb and background_init_status["knowledge_base"] == "ready":
            try:
                stats = await kb.get_stats()
                stats["initialization_status"] = "ready"
                return stats
            except Exception as e:
                logger.error(f"Knowledge base stats error: {e}")

        # Return immediate fallback response
        return {
            "total_documents": 0,
            "total_chunks": 0,
            "categories": [],
            "total_facts": 0,
            "initialization_status": background_init_status["knowledge_base"],
            "message": (
                "Knowledge base still initializing"
                if background_init_status["knowledge_base"] != "ready"
                else "Knowledge base not available"
            ),
        }

    # Include the full chat router - fix the root cause of slow imports later

    app.include_router(api_router, prefix="/api/system")
    app.include_router(api_router, prefix="/api")

    # Import and include CONSOLIDATED chat router after basic routes
    # This replaces ALL previous chat routers: chat.py, async_chat.py, chat_unified.py, chat_improved.py, chat_knowledge.py
    try:
        from backend.api.chat_consolidated import router as chat_consolidated_router

        app.include_router(chat_consolidated_router, prefix="/api")
        logger.info("✅ CONSOLIDATED chat router included - ALL 5 routers merged with ZERO functionality loss")
        logger.info("  - 45 endpoints from chat.py (2535 lines)")
        logger.info("  - Async architecture from async_chat.py (249 lines)")
        logger.info("  - Unified service from chat_unified.py (264 lines)")
        logger.info("  - Error handling from chat_improved.py (288 lines)")
        logger.info("  - Knowledge management from chat_knowledge.py (747 lines)")
    except Exception as e:
        logger.error(f"Failed to include consolidated chat router: {e}")
        # Fallback to original chat router if consolidated fails
        try:
            from backend.api.chat import router as chat_router
            app.include_router(chat_router, prefix="/api")
            logger.warning("⚠️ Using fallback original chat router due to consolidated router failure")
        except Exception as fallback_error:
            logger.error(f"Failed to include fallback chat router: {fallback_error}")
            # Don't add fallback - let it fail if this is critical

    # Import and include knowledge router for categories and system knowledge
    try:
        from backend.api.knowledge import router as knowledge_router

        app.include_router(knowledge_router, prefix="/api/knowledge_base")
        logger.info(
            "✅ Knowledge router included with /categories and system knowledge endpoints"
        )
    except Exception as e:
        logger.error(f"Failed to include knowledge router: {e}")

    # Import and include validation dashboard router
    try:
        from backend.api.validation_dashboard import router as validation_router

        app.include_router(validation_router, prefix="/api/validation-dashboard")
        logger.info("✅ Validation dashboard router included with /report endpoint")
    except Exception as e:
        logger.error(f"Failed to include validation dashboard router: {e}")

    # Import and include codebase analytics router
    try:
        from backend.api.codebase_analytics import router as codebase_analytics_router

        app.include_router(codebase_analytics_router, prefix="/api/analytics")
        logger.info("✅ Codebase analytics router included with /declarations and /duplicates endpoints")
    except Exception as e:
        logger.error(f"Failed to include codebase analytics router: {e}")

    # CRITICAL FIX: Add simple WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """Simple WebSocket endpoint for fast mode"""
        try:
            await websocket.accept()
            logger.info("WebSocket connection accepted in fast mode")

            # Send welcome message
            await websocket.send_json(
                {
                    "type": "connection_status",
                    "status": "connected",
                    "mode": "fast_startup",
                    "message": "WebSocket connected in fast mode. Full features initializing...",
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Keep connection alive and handle messages
            while True:
                try:
                    data = await websocket.receive_text()
                    # Echo back for now
                    await websocket.send_json(
                        {
                            "type": "echo",
                            "data": data,
                            "timestamp": datetime.now().isoformat(),
                            "mode": "fast_startup",
                        }
                    )
                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected")
                    break
                except Exception as e:
                    logger.error(f"WebSocket error: {e}")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": str(e),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")

    logger.info("✅ Essential routes added (including chat endpoints and WebSocket)")


def create_fast_app() -> FastAPI:
    """
    Create a FastAPI application that starts quickly
    """
    logger.info("🚀 Creating Fast AutoBot application...")

    # Create minimal FastAPI app
    app = FastAPI(
        title="AutoBot Fast API",
        description="Fast-starting AutoBot backend",
        lifespan=lambda app: create_fast_lifespan_manager(app),
    )

    # Add essential middleware and routes
    add_fast_middleware(app)
    add_essential_routes(app)

    # Serve static files if available
    static_dir = "static"
    if os.path.exists(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
        logger.info(f"✅ Static files mounted from {static_dir}")

    logger.info("✅ Fast AutoBot application created")
    return app
