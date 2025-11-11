"""
Enhanced FastAPI Application Factory with AI Stack Integration

This module extends the existing app factory with comprehensive AI Stack
integration capabilities, including RAG, enhanced chat, knowledge extraction,
and multi-agent coordination.
"""

import asyncio
import logging
import os
import time
import traceback
from contextlib import asynccontextmanager
from enum import Enum
from typing import Dict, List, Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.agent import router as agent_router
from backend.api.agent_config import router as agent_config_router

# Import new AI Stack integration routers
from backend.api.ai_stack_integration import router as ai_stack_router

# Import original API routers
from backend.api.chat import router as chat_router
from backend.api.chat_enhanced import router as chat_enhanced_router
from backend.api.developer import router as developer_router
from backend.api.embeddings import router as embeddings_router
from backend.api.error_monitoring import router as error_monitoring_router
from backend.api.files import router as files_router
from backend.api.intelligent_agent import router as intelligent_agent_router
from backend.api.kb_librarian import router as kb_librarian_router
from backend.api.knowledge import router as knowledge_router
from backend.api.knowledge_advanced_rag import router as knowledge_advanced_rag_router
from backend.api.knowledge_enhanced import router as knowledge_enhanced_router
from backend.api.llm import router as llm_router
from backend.api.metrics import router as metrics_router
from backend.api.monitoring import router as monitoring_router
from backend.api.prompts import router as prompts_router
from backend.api.redis import router as redis_router
from backend.api.research_browser import router as research_browser_router
from backend.api.scheduler import router as scheduler_router
from backend.api.secrets import router as secrets_router
from backend.api.security import router as security_router
from backend.api.settings import router as settings_router
from backend.api.system import router as system_router
from backend.api.templates import router as templates_router
from backend.api.terminal import router as terminal_router
from backend.api.voice import router as voice_router
from backend.api.websockets import router as websocket_router
from backend.api.workflow import router as workflow_router
from backend.services.ai_stack_client import close_ai_stack_client, get_ai_stack_client

# Import additional modules
from src.api_registry import APIRegistry
from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Import authentication and security middleware
from src.auth_middleware import AuthenticationMiddleware
from src.chat_workflow_manager import ChatWorkflowManager
from src.constants.network_constants import NetworkConstants
# REFACTORED: Removed deprecated RedisPoolManager import
# from src.redis_pool_manager import RedisPoolManager
# Redis connections now managed centrally via src.utils.redis_client::get_redis_client()
from src.security_layer import SecurityLayer
from src.utils.background_llm_sync import background_llm_sync

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enhanced initialization tracking including AI Stack
background_init_status = {
    "redis_pools": "pending",
    "knowledge_base": "pending",
    "chat_workflow": "pending",
    "llm_sync": "pending",
    "ai_stack": "pending",
    "ai_stack_agents": "pending",
    "errors": [],
}


def log_initialization_step(
    stage: str, message: str, percentage: int = 0, success: bool = True
):
    """Log initialization steps with consistent formatting."""
    icon = "✅" if success else "❌" if percentage == 100 else "🔄"
    logger.info(f"{icon} [{percentage:3d}%] {stage}: {message}")


async def initialize_ai_stack(app: FastAPI) -> None:
    """Initialize AI Stack connection and verify agent availability."""
    try:
        log_initialization_step("AI Stack", "Initializing AI Stack connection...", 0)

        # Test AI Stack connectivity
        ai_client = await get_ai_stack_client()
        health_status = await ai_client.health_check()

        if health_status["status"] == "healthy":
            background_init_status["ai_stack"] = "ready"
            log_initialization_step(
                "AI Stack", "AI Stack connection established", 50, True
            )

            # Test agent availability
            try:
                agents_info = await ai_client.list_available_agents()
                agent_count = len(agents_info.get("agents", []))
                background_init_status["ai_stack_agents"] = "ready"

                # Store agent info in app state for reference
                app.state.ai_stack_agents = agents_info
                app.state.ai_stack_client = ai_client

                log_initialization_step(
                    "AI Stack", f"Verified {agent_count} AI agents available", 100, True
                )

            except Exception as e:
                logger.warning(f"AI Stack agent verification failed: {e}")
                background_init_status["ai_stack_agents"] = "partial"
                background_init_status["errors"].append(f"Agent verification: {str(e)}")

        else:
            background_init_status["ai_stack"] = "degraded"
            background_init_status["errors"].append("AI Stack health check failed")
            log_initialization_step(
                "AI Stack", "AI Stack connection degraded", 100, False
            )

    except Exception as e:
        logger.error(f"AI Stack initialization failed: {e}")
        background_init_status["ai_stack"] = "failed"
        background_init_status["errors"].append(f"AI Stack init: {str(e)}")
        log_initialization_step(
            "AI Stack", f"Initialization failed: {str(e)}", 100, False
        )


