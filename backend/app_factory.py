"""
Consolidated Application Factory for AutoBot FastAPI Backend

This module implements the Application Factory Pattern to create and configure
the FastAPI application instance with all the best features from previous iterations:
- Complete FastAPI setup with all routers (from original app_factory.py)
- Redis timeout fixes and fast startup (from fast_app_factory_fix.py)
- Modern dependency injection support (from async_app_factory.py)
- Background initialization for performance (from fast_app_factory.py)
"""

import asyncio
import logging
import os
import signal
import socket
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union, Any

import redis
from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
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
    REDIS_HOST_IP,
)

# Import constants
from src.constants.network_constants import NetworkConstants, ServiceURLs

# Import API routers with proper error handling
from backend.api.agent import router as agent_router
from backend.api.agent_config import router as agent_config_router
from backend.api.chat import router as chat_router
from backend.api.developer import (
    api_registry,
    enhanced_404_handler,
    enhanced_405_handler,
)
from backend.api.developer import router as developer_router
from backend.api.embeddings import router as embeddings_router
from backend.api.error_monitoring import router as error_monitoring_router
from backend.api.files import router as files_router
from backend.api.intelligent_agent import router as intelligent_agent_router
from backend.api.kb_librarian import router as kb_librarian_router
from backend.api.knowledge import router as knowledge_router
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

# Import core components
from src.chat_history_manager import ChatHistoryManager
from src.config import config as global_config_manager
from src.diagnostics import PerformanceOptimizedDiagnostics
from src.enhanced_security_layer import EnhancedSecurityLayer
from src.knowledge_base import KnowledgeBase
from src.security_layer import SecurityLayer
from src.utils.redis_client import get_redis_client
from src.voice_interface import VoiceInterface

logger = logging.getLogger(__name__)

# Track actual startup time for real uptime reporting
APP_START_TIME = time.time()

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

class MinimalChatHistoryManager:
    """Minimal chat history manager to prevent None errors during startup"""

    async def save_session_fast(self, chat_id: str, session_data: dict):
        """Fast session save without full processing"""
        logger.info(f"Chat session save operation for {chat_id} (minimal implementation)")
        return {"status": "success", "method": "minimal"}

    async def save_session(self, chat_id: str, session_data: dict = None, messages: list = None, name: str = None):
        """Fast session save operation - compatible with both old and new API calls"""
        logger.info(f"Chat session save operation for {chat_id} (minimal implementation)")

        if messages is not None:
            logger.info(f"Saving {len(messages)} messages for chat {chat_id}")
        if session_data is not None:
            logger.info(f"Saving session data for chat {chat_id}")
        if name is not None:
            logger.info(f"Chat name: {name}")

        return {"status": "success", "method": "minimal", "chat_id": chat_id}

    async def list_sessions_fast(self):
        """Fast session listing without full chat loading"""
        logger.info("Chat sessions list operation (minimal implementation)")
        return []

    def _get_chats_directory(self):
        """Get chats directory path"""
        chats_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chats")
        os.makedirs(chats_dir, exist_ok=True)
        return chats_dir


def report_startup_progress(stage: str, message: str, percentage: int, icon: str = "📋"):
    """Report startup progress"""
    logger.info(f"{icon} [{percentage:3d}%] {stage}: {message}")


