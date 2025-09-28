"""
Application Factory for AutoBot FastAPI Backend

This module implements the Application Factory Pattern to create and configure
the FastAPI application instance, keeping main.py clean and focused.
"""

import logging
import os
import socket
from contextlib import asynccontextmanager
from enum import Enum
from typing import List, Union

import redis
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import API routers
from backend.api.agent import router as agent_router
from backend.api.agent_config import router as agent_config_router
from backend.api.chat_consolidated import router as chat_router
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
from backend.api.terminal_consolidated import router as terminal_consolidated_router
from backend.api.voice import router as voice_router
from backend.api.websockets import router as websocket_router
from backend.api.workflow import router as workflow_router

# Import host IP addresses from main config
from src.config import (
    BACKEND_HOST_IP,
    BACKEND_PORT,
    FRONTEND_HOST_IP,
    FRONTEND_PORT,
    HTTP_PROTOCOL,
    REDIS_HOST_IP,
)

# Import workflow automation router
try:
    from backend.api.workflow_automation import router as workflow_automation_router

    WORKFLOW_AUTOMATION_AVAILABLE = True
except ImportError:
    workflow_automation_router = None
    WORKFLOW_AUTOMATION_AVAILABLE = False
from src.chat_history_manager import ChatHistoryManager

# Import centralized configuration
from src.config import config as global_config_manager
from src.diagnostics import Diagnostics
from src.enhanced_security_layer import EnhancedSecurityLayer
from src.knowledge_base import KnowledgeBase

# Import core components
from src.security_layer import SecurityLayer
from src.utils.redis_client import get_redis_client
from src.voice_interface import VoiceInterface

logger = logging.getLogger(__name__)


async def _check_redis_modules(redis_host: str, redis_port: int) -> bool:
    """Checks if RediSearch module is loaded in Redis."""
    try:
        resolved_host = redis_host
        # Docker Desktop specific networking: host.docker.internal allows containers
        # to connect to services running on the host machine. This is a special DNS name
        # that Docker Desktop provides for container-to-host communication.
        # We resolve it to an actual IP address for better connection reliability.
        if redis_host == "host.docker.internal":
            try:
                # URGENT FIX: DNS resolution can block - add timeout
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
            # URGENT FIX: Add timeout to prevent blocking
            r.ping()  # Redis py default timeout is 30s which may be too long
            logger.info(
                f"Successfully connected to Redis at {resolved_host}:{redis_port}"
            )

            # Try to get client info with proper error handling
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
                    logger.warning(
                        "❌ RediSearch module 'search' is NOT detected in Redis."
                    )
                    return False
            else:
                logger.warning(
                    "Could not retrieve module list - Redis modules check skipped"
                )
                return True
        except Exception as e:
            logger.warning(f"Could not check Redis modules: {e}")
            # Return True anyway since basic Redis connection works
            return True

    except redis.ConnectionError as e:
        logger.error(
            f"Failed to connect to Redis at {redis_host}:{redis_port} for "
            f"module check: {e}"
        )
        return False
    except Exception as e:
        logger.error(f"Error checking Redis modules: {e}")
        return False


async def _initialize_core_components(app: FastAPI) -> None:
    """Initialize all core application components."""
    logger.debug("Initializing core components...")

    try:
        # Orchestrator will be initialized in _initialize_orchestrator
        logger.info("Orchestrator will be initialized separately")

        app.state.knowledge_base = KnowledgeBase()
        logger.info("KnowledgeBase initialized and stored in app.state")

        app.state.diagnostics = Diagnostics()
        logger.info("Diagnostics initialized and stored in app.state")

        app.state.voice_interface = VoiceInterface()
        logger.info("VoiceInterface initialized and stored in app.state")

        app.state.security_layer = SecurityLayer()
        logger.info("SecurityLayer initialized and stored in app.state")

        # Initialize Enhanced Security Layer with command execution controls
        app.state.enhanced_security_layer = EnhancedSecurityLayer()
        logger.info("EnhancedSecurityLayer initialized and stored in app.state")

        logger.info(
            "Core components (Orchestrator, KB, Diagnostics, Voice, Security) "
            "initialized"
        )

        # Verify components are accessible (orchestrator will be initialized later)
        logger.debug(f"Diagnostics in app.state: {app.state.diagnostics is not None}")
        logger.debug(
            f"KnowledgeBase in app.state: {app.state.knowledge_base is not None}"
        )
        logger.debug(
            f"VoiceInterface in app.state: {app.state.voice_interface is not None}"
        )
        logger.debug(
            f"SecurityLayer in app.state: {app.state.security_layer is not None}"
        )

    except Exception as e:
        logger.error(f"Error initializing core components: {e}", exc_info=True)
        raise


