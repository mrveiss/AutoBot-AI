"""
Application Factory for AutoBot FastAPI Backend

This module implements the Application Factory Pattern to create and configure 
the FastAPI application instance, keeping main.py clean and focused.
"""

import os
import asyncio
import logging
import redis
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import APIRouter
from typing import List

# Import centralized configuration
from src.config import config as global_config_manager
from src.utils.redis_client import get_redis_client

# Import core components
from src.orchestrator import Orchestrator
from src.knowledge_base import KnowledgeBase
from src.diagnostics import Diagnostics
from src.security_layer import SecurityLayer
from src.voice_interface import VoiceInterface
from src.chat_history_manager import ChatHistoryManager

# Import API routers
from backend.api.chat import router as chat_router
from backend.api.system import router as system_router
from backend.api.settings import router as settings_router
from backend.api.prompts import router as prompts_router
from backend.api.knowledge import router as knowledge_router
from backend.api.llm import router as llm_router
from backend.api.redis import router as redis_router
from backend.api.voice import router as voice_router
from backend.api.agent import router as agent_router
from backend.api.files import router as files_router
from backend.api.websockets import router as websocket_router
from backend.api.developer import router as developer_router, api_registry, enhanced_404_handler, enhanced_405_handler

logger = logging.getLogger(__name__)

async def _check_redis_modules(redis_host: str, redis_port: int) -> bool:
    """Checks if RediSearch module is loaded in Redis."""
    try:
        resolved_host = redis_host
        if redis_host == "host.docker.internal":
            try:
                resolved_host = socket.gethostbyname(redis_host)
                logger.info(f"Resolved host.docker.internal to IP: {resolved_host}")
            except socket.gaierror as e:
                logger.error(f"Failed to resolve host.docker.internal: {e}")
                resolved_host = redis_host

        r = get_redis_client()
        if r is None:
            logger.error("Could not get Redis client from centralized utility")
            return False
        
        try:
            # Test basic connection first
            r.ping()
            logger.info(f"Successfully connected to Redis at {resolved_host}:{redis_port}")
            
            # Try to get client info with proper error handling
            try:
                client_info = r.client_list()
                logger.info(f"Redis client info retrieved successfully")
            except Exception as e:
                logger.warning(f"Could not get client info from Redis: {e}")
                client_info = []
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}")
            return False

        try:
            # Try to get module list - this may fail on some Redis configurations
            modules = r.module_list()
            if isinstance(modules, list):
                module_names = [m.get('name', '') for m in modules] if modules else []
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
            # Return True anyway since basic Redis connection works
            return True
            
    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis at {redis_host}:{redis_port} for module check: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking Redis modules: {e}")
        return False

async def _initialize_core_components(app: FastAPI) -> None:
    """Initialize all core application components."""
    logger.debug("Initializing core components...")
    
    try:
        app.state.orchestrator = Orchestrator()
        logger.info("Orchestrator initialized and stored in app.state")
        
        app.state.knowledge_base = KnowledgeBase()
        logger.info("KnowledgeBase initialized and stored in app.state")
        
        app.state.diagnostics = Diagnostics()
        logger.info("Diagnostics initialized and stored in app.state")
        
        app.state.voice_interface = VoiceInterface()
        logger.info("VoiceInterface initialized and stored in app.state")
        
        app.state.security_layer = SecurityLayer()
        logger.info("SecurityLayer initialized and stored in app.state")
        
        logger.info("Core components (Orchestrator, KB, Diagnostics, Voice, Security) initialized")
        
        # Verify components are accessible
        logger.debug(f"Orchestrator in app.state: {app.state.orchestrator is not None}")
        logger.debug(f"Diagnostics in app.state: {app.state.diagnostics is not None}")
        logger.debug(f"KnowledgeBase in app.state: {app.state.knowledge_base is not None}")
        logger.debug(f"VoiceInterface in app.state: {app.state.voice_interface is not None}")
        logger.debug(f"SecurityLayer in app.state: {app.state.security_layer is not None}")
        
    except Exception as e:
        logger.error(f"Error initializing core components: {e}", exc_info=True)
        raise