async def _check_redis_modules(redis_host: str, redis_port: int) -> bool:
    """Checks if RediSearch module is loaded in Redis with timeout protection."""
    try:
        resolved_host = redis_host
        # Docker Desktop specific networking with timeout protection
        if redis_host == "host.docker.internal":
            try:
                socket.setdefaulttimeout(2.0)  # 2 second timeout
                resolved_host = socket.gethostbyname(redis_host)
                logger.info(f"Resolved host.docker.internal to IP: {resolved_host}")
                socket.setdefaulttimeout(None)  # Reset to default
            except (socket.gaierror, socket.timeout) as e:
                logger.error(f"Failed to resolve host.docker.internal: {e}")
                resolved_host = redis_host
                socket.setdefaulttimeout(None)  # Reset to default

        r = get_redis_client()
        if r is None:
            logger.error("Could not get Redis client from centralized utility")
            return False

        try:
            # Add timeout to prevent blocking
            r.ping()
            logger.info(f"Successfully connected to Redis at {resolved_host}:{redis_port}")

            try:
                r.client_list()
                logger.info("Redis client info retrieved successfully")
            except Exception as e:
                logger.warning(f"Could not get client info from Redis: {e}")
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}")
            return False

        try:
            # Try to get module list - this may fail on some Redis configurations
            modules = r.module_list()
            if isinstance(modules, list):
                module_names = [m.get("name", "") for m in modules] if modules else []
                logger.info(f"Redis modules loaded: {module_names}")
                if "search" in module_names:
                    logger.info("✅ RediSearch module 'search' is detected in Redis.")
                    return True
                else:
                    logger.warning("❌ RediSearch module 'search' is NOT detected in Redis.")
                    return False
            else:
                logger.warning("Could not retrieve module list - Redis modules check skipped")
                return True
        except Exception as e:
            logger.warning(f"Could not check Redis modules: {e}")
            return True

    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis at {redis_host}:{redis_port} for module check: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking Redis modules: {e}")
        return False