async def _initialize_orchestrator(app: FastAPI) -> None:
    """Initialize the orchestrator with Redis tasks if needed."""
    logger.debug("Starting Orchestrator startup...")

    try:
        # PERFORMANCE FIX: Initialize lightweight orchestrator for fast routing
        logger.info(
            "PERFORMANCE FIX: Initializing LightweightOrchestrator for "
            "non-blocking operations"
        )
        from src.lightweight_orchestrator import lightweight_orchestrator

        await lightweight_orchestrator.startup()
        app.state.lightweight_orchestrator = lightweight_orchestrator
        logger.info("LightweightOrchestrator initialized successfully")

        # Initialize full orchestrator for backward compatibility
        logger.info("Initializing full orchestrator for chat endpoint compatibility")
        from src.orchestrator import Orchestrator
        from src.utils.service_registry import ServiceConfig, get_service_registry

        # Register ollama service if not already registered
        registry = get_service_registry()
        if "ollama" not in registry.services:
            logger.info("Registering ollama service for orchestrator initialization")
            ollama_service = ServiceConfig(
                name="ollama",
                host="localhost",
                port=11434,
                scheme="http",
                path="",
                health_endpoint="/api/tags",
            )
            registry.register_service(ollama_service)
            logger.info("Ollama service registered successfully")

        # Initialize the main orchestrator (has workflow orchestration methods)
        app.state.orchestrator = Orchestrator()
        logger.info("Full orchestrator initialized successfully")

        # DISABLE Redis background tasks that block the event loop
        logger.info(
            "PERFORMANCE FIX: Disabling Redis background tasks to " "prevent blocking"
        )
        app.state.background_tasks = []

    except Exception as e:
        logger.error(f"Error during orchestrator startup: {e}", exc_info=True)
        # Ensure background_tasks is initialized even on failure
        app.state.background_tasks = []
        # Set orchestrator to None on failure
        app.state.orchestrator = None
        # Log and allow the app to potentially continue in a degraded state

    logger.debug("Orchestrator startup completed")

    # Verify orchestrator initialization
    logger.debug(
        f"Orchestrator in app.state: "
        f"{getattr(app.state, 'orchestrator', None) is not None}"
    )
    logger.debug(
        f"Lightweight orchestrator in app.state: "
        f"{getattr(app.state, 'lightweight_orchestrator', None) is not None}"
    )


async def _initialize_knowledge_base(app: FastAPI) -> None:
    """Initialize the knowledge base asynchronously."""
    logger.debug("Initializing KnowledgeBase...")

    # URGENT FIX: Skip KB initialization to prevent blocking during startup
    logger.info(
        "PERFORMANCE FIX: Skipping KnowledgeBase ainit() to " "prevent startup blocking"
    )
    # try:
    #     await app.state.knowledge_base.ainit()
    #     logger.info("KnowledgeBase ainit() called during startup")
    # except Exception as e:
    #     logger.error(f"Error during KnowledgeBase initialization: {e}",
    #                  exc_info=True)
    #     logger.warning("KnowledgeBase initialization failed, but "
    #                    "continuing startup...")

    logger.debug("KnowledgeBase initialization skipped")


async def _initialize_chat_history_manager(app: FastAPI) -> None:
    """Initialize the chat history manager with Redis configuration."""
    logger.debug("Initializing ChatHistoryManager...")

    redis_config = global_config_manager.get_redis_config()
    use_redis = redis_config.get("enabled", False)
    redis_host = redis_config.get("host", REDIS_HOST_IP)
    redis_port = redis_config.get("port", 6379)

    logger.info(
        f"Redis configuration loaded: enabled={use_redis}, host={redis_host}, "
        f"port={redis_port}"
    )

    app.state.chat_history_manager = ChatHistoryManager(
        history_file=global_config_manager.get_nested(
            "data.chat_history_file", "data/chat_history.json"
        ),
        use_redis=use_redis,
        redis_host=redis_host,
        redis_port=redis_port,
    )

    logger.info("ChatHistoryManager initialized")
    logger.debug(
        f"ChatHistoryManager in app.state: {app.state.chat_history_manager is not None}"
    )