async def get_or_create_knowledge_base(app: FastAPI, force_refresh: bool = False):
    """
    Get or create a properly initialized knowledge base instance for the app.
    Enhanced with AI Stack integration awareness.
    """
    from backend.knowledge_factory import get_or_create_knowledge_base as factory_kb

    try:
        kb = await factory_kb(app, force_refresh)
        if kb is not None:
            background_init_status["knowledge_base"] = "ready"

            # Enhanced: Check if AI Stack integration is available
            if (
                hasattr(app.state, "ai_stack_client")
                and background_init_status.get("ai_stack") == "ready"
            ):
                logger.info(
                    "Knowledge Base initialized with AI Stack enhancement available"
                )
            else:
                logger.info("Knowledge Base initialized in standalone mode")
        else:
            background_init_status["knowledge_base"] = "failed"
            logger.error("Knowledge base initialization failed")
        return kb
    except Exception as e:
        logger.error(f"Knowledge base initialization error: {e}")
        background_init_status["knowledge_base"] = "failed"
        background_init_status["errors"].append(f"KB init: {str(e)}")
        return None


async def enhanced_background_init(app: FastAPI):
    """
    Enhanced background initialization with AI Stack integration.
    """
    try:
        log_initialization_step(
            "Background Init", "Starting enhanced background initialization...", 0
        )

        # Original initialization tasks
        tasks = []

        # REFACTORED: Redis now uses centralized client management
        # Redis connections are handled by get_redis_client() when needed
        async def init_redis():
            try:
                # Mark Redis as ready - no initialization needed with centralized client
                # Components will call get_redis_client() directly when they need Redis
                background_init_status["redis_pools"] = "ready"
                log_initialization_step(
                    "Redis",
                    "Using centralized Redis client management (src.utils.redis_client)",
                    90,
                    True
                )
            except Exception as e:
                logger.error(f"Redis status check failed: {e}")
                background_init_status["redis_pools"] = "failed"
                background_init_status["errors"].append(f"Redis: {str(e)}")

        # Knowledge base initialization
        async def init_kb():
            kb = await get_or_create_knowledge_base(app, force_refresh=False)
            if kb:
                app.state.knowledge_base = kb
                log_initialization_step(
                    "Knowledge Base", "Knowledge base ready", 90, True
                )

        # Chat workflow initialization
        async def init_chat_workflow():
            try:
                workflow_manager = ChatWorkflowManager()
                app.state.chat_workflow_manager = workflow_manager
                background_init_status["chat_workflow"] = "ready"
                log_initialization_step(
                    "Chat Workflow", "Chat workflow manager initialized", 90, True
                )
            except Exception as e:
                logger.error(f"Chat workflow initialization failed: {e}")
                background_init_status["chat_workflow"] = "failed"
                background_init_status["errors"].append(f"Chat workflow: {str(e)}")

        # LLM sync initialization
        async def init_llm_sync():
            try:
                await background_llm_sync()
                background_init_status["llm_sync"] = "ready"
                log_initialization_step(
                    "LLM Sync", "LLM synchronization completed", 90, True
                )
            except Exception as e:
                logger.error(f"LLM sync failed: {e}")
                background_init_status["llm_sync"] = "failed"
                background_init_status["errors"].append(f"LLM sync: {str(e)}")

        # AI Stack initialization (new)
        async def init_ai_stack():
            await initialize_ai_stack(app)

        # Run all initialization tasks concurrently
        tasks = [
            init_redis(),
            init_kb(),
            init_chat_workflow(),
            init_llm_sync(),
            init_ai_stack(),  # New AI Stack initialization
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        # Check overall initialization status
        failed_services = [
            service
            for service, status in background_init_status.items()
            if status == "failed" and service != "errors"
        ]

        if failed_services:
            log_initialization_step(
                "Background Init",
                f"Completed with {len(failed_services)} failed services: {', '.join(failed_services)}",
                100,
                False,
            )
        else:
            log_initialization_step(
                "Background Init", "All services initialized successfully", 100, True
            )

    except Exception as e:
        logger.error(f"Background initialization failed: {e}")
        background_init_status["errors"].append(f"Background init: {str(e)}")


@asynccontextmanager
async def enhanced_lifespan(app: FastAPI):
    """Enhanced application lifespan with AI Stack cleanup."""
    # Startup
    logger.info("🚀 Enhanced AutoBot Backend starting up with AI Stack integration...")

    # Start background initialization
    asyncio.create_task(enhanced_background_init(app))

    yield

    # Shutdown
    logger.info("🔄 Enhanced AutoBot Backend shutting down...")

    # Cleanup AI Stack client
    try:
        await close_ai_stack_client()
        logger.info("✅ AI Stack client closed successfully")
    except Exception as e:
        logger.error(f"❌ Error closing AI Stack client: {e}")

    # REFACTORED: Removed redis_pools cleanup - using centralized Redis client management
    # Redis connections are automatically managed by get_redis_client()
    logger.info("✅ Redis connections managed by centralized client (src.utils.redis_client)")

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
        description="Comprehensive AI-powered automation platform with advanced RAG, multi-agent coordination, and NPU acceleration",
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

    # Add authentication middleware
    app.add_middleware(AuthenticationMiddleware)

    # Configure enhanced API routes
    configure_enhanced_api_routes(app)

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Global exception: {exc}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "path": str(request.url.path),
                "timestamp": time.time(),
                "ai_stack_available": background_init_status.get("ai_stack") == "ready",
            },
        )

    # Enhanced health check endpoint
    @app.get("/api/health")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def enhanced_health_check():
        """Enhanced health check endpoint with AI Stack status."""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "background_init": background_init_status,
            "services": {
                "redis_pools": background_init_status.get("redis_pools", "unknown"),
                "knowledge_base": background_init_status.get(
                    "knowledge_base", "unknown"
                ),
                "chat_workflow": background_init_status.get("chat_workflow", "unknown"),
                "llm_sync": background_init_status.get("llm_sync", "unknown"),
                "ai_stack": background_init_status.get("ai_stack", "unknown"),
                "ai_stack_agents": background_init_status.get(
                    "ai_stack_agents", "unknown"
                ),
            },
            "ai_enhanced": background_init_status.get("ai_stack") == "ready",
            "agent_count": len(
                getattr(app.state, "ai_stack_agents", {}).get("agents", [])
            ),
            "capabilities": {
                "rag_enhanced_search": background_init_status.get("ai_stack")
                == "ready",
                "multi_agent_coordination": background_init_status.get(
                    "ai_stack_agents"
                )
                == "ready",
                "knowledge_extraction": background_init_status.get("ai_stack")
                == "ready",
                "enhanced_chat": background_init_status.get("ai_stack") == "ready",
                "npu_acceleration": background_init_status.get("ai_stack_agents")
                == "ready",
            },
        }

    # AI Stack specific health endpoint
    @app.get("/api/health/ai-stack")
    @with_error_handling(category=ErrorCategory.SYSTEM)
    async def ai_stack_health():
        """Dedicated AI Stack health endpoint."""
        if hasattr(app.state, "ai_stack_client"):
            ai_client = app.state.ai_stack_client
            health_status = await ai_client.health_check()
            return health_status
        else:
            return {
                "status": "unavailable",
                "message": "AI Stack client not initialized",
                "timestamp": time.time(),
            }

    # Add static files
    add_static_files(app)

    logger.info("✅ Enhanced FastAPI application configured successfully")
    return app