async def initialize_components_background(app: FastAPI):
    """Initialize heavy components in the background with comprehensive error handling"""
    global background_init_status

    background_init_status["initialization_start"] = datetime.now().isoformat()
    logger.info("🚀 Starting background component initialization...")

    try:
        # Initialize orchestrator (CRITICAL for chat functionality)
        logger.info("🤖 Initializing orchestrator...")
        background_init_status["orchestrator"] = "initializing"

        try:
            from src.lightweight_orchestrator import lightweight_orchestrator
            await lightweight_orchestrator.startup()
            app.state.lightweight_orchestrator = lightweight_orchestrator
            app.state.orchestrator = lightweight_orchestrator  # For compatibility
            background_init_status["orchestrator"] = "ready"
            logger.info("✅ Orchestrator initialized successfully")
            report_startup_progress("orchestrator", "Orchestrator ready", 25, "🤖")
        except Exception as e:
            background_init_status["orchestrator"] = "failed"
            background_init_status["errors"].append(f"Orchestrator: {str(e)}")
            logger.error(f"❌ Orchestrator initialization failed: {e}")

        # Initialize knowledge base
        logger.info("🧠 Initializing knowledge base...")
        background_init_status["knowledge_base"] = "initializing"

        try:
            from src.knowledge_base import KnowledgeBase
            app.state.knowledge_base = KnowledgeBase()
            background_init_status["knowledge_base"] = "ready"
            logger.info("✅ Knowledge base initialized")
            report_startup_progress("knowledge_base", "Knowledge base ready", 50, "🧠")
        except Exception as e:
            background_init_status["knowledge_base"] = "failed"
            background_init_status["errors"].append(f"Knowledge base: {str(e)}")
            logger.error(f"❌ Knowledge base initialization failed: {e}")

        # Initialize chat history manager
        logger.info("💬 Initializing chat history manager...")
        background_init_status["chat_history"] = "initializing"

        try:
            redis_config = global_config_manager.get_redis_config()
            app.state.chat_history_manager = ChatHistoryManager(
                history_file=global_config_manager.get_nested(
                    "data.chat_history_file", "data/chat_history.json"
                ),
                use_redis=redis_config.get("enabled", False),
                redis_host=redis_config.get("host", REDIS_HOST_IP),
                redis_port=redis_config.get("port", 6379),
            )
            background_init_status["chat_history"] = "ready"
            logger.info("✅ Chat history manager initialized")
            report_startup_progress("chat_history", "Chat history ready", 75, "💬")
        except Exception as e:
            background_init_status["chat_history"] = "failed"
            background_init_status["errors"].append(f"Chat history: {str(e)}")
            logger.error(f"❌ Chat history initialization failed: {e}")

        # Initialize Redis client
        logger.info("🔄 Initializing Redis client...")
        background_init_status["redis_client"] = "initializing"

        try:
            app.state.main_redis_client = get_redis_client()
            if app.state.main_redis_client:
                app.state.main_redis_client.ping()
                background_init_status["redis_client"] = "ready"
                logger.info("✅ Redis client initialized")
            else:
                background_init_status["redis_client"] = "failed"
                background_init_status["errors"].append("Redis client: Could not connect")
        except Exception as e:
            background_init_status["redis_client"] = "failed"
            background_init_status["errors"].append(f"Redis client: {str(e)}")
            logger.error(f"❌ Redis client initialization failed: {e}")

        # Initialize remaining core components
        try:
            app.state.diagnostics = PerformanceOptimizedDiagnostics()
            app.state.voice_interface = VoiceInterface()
            app.state.security_layer = SecurityLayer()
            app.state.enhanced_security_layer = EnhancedSecurityLayer()
            logger.info("✅ Core components initialized")
        except Exception as e:
            background_init_status["errors"].append(f"Core components: {str(e)}")
            logger.error(f"❌ Core components initialization failed: {e}")

        # Check Redis modules
        try:
            redis_config = global_config_manager.get_redis_config()
            await _check_redis_modules(
                redis_config.get("host", REDIS_HOST_IP),
                redis_config.get("port", 6379)
            )
        except Exception as e:
            logger.warning(f"Redis modules check failed: {e}")

        # Start system monitoring
        try:
            from src.metrics.system_monitor import system_monitor
            await system_monitor.start_monitoring()
            logger.info("✅ System monitoring started")
        except Exception as e:
            logger.error(f"Failed to start system monitoring: {e}")

        # Start workflow scheduler
        try:
            from src.workflow_scheduler import workflow_scheduler

            async def execute_scheduled_workflow(scheduled_workflow):
                """Execute a scheduled workflow using the workflow API"""
                try:
                    from fastapi import BackgroundTasks
                    from backend.api.workflow import (
                        WorkflowExecutionRequest,
                        execute_workflow,
                    )

                    execution_request = WorkflowExecutionRequest(
                        user_message=scheduled_workflow.user_message,
                        workflow_id=scheduled_workflow.id,
                        auto_approve=scheduled_workflow.auto_approve,
                    )

                    background_tasks = BackgroundTasks()
                    result = await execute_workflow(execution_request, background_tasks)
                    return result

                except Exception as e:
                    logger.error(f"Scheduled workflow execution failed: {e}")
                    return {"success": False, "error": str(e)}

            workflow_scheduler.set_workflow_executor(execute_scheduled_workflow)
            await workflow_scheduler.start()
            logger.info("✅ Workflow scheduler started")
        except Exception as e:
            logger.error(f"Failed to start workflow scheduler: {e}")

        # Mark as complete
        ready_components = sum(
            1 for key, status in background_init_status.items()
            if isinstance(status, str) and status == "ready"
        )
        total_components = 4  # orchestrator, knowledge_base, chat_history, redis_client

        background_init_status["components_ready"] = (ready_components >= 3)  # Allow for some failures
        background_init_status["initialization_complete"] = datetime.now().isoformat()

        report_startup_progress("complete", "Background initialization complete", 100, "🎉")
        logger.info(f"🎉 Background initialization complete: {ready_components}/{total_components} components ready")

    except Exception as e:
        background_init_status["errors"].append(f"Initialization error: {str(e)}")
        logger.error(f"❌ Background initialization failed: {e}")


@asynccontextmanager
async def create_lifespan_manager(app: FastAPI):
    """
    Consolidated lifespan manager with fast startup and background initialization
    """
    logger.info("🚀 Application lifespan startup initiated")

    try:
        # Fast startup: Set minimal chat history manager immediately
        app.state.chat_history_manager = MinimalChatHistoryManager()
        report_startup_progress("state", "App state initialized", 10, "📦")

        # Start background initialization without waiting
        asyncio.create_task(initialize_components_background(app))

        logger.info("✅ Fast application startup completed - API ready immediately")

    except Exception as e:
        logger.error(f"Failed to initialize application: {e}", exc_info=True)
        raise

    yield

    # Shutdown events
    logger.info("🛑 Application lifespan shutdown initiated")

    try:
        from src.metrics.system_monitor import system_monitor
        await system_monitor.stop_monitoring()
        logger.info("System monitoring stopped")
    except Exception as e:
        logger.error(f"Failed to stop system monitoring: {e}")

    try:
        from src.workflow_scheduler import workflow_scheduler
        await workflow_scheduler.stop()
        logger.info("Workflow scheduler stopped")
    except Exception as e:
        logger.error(f"Failed to stop workflow scheduler: {e}")

    logger.info("Application lifespan shutdown completed")