async def _initialize_redis_client(app: FastAPI) -> None:
    """Initialize the main Redis client for the application."""
    logger.debug("Initializing main Redis client...")

    try:
        app.state.main_redis_client = get_redis_client()
        if app.state.main_redis_client is None:
            logger.error("Could not get Redis client from centralized utility")
            return
        app.state.main_redis_client.ping()  # Test connection
        logger.info("Main Redis client initialized and connected")
    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis for main_redis_client: {e}")
        app.state.main_redis_client = None

    logger.debug("Main Redis client initialization completed")


@asynccontextmanager
async def create_lifespan_manager(app: FastAPI):
    """
    Context manager for application startup and shutdown events.
    Replaces deprecated @app.on_event("startup") and @app.on_event("shutdown").
    """
    logger.info("Application lifespan startup initiated")

    try:
        # Initialize all core components
        await _initialize_core_components(app)
        await _initialize_orchestrator(app)

        # Check Redis modules
        redis_config = global_config_manager.get_redis_config()
        await _check_redis_modules(
            redis_config.get("host", REDIS_HOST_IP), redis_config.get("port", 6379)
        )

        # Initialize remaining components
        await _initialize_knowledge_base(app)
        await _initialize_chat_history_manager(app)
        await _initialize_redis_client(app)

        logger.info("Application startup completed successfully")

    except Exception as e:
        logger.error(f"Failed to initialize application: {e}", exc_info=True)
        raise

    # System monitoring and scheduler startup
    try:
        from src.metrics.system_monitor import system_monitor

        await system_monitor.start_monitoring()
        logger.info("System monitoring started")
    except Exception as e:
        logger.error(f"Failed to start system monitoring: {e}")

    try:
        from src.workflow_scheduler import workflow_scheduler

        # Set up workflow executor integration
        async def execute_scheduled_workflow(scheduled_workflow):
            """Execute a scheduled workflow using the workflow API"""
            try:
                from fastapi import BackgroundTasks

                from backend.api.workflow import (
                    WorkflowExecutionRequest,
                    execute_workflow,
                )

                # Create execution request
                execution_request = WorkflowExecutionRequest(
                    user_message=scheduled_workflow.user_message,
                    workflow_id=scheduled_workflow.id,
                    auto_approve=scheduled_workflow.auto_approve,
                )

                # Execute workflow
                background_tasks = BackgroundTasks()
                result = await execute_workflow(execution_request, background_tasks)

                return result

            except Exception as e:
                logger.error(f"Scheduled workflow execution failed: {e}")
                return {"success": False, "error": str(e)}

        workflow_scheduler.set_workflow_executor(execute_scheduled_workflow)
        await workflow_scheduler.start()
        logger.info("Workflow scheduler started")
    except Exception as e:
        logger.error(f"Failed to start workflow scheduler: {e}")

    yield

    # Shutdown events
    logger.info("Application lifespan shutdown initiated")

    # System monitoring and scheduler shutdown
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
    """Add middleware to the FastAPI application."""
    # Enable CORS for frontend on multiple ports using config
    backend_config = global_config_manager.get_backend_config()
    cors_origins = backend_config.get("cors_origins", [])

    # Use fallback if cors_origins is empty
    # (since get() returns [] when key exists but is empty)
    if not cors_origins:
        # Build CORS origins dynamically from configuration
        cors_origins = [
            f"{HTTP_PROTOCOL}://{FRONTEND_HOST_IP}:{FRONTEND_PORT}",
            f"{HTTP_PROTOCOL}://{BACKEND_HOST_IP}:{BACKEND_PORT}",
        ]

        # Add development server origins from configuration
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
        response.headers["X-Content-Type-Options"] = "nosnif"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

        return response