async def _initialize_orchestrator(app: FastAPI) -> None:
    """Initialize the orchestrator with Redis tasks if needed."""
    logger.debug("Starting Orchestrator startup...")
    
    async def safe_redis_task_wrapper(task_name, coro):
        """Wrapper for Redis background tasks with error handling"""
        try:
            await coro
        except Exception as e:
            logger.error(f"Redis background task '{task_name}' failed: {e}", exc_info=True)
            logger.warning(f"Redis task '{task_name}' will be retried in 30 seconds...")
            await asyncio.sleep(30)
            # Could implement retry logic here if needed

    try:
        await app.state.orchestrator.startup()
        if app.state.orchestrator.task_transport_type == "redis" and app.state.orchestrator.redis_client:
            logger.info("Enabling Redis background tasks for autonomous operation...")
            
            # Create background tasks with enhanced error handling
            command_approval_task = asyncio.create_task(
                safe_redis_task_wrapper(
                    "command_approvals_listener", 
                    app.state.orchestrator._listen_for_command_approvals()
                )
            )
            
            worker_capabilities_task = asyncio.create_task(
                safe_redis_task_wrapper(
                    "worker_capabilities_listener", 
                    app.state.orchestrator._listen_for_worker_capabilities()
                )
            )
            
            # Store task references for monitoring and cleanup
            app.state.background_tasks = [command_approval_task, worker_capabilities_task]
            
            logger.info("Redis background tasks successfully enabled and monitoring initiated")
        else:
            logger.info("Redis background tasks skipped - using local task transport or Redis unavailable")
            app.state.background_tasks = []
            
    except Exception as e:
        logger.error(f"Error during orchestrator startup: {e}", exc_info=True)
        # Ensure background_tasks is initialized even on failure
        app.state.background_tasks = []
        # Log and allow the app to potentially continue in a degraded state
    
    logger.debug("Orchestrator startup completed")

async def _initialize_knowledge_base(app: FastAPI) -> None:
    """Initialize the knowledge base asynchronously."""
    logger.debug("Initializing KnowledgeBase...")
    
    try:
        await app.state.knowledge_base.ainit()
        logger.info("KnowledgeBase ainit() called during startup")
    except Exception as e:
        logger.error(f"Error during KnowledgeBase initialization: {e}", exc_info=True)
        logger.warning("KnowledgeBase initialization failed, but continuing startup...")
    
    logger.debug("KnowledgeBase initialized")

async def _initialize_chat_history_manager(app: FastAPI) -> None:
    """Initialize the chat history manager with Redis configuration."""
    logger.debug("Initializing ChatHistoryManager...")
    
    redis_config = global_config_manager.get_redis_config()
    use_redis = redis_config.get('enabled', False)
    redis_host = redis_config.get('host', 'localhost')
    redis_port = redis_config.get('port', 6379)
    
    logger.info(f"Redis configuration loaded: enabled={use_redis}, host={redis_host}, port={redis_port}")

    app.state.chat_history_manager = ChatHistoryManager(
        history_file=global_config_manager.get_nested('data.chat_history_file', "data/chat_history.json"),
        use_redis=use_redis,
        redis_host=redis_host,
        redis_port=redis_port
    )
    
    logger.info("ChatHistoryManager initialized")
    logger.debug(f"ChatHistoryManager in app.state: {app.state.chat_history_manager is not None}")

async def _initialize_redis_client(app: FastAPI) -> None:
    """Initialize the main Redis client for the application."""
    logger.debug("Initializing main Redis client...")
    
    redis_config = global_config_manager.get_redis_config()
    redis_host = redis_config.get('host', 'localhost')
    redis_port = redis_config.get('port', 6379)
    
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
        await _check_redis_modules(redis_config.get('host', 'localhost'), redis_config.get('port', 6379))
        
        # Initialize remaining components
        await _initialize_knowledge_base(app)
        await _initialize_chat_history_manager(app)
        await _initialize_redis_client(app)
        
        logger.info("Application startup completed successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}", exc_info=True)
        raise
    
    yield
    
    # Shutdown events
    logger.info("Application lifespan shutdown initiated")

def add_middleware(app: FastAPI) -> None:
    """Add middleware to the FastAPI application."""
    # Enable CORS for frontend on multiple ports using config
    backend_config = global_config_manager.get_backend_config()
    cors_origins = backend_config.get('cors_origins', [])
    
    # Use fallback if cors_origins is empty (since get() returns [] when key exists but is empty)
    if not cors_origins:
        cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    logger.info(f"CORS middleware added with origins: {cors_origins}")

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        
        # Remove potentially problematic headers
        headers_to_remove = ["content-security-policy", "x-xss-protection", "X-Frame-Options", "Expires"]
        for header in headers_to_remove:
            if header in response.headers:
                del response.headers[header]

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
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
        (files_router, "/files", ["files"], "files"),
        (developer_router, "/developer", ["developer"], "developer")
    ]
    
    for router, prefix, tags, name in routers_config:
        api_router.include_router(router, prefix=prefix, tags=tags)
        # Register router in API registry for developer mode
        api_registry.register_router(name, router, f"/api{prefix}")
    
    # Add utility endpoints
    @api_router.get("/hello")
    async def hello_world():
        return {"message": "Hello from AutoBot backend!"}

    @api_router.get("/version")
    async def get_version():
        return {
            "version_no": "1.0.0",
            "version_time": "2025-06-18 20:00 UTC"
        }

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
        logger.warning(f"Static directory {static_dir} not found - skipping static file mounting")

def add_utility_routes(app: FastAPI) -> None:
    """Add utility routes that don't fit in the API structure."""
    @app.get("/.well-known/appspecific/com.chrome.devtools.json")
    async def chrome_devtools_json():
        """
        Handles the request for /.well-known/appspecific/com.chrome.devtools.json
        to prevent 404 errors in Chrome/Edge developer console.
        """
        from fastapi.responses import JSONResponse
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