def add_middleware(app: FastAPI) -> None:
    """Add comprehensive middleware to the FastAPI application."""
    # Build CORS origins dynamically from configuration
    try:
        backend_config = global_config_manager.get_config_section("backend")
        cors_origins = backend_config.get("cors_origins", [])
    except Exception as e:
        logger.warning(f"Could not load backend config: {e}, using defaults")
        backend_config = {}
        cors_origins = []

    if not cors_origins:
        cors_origins = [
            f"{HTTP_PROTOCOL}://{FRONTEND_HOST_IP}:{FRONTEND_PORT}",
            f"{HTTP_PROTOCOL}://{BACKEND_HOST_IP}:{BACKEND_PORT}",
        ]

        # Add development server origins
        dev_origins = backend_config.get(
            "dev_origins",
            [
                "http://127.0.0.1:5173",  # Vite dev server
                ServiceURLs.FRONTEND_LOCAL,  # Alternative localhost
                "http://127.0.0.1:3000",  # Alternative dev port
                "http://localhost:3000",  # Alternative localhost dev port
            ],
        )
        cors_origins.extend(dev_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "Accept",
            "Origin",
            "Access-Control-Request-Method",
            "Access-Control-Request-Headers",
        ],
        expose_headers=[
            "Content-Type",
            "X-Total-Count",
            "X-Request-ID",
        ],
    )
    logger.info(f"CORS middleware added with origins: {cors_origins}")

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)

        # Remove potentially problematic headers
        headers_to_remove = [
            "content-security-policy",
            "x-xss-protection",
            "X-Frame-Options",
            "Expires",
        ]
        for header in headers_to_remove:
            if header in response.headers:
                del response.headers[header]

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

        return response