def add_api_routes(app: FastAPI) -> None:
    """Add all API routes to the FastAPI application."""
    # Create an API router
    api_router = APIRouter()

    # Include modular API routers and register them
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
        (
            terminal_consolidated_router,
            "/terminal/consolidated",
            ["terminal_consolidated"],
            "terminal_consolidated",
        ),
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

    # Add workflow automation router if available
    if WORKFLOW_AUTOMATION_AVAILABLE and workflow_automation_router:
        routers_config.append(
            (
                workflow_automation_router,
                "/workflow_automation",
                ["workflow_automation"],
                "workflow_automation",
            )
        )

    # Add advanced workflow orchestrator router if available
    try:
        from backend.api.advanced_workflow_orchestrator import (
            router as advanced_workflow_router,
        )

        routers_config.append(
            (
                advanced_workflow_router,
                "/advanced_workflow",
                ["advanced_workflow"],
                "advanced_workflow",
            )
        )
        logger.info("Advanced workflow orchestrator router registered")
    except ImportError:
        logger.info("Advanced workflow orchestrator not available - skipping router")

    # Chat knowledge functionality is now included in the consolidated chat router
    # No need for separate chat_knowledge router import as it's consolidated
    # The consolidated chat router includes ALL knowledge management endpoints
    logger.info("Chat knowledge functionality included in consolidated chat router")

    # Add project state router if available
    try:
        from backend.api.project_state import router as project_state_router

        routers_config.append(
            (project_state_router, "", ["project_state"], "project_state")
        )
        logger.info("Project state router registered")
    except ImportError as e:
        logger.info(f"Project state router not available - skipping router: {e}")

    # Add enhanced orchestration router
    try:
        from backend.api.orchestration import router as orchestration_router

        routers_config.append(
            (orchestration_router, "/orchestration", ["orchestration"], "orchestration")
        )
        logger.info("Enhanced orchestration router registered")
    except ImportError:
        logger.info("Enhanced orchestration router not available - skipping router")

    # Add code search router
    try:
        from backend.api.code_search import router as code_search_router

        routers_config.append(
            (code_search_router, "/code_search", ["code_search"], "code_search")
        )
        logger.info("Code search router registered")
    except ImportError:
        logger.info("Code search router not available - skipping router")

    # Add development speedup router
    try:
        from backend.api.development_speedup import router as dev_speedup_router

        routers_config.append(
            (
                dev_speedup_router,
                "/development_speedup",
                ["development_speedup"],
                "development_speedup",
            )
        )
        logger.info("Development speedup router registered")
    except ImportError:
        logger.info("Development speedup router not available - skipping router")

    # Add secure sandbox router
    try:
        from backend.api.sandbox import router as sandbox_router

        routers_config.append((sandbox_router, "/sandbox", ["sandbox"], "sandbox"))
        logger.info("Secure sandbox router registered")
    except ImportError:
        logger.info("Secure sandbox router not available - skipping router")

    # Add elevation router for privilege escalation
    try:
        from backend.api.elevation import router as elevation_router

        routers_config.append(
            (elevation_router, "/system/elevation", ["elevation"], "elevation")
        )
        logger.info("Elevation router registered")
    except ImportError as e:
        logger.info(f"Elevation router not available - skipping router: {e}")

    # Add enhanced memory router for Phase 7 features
    try:
        from backend.api.enhanced_memory import router as enhanced_memory_router

        routers_config.append(
            (enhanced_memory_router, "/memory", ["enhanced_memory"], "enhanced_memory")
        )
        logger.info("Enhanced memory router registered")
    except ImportError as e:
        logger.info(f"Enhanced memory router not available - skipping router: {e}")

    # Add advanced control router for Phase 8 features
    try:
        from backend.api.advanced_control import router as advanced_control_router

        routers_config.append(
            (
                advanced_control_router,
                "/control",
                ["advanced_control"],
                "advanced_control",
            )
        )
        logger.info("Advanced control router registered")
    except ImportError as e:
        logger.info(f"Advanced control router not available - skipping router: {e}")

    # Add phase management router for Phase 6 features
    try:
        from backend.api.phase_management import router as phase_management_router

        routers_config.append(
            (
                phase_management_router,
                "/phases",
                ["phase_management"],
                "phase_management",
            )
        )
        logger.info("Phase management router registered")
    except ImportError as e:
        logger.info(f"Phase management router not available - skipping router: {e}")

    # Add state tracking router for comprehensive project state management
    try:
        from backend.api.state_tracking import router as state_tracking_router

        routers_config.append(
            (
                state_tracking_router,
                "/state-tracking",
                ["state_tracking"],
                "state_tracking",
            )
        )
        logger.info("State tracking router registered")
    except ImportError as e:
        logger.info(f"State tracking router not available - skipping router: {e}")

    # Add LLM awareness router for agent self-awareness
    try:
        from backend.api.llm_awareness import router as llm_awareness_router

        routers_config.append(
            (
                llm_awareness_router,
                "/llm-awareness",
                ["llm_awareness"],
                "llm_awareness",
            )
        )
        logger.info("LLM awareness router registered")
    except ImportError as e:
        logger.info(f"LLM awareness router not available - skipping router: {e}")

    # Add validation dashboard router for real-time monitoring
    try:
        from backend.api.validation_dashboard import (
            router as validation_dashboard_router,
        )

        routers_config.append(
            (
                validation_dashboard_router,
                "/validation-dashboard",
                ["validation_dashboard"],
                "validation_dashboard",
            )
        )
        logger.info("Validation dashboard router registered")
    except ImportError as e:
        logger.info(f"Validation dashboard router not available - skipping router: {e}")

    for router, prefix, tags, name in routers_config:
        try:
            # Convert tags to proper type for FastAPI
            router_tags: List[Union[str, Enum]] = list(tags) if tags else []
            api_router.include_router(router, prefix=prefix, tags=router_tags)
            # Register router in API registry for developer mode
            api_registry.register_router(name, router, f"/api{prefix}")
            logger.info(f"Successfully registered router: {name} at /api{prefix}")
        except Exception as e:
            logger.error(f"Failed to register router {name}: {e}")
            # Continue with other routers even if one fails

    # Add utility endpoints
    @api_router.get("/hello")
    async def hello_world():
        return {"message": "Hello from AutoBot backend!"}

    @api_router.get("/version")
    async def get_version():
        return {"version_no": "1.0.0", "version_time": "2025-06-18 20:00 UTC"}

    # Manual OPTIONS handler for debugging CORS issues
    @api_router.options("/{path:path}")
    async def handle_options(path: str):
        return {"message": "OPTIONS request handled"}

    # Register utility endpoints
    api_registry.register_router("utility", api_router, "/api")

    # Include the API router in the main app
    app.include_router(api_router, prefix="/api")

    # Include WebSocket router
    app.include_router(websocket_router)

    logger.info("API routes configured")