def configure_enhanced_api_routes(app: FastAPI) -> None:
    """Configure all API routes including enhanced AI Stack endpoints."""
    # Create API registry for tracking endpoints
    api_registry = APIRegistry()

    # Create main API router
    from fastapi import APIRouter

    api_router = APIRouter()

    # Core routers configuration (original)
    core_routers_config = [
        (chat_router, "", ["chat"], "chat"),
        (system_router, "/system", ["system"], "system"),
        (settings_router, "/settings", ["settings"], "settings"),
        (prompts_router, "/prompts", ["prompts"], "prompts"),
        (knowledge_router, "/knowledge_base", ["knowledge"], "knowledge"),
        (llm_router, "/llm", ["llm"], "llm"),
        (redis_router, "/redis", ["redis"], "redis"),
        (voice_router, "/voice", ["voice"], "voice"),
        (agent_router, "/agent", ["agent"], "agent"),
        (agent_config_router, "/agent-config", ["agent-config"], "agent_config"),
        (
            intelligent_agent_router,
            "/intelligent-agent",
            ["intelligent-agent"],
            "intelligent_agent",
        ),
        (files_router, "/files", ["files"], "files"),
        (developer_router, "/developer", ["developer"], "developer"),
        (embeddings_router, "/embeddings", ["embeddings"], "embeddings"),
        (kb_librarian_router, "/kb-librarian", ["kb-librarian"], "kb_librarian"),
        (terminal_router, "/terminal", ["terminal"], "terminal"),
        (workflow_router, "/workflow", ["workflow"], "workflow"),
        (metrics_router, "/metrics", ["metrics"], "metrics"),
        (monitoring_router, "/monitoring", ["monitoring"], "monitoring"),
        (templates_router, "/templates", ["templates"], "templates"),
        (scheduler_router, "/scheduler", ["scheduler"], "scheduler"),
        (secrets_router, "/secrets", ["secrets"], "secrets"),
        (research_browser_router, "/research", ["research"], "research_browser"),
        (security_router, "/security", ["security"], "security"),
        (error_monitoring_router, "/errors", ["error-monitoring"], "error_monitoring"),
    ]

    # Enhanced AI Stack routers (new)
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

    # Add optional routers with error handling
    optional_routers = [
        (
            "backend.api.workflow_automation",
            "/workflow_automation",
            ["workflow_automation"],
            "workflow_automation",
        ),
        (
            "backend.api.advanced_workflow_orchestrator",
            "/advanced_workflow",
            ["advanced_workflow"],
            "advanced_workflow",
        ),
        ("backend.api.project_state", "", ["project_state"], "project_state"),
        (
            "backend.api.orchestration",
            "/orchestration",
            ["orchestration"],
            "orchestration",
        ),
        ("backend.api.code_search", "/code_search", ["code_search"], "code_search"),
        (
            "backend.api.development_speedup",
            "/development_speedup",
            ["development_speedup"],
            "development_speedup",
        ),
        ("backend.api.sandbox", "/sandbox", ["sandbox"], "sandbox"),
        ("backend.api.elevation", "/system/elevation", ["elevation"], "elevation"),
        (
            "backend.api.enhanced_memory",
            "/memory",
            ["enhanced_memory"],
            "enhanced_memory",
        ),
        (
            "backend.api.advanced_control",
            "/control",
            ["advanced_control"],
            "advanced_control",
        ),
        (
            "backend.api.phase_management",
            "/phases",
            ["phase_management"],
            "phase_management",
        ),
        (
            "backend.api.state_tracking",
            "/state-tracking",
            ["state_tracking"],
            "state_tracking",
        ),
        (
            "backend.api.llm_awareness",
            "/llm-awareness",
            ["llm_awareness"],
            "llm_awareness",
        ),
        (
            "backend.api.validation_dashboard",
            "/validation-dashboard",
            ["validation_dashboard"],
            "validation_dashboard",
        ),
    ]

    # Register optional routers
    for module_path, prefix, tags, name in optional_routers:
        try:
            module = __import__(module_path, fromlist=["router"])
            router = getattr(module, "router")
            router_tags: List[Union[str, Enum]] = list(tags) if tags else []
            api_router.include_router(router, prefix=prefix, tags=router_tags)
            api_registry.register_router(name, router, f"/api{prefix}")
            logger.info(
                f"✅ Successfully registered optional router: {name} at /api{prefix}"
            )
        except ImportError:
            logger.info(f"⏭️ Optional router not available - skipping: {name}")
        except Exception as e:
            logger.error(f"❌ Failed to register optional router {name}: {e}")

    # Register utility endpoints
    api_registry.register_router("utility", api_router, "/api")

    # Include the API router in the main app
    app.include_router(api_router, prefix="/api")

    # Include WebSocket router
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
    "get_or_create_knowledge_base",
    "initialize_ai_stack",
]