def add_api_routes(app: FastAPI) -> None:
    """Add all API routes to the FastAPI application with comprehensive router loading."""
    api_router = APIRouter()

    # Essential routes that work immediately
    @api_router.get("/health")
    async def ultra_fast_health():
        """Ultra-fast health check - responds immediately"""
        current_time = time.time()
        uptime_seconds = current_time - APP_START_TIME
        return {
            "status": "healthy",
            "backend": "connected",
            "timestamp": datetime.now().isoformat(),
            "fast_startup": True,
            "uptime": uptime_seconds,
            "uptime_human": f"{uptime_seconds:.1f} seconds",
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
        return {"message": "Hello from AutoBot backend!"}

    @api_router.get("/version")
    async def get_version():
        import hashlib
        build_identifier = f"consolidated_1.0.0_{int(APP_START_TIME)}"
        build_hash = hashlib.md5(build_identifier.encode()).hexdigest()[:12]

        return {
            "version": "1.0.0",
            "backend": "consolidated_factory",
            "api_version": "v1",
            "buildHash": build_hash,
            "timestamp": datetime.now().isoformat(),
            "version_no": "1.0.0",
            "version_time": "2025-09-28 UTC"
        }

    # Manual OPTIONS handler for debugging CORS issues
    @api_router.options("/{path:path}")
    async def handle_options(path: str):
        return {"message": "OPTIONS request handled"}

    # Core routers configuration
    routers_config = [
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
        (intelligent_agent_router, "/intelligent-agent", ["intelligent-agent"], "intelligent_agent"),
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

    # Add optional routers with error handling
    optional_routers = [
        ("backend.api.workflow_automation", "/workflow_automation", ["workflow_automation"], "workflow_automation"),
        ("backend.api.advanced_workflow_orchestrator", "/advanced_workflow", ["advanced_workflow"], "advanced_workflow"),
        ("backend.api.project_state", "", ["project_state"], "project_state"),
        ("backend.api.orchestration", "/orchestration", ["orchestration"], "orchestration"),
        ("backend.api.code_search", "/code_search", ["code_search"], "code_search"),
        ("backend.api.development_speedup", "/development_speedup", ["development_speedup"], "development_speedup"),
        ("backend.api.sandbox", "/sandbox", ["sandbox"], "sandbox"),
        ("backend.api.elevation", "/system/elevation", ["elevation"], "elevation"),
        ("backend.api.enhanced_memory", "/memory", ["enhanced_memory"], "enhanced_memory"),
        ("backend.api.advanced_control", "/control", ["advanced_control"], "advanced_control"),
        ("backend.api.phase_management", "/phases", ["phase_management"], "phase_management"),
        ("backend.api.state_tracking", "/state-tracking", ["state_tracking"], "state_tracking"),
        ("backend.api.llm_awareness", "/llm-awareness", ["llm_awareness"], "llm_awareness"),
        ("backend.api.validation_dashboard", "/validation-dashboard", ["validation_dashboard"], "validation_dashboard"),
    ]

    # Register core routers
    for router, prefix, tags, name in routers_config:
        try:
            router_tags: List[Union[str, Enum]] = list(tags) if tags else []
            api_router.include_router(router, prefix=prefix, tags=router_tags)
            api_registry.register_router(name, router, f"/api{prefix}")
            logger.info(f"✅ Successfully registered router: {name} at /api{prefix}")
        except Exception as e:
            logger.error(f"❌ Failed to register router {name}: {e}")

    # Register optional routers
    for module_path, prefix, tags, name in optional_routers:
        try:
            module = __import__(module_path, fromlist=["router"])
            router = getattr(module, "router")
            router_tags: List[Union[str, Enum]] = list(tags) if tags else []
            api_router.include_router(router, prefix=prefix, tags=router_tags)
            api_registry.register_router(name, router, f"/api{prefix}")
            logger.info(f"✅ Successfully registered optional router: {name} at /api{prefix}")
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

    logger.info("✅ API routes configured with comprehensive router loading")


def add_static_files(app: FastAPI) -> None:
    """Mount static file serving."""
    static_dir = "static"
    if os.path.exists(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
        logger.info(f"Static files mounted from {static_dir}")
    else:
        logger.warning(f"Static directory {static_dir} not found - skipping static file mounting")


def add_utility_routes(app: FastAPI) -> None:
    """Add utility routes that don't fit in the API structure."""

    @app.get("/.well-known/appspecific/com.chrome.devtools.json")
    async def chrome_devtools_json():
        """
        Handles the request for /.well-known/appspecific/com.chrome.devtools.json
        to prevent 404 errors in Chrome/Edge developer console.
        """
        return JSONResponse(status_code=200, content={})


def add_error_handlers(app: FastAPI) -> None:
    """Add comprehensive error handlers."""

    @app.exception_handler(404)
    async def not_found_handler(request, exc):
        return await enhanced_404_handler(request, exc)

    @app.exception_handler(405)
    async def method_not_allowed_handler(request, exc):
        return await enhanced_405_handler(request, exc)

    @app.exception_handler(500)
    async def internal_error_handler(request, exc):
        """Handle 500 errors gracefully"""
        logger.error(f"Internal server error on {request.url.path}: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error occurred"}
        )


def setup_signal_handlers():
    """Setup graceful shutdown signal handlers"""
    def signal_handler(signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def create_app() -> FastAPI:
    """
    Consolidated application factory function that creates and configures the FastAPI application
    with the best features from all previous implementations.

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    logger.info("🚀 Creating consolidated AutoBot FastAPI application...")

    # Create FastAPI app with lifespan manager
    app = FastAPI(
        title="AutoBot API",
        description="Consolidated AutoBot Backend API with timeout fixes and comprehensive features",
        version="1.0.0-consolidated",
        lifespan=lambda app: create_lifespan_manager(app)
    )

    # Configure the application
    add_middleware(app)
    add_api_routes(app)
    add_static_files(app)
    add_utility_routes(app)
    add_error_handlers(app)

    # Setup signal handlers
    setup_signal_handlers()

    # Report startup progress
    report_startup_progress("initialization", "FastAPI application created", 100, "🎉")
    logger.info("✅ Consolidated FastAPI application created and configured")

    return app


# Create the app instance for uvicorn
app = create_app()