def add_static_files(app: FastAPI) -> None:
    """Mount static file serving."""
    # Mount static files for frontend (using root static directory)
    static_dir = "static"
    if os.path.exists(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
        logger.info(f"Static files mounted from {static_dir}")
    else:
        logger.warning(
            f"Static directory {static_dir} not found - skipping static file mounting"
        )


def add_utility_routes(app: FastAPI) -> None:
    """Add utility routes that don't fit in the API structure."""

    @app.get("/.well-known/appspecific/com.chrome.devtools.json")
    async def chrome_devtools_json():
        """
        Handles the request for /.well-known/appspecific/com.chrome.devtools.json
        to prevent 404 errors in Chrome/Edge developer console.
        """
        from fastapi.responses import JSONResponse
from src.constants.network_constants import NetworkConstants, ServiceURLs

        return JSONResponse(status_code=200, content={})


def create_app() -> FastAPI:
    """
    Application factory function that creates and configures the FastAPI application.

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    logger.info("Creating FastAPI application...")

    # Create FastAPI app with lifespan manager
    app = FastAPI(lifespan=lambda app: create_lifespan_manager(app))

    # Configure the application
    add_middleware(app)
    add_api_routes(app)
    add_static_files(app)
    add_utility_routes(app)

    # Add enhanced error handlers for developer mode
    @app.exception_handler(404)
    async def not_found_handler(request, exc):
        return await enhanced_404_handler(request, exc)

    @app.exception_handler(405)
    async def method_not_allowed_handler(request, exc):
        return await enhanced_405_handler(request, exc)

    logger.info("FastAPI application created and configured")
    return app


# Create the app instance for uvicorn
app = create_app()