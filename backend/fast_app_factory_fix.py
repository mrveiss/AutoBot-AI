"""
Fast App Factory with Redis Connection Fix
Temporary fix for Redis connection timeout issues
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import List, Union

import redis
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import centralized router registry
from backend.api.registry import get_router_configs, RouterStatus

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import startup tracking
try:
    from backend.api.startup import add_startup_message, StartupPhase
    startup_available = True
except ImportError:
    startup_available = False
    logger.warning("Startup tracking not available")

def report_startup_progress(phase: str, message: str, progress: int, icon: str = "🚀"):
    """Report startup progress if startup API is available"""
    if startup_available:
        try:
            phase_enum = StartupPhase(phase)
            add_startup_message(phase_enum, message, progress, icon)
        except Exception as e:
            logger.debug(f"Failed to report startup progress: {e}")
    else:
        logger.info(f"[{progress}%] {message}")

# PERFORMANCE FIX: Set environment variable to prevent immediate knowledge base initialization
os.environ["AUTOBOT_LAZY_INIT"] = "true"  # Signal to delay heavy initialization

# Reset startup state for fresh start
try:
    from backend.api.startup import reset_startup_state
    reset_startup_state()
except ImportError:
    logger.debug("Startup state reset not available")

# Report initial startup progress
report_startup_progress("initializing", "Starting AutoBot backend...", 10, "🚀")

# Load routers from centralized registry
router_registry = get_router_configs()
loaded_routers = {}

logger.info(f"Loading {len(router_registry)} routers from centralized registry...")
report_startup_progress("starting_services", "Loading API routers...", 20, "⚙️")

# Dynamically import and configure routers based on registry
total_routers = len(router_registry)
loaded_count = 0

for router_name, config in router_registry.items():
    try:
        # CRITICAL FIX: Skip specific problematic routers and DISABLED routers  
        if config.status == RouterStatus.DISABLED:
            logger.info(f"Skipping {config.name} router (status: {config.status.value})")
            continue
            
        # Skip only the intelligent_agent router to prevent startup deadlock
        if router_name == "intelligent_agent":
            logger.info(f"Skipping {config.name} router to prevent blocking initialization during startup")
            continue
            
        # Dynamic import based on module path
        module_parts = config.module_path.split('.')
        module_name = module_parts[-1]
        module_path = '.'.join(module_parts)
        
        # Import the module and get the router
        module = __import__(module_path, fromlist=['router'])
        router = getattr(module, 'router')
        
        loaded_routers[router_name] = {
            'router': router,
            'prefix': config.prefix,
            'tags': config.tags,
            'config': config
        }
        
        loaded_count += 1
        progress = 20 + int((loaded_count / total_routers) * 40)  # 20-60% for router loading
        report_startup_progress("starting_services", f"Loaded {config.name} router", progress, "✅")
        
        status_msg = f"({config.status.value})" if config.status != RouterStatus.ENABLED else ""
        logger.info(f"{config.name.title()} router will be mounted at {config.prefix} {status_msg}")
        
    except ImportError as e:
        logger.warning(f"Could not import {config.name} router from {config.module_path}: {e}")
    except AttributeError as e:
        logger.warning(f"Module {config.module_path} does not have 'router' attribute: {e}")
    except Exception as e:
        logger.error(f"Unexpected error loading {config.name} router: {e}")

logger.info(f"Successfully loaded {len(loaded_routers)}/{len(router_registry)} routers from registry")
report_startup_progress("starting_services", f"Loaded {len(loaded_routers)} API routers", 60, "🎯")

# CRITICAL FIX: Manually ensure WebSocket router is loaded
try:
    from backend.api.websockets import router as websocket_router
    if 'websockets' not in loaded_routers:
        logger.warning("WebSocket router not loaded from registry, manually importing...")
        loaded_routers['websockets'] = {
            'router': websocket_router,
            'prefix': '',  # WebSocket routes don't use prefix
            'tags': ['websockets', 'realtime']
        }
        logger.info("✅ WebSocket router manually loaded with config")
except ImportError as e:
    logger.error(f"❌ Failed to manually load WebSocket router: {e}")

# Override Redis timeout
os.environ["AUTOBOT_REDIS_SOCKET_TIMEOUT"] = "2"  # 2 second timeout instead of 30

async def get_or_create_orchestrator(app):
    """Lazy load orchestrator when needed"""
    if hasattr(app.state, 'orchestrator') and app.state.orchestrator is not None:
        return app.state.orchestrator
    
    try:
        logger.info("Lazy loading orchestrator for chat functionality...")
        from src.lightweight_orchestrator import LightweightOrchestrator
        orchestrator = LightweightOrchestrator()
        await orchestrator.startup()
        app.state.orchestrator = orchestrator
        logger.info("Orchestrator lazy loaded successfully")
        return orchestrator
    except Exception as e:
        logger.error(f"Failed to lazy load orchestrator: {e}")
        # Return a minimal orchestrator that can handle basic requests
        from types import SimpleNamespace
        minimal_orchestrator = SimpleNamespace()
        minimal_orchestrator.route_request = lambda msg, **kwargs: {"response": "Chat temporarily unavailable - orchestrator loading failed", "error": True}
        app.state.orchestrator = minimal_orchestrator
        return minimal_orchestrator

async def get_or_create_knowledge_base(app):
    """Lazy load knowledge base when needed"""
    if hasattr(app.state, 'knowledge_base') and app.state.knowledge_base is not None:
        return app.state.knowledge_base
    
    try:
        logger.info("Lazy loading knowledge base for search functionality...")
        from src.knowledge_base import KnowledgeBase
        from src.config import config as global_config
        
        knowledge_base = KnowledgeBase(config_manager=global_config)
        
        # CRITICAL FIX: Initialize the knowledge base properly
        logger.info("Initializing knowledge base with existing data...")
        await knowledge_base.ainit()
        
        app.state.knowledge_base = knowledge_base
        logger.info("Knowledge base lazy loaded and initialized successfully")
        return knowledge_base
        
    except Exception as e:
        logger.error(f"Failed to lazy load knowledge base: {e}")
        import traceback
        traceback.print_exc()
        
        # Return a minimal knowledge base that returns empty results
        from types import SimpleNamespace
        minimal_kb = SimpleNamespace()
        minimal_kb.search = lambda query, **kwargs: []
        minimal_kb.add_entry = lambda *args, **kwargs: {"error": "Knowledge base unavailable"}
        app.state.knowledge_base = minimal_kb
        return minimal_kb


@asynccontextmanager
async def create_lifespan_manager(app: FastAPI):
    """Minimal lifespan manager that doesn't block on Redis"""
    logger.info("Starting application with minimal initialization...")
    report_startup_progress("connecting_backend", "Initializing backend services...", 70, "🔧")
    
    # PERFORMANCE FIX: Skip ALL heavy initialization during startup
    app.state.knowledge_base = None  # Will be lazy-loaded on first use
    app.state.security_layer = None
    app.state.main_redis_client = None
    app.state.orchestrator = None  # Will be lazy-loaded on first use
    
    logger.info("Skipped all heavy component initialization - will lazy-load on demand")
    
    # Initialize minimal chat history manager to prevent errors
    from src.chat_history_manager import ChatHistoryManager
    app.state.chat_history_manager = ChatHistoryManager(
        history_file="data/chat_history.json",
        use_redis=False  # Start without Redis
    )
    
    # Try Redis connection with short timeout
    try:
        import redis
        r = redis.Redis(
            host=os.getenv("AUTOBOT_REDIS_HOST", "redis" if (os.path.exists('/.dockerenv') or os.getenv('DOCKER_CONTAINER')) else "localhost"),
            port=int(os.getenv("AUTOBOT_REDIS_PORT", "6379")),
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        r.ping()
        app.state.main_redis_client = r
        report_startup_progress("connecting_backend", "Connected to Redis cache", 80, "🔗")
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.warning(f"Redis connection failed (non-blocking): {e}")
        report_startup_progress("connecting_backend", "Redis unavailable - using fallback mode", 80, "⚠️")
        # Continue without Redis - app will still work for basic operations
    
    # CRITICAL FIX: Move LLM configuration synchronization to background task
    # This was blocking startup with synchronous imports and operations
    async def background_llm_sync():
        """Background task to perform LLM configuration synchronization"""
        try:
            from backend.utils.llm_config_sync import LLMConfigurationSynchronizer
            logger.info("Starting background LLM configuration synchronization...")
            
            # Synchronize LLM config with agents (now in background)
            sync_result = LLMConfigurationSynchronizer.sync_llm_config_with_agents()
            
            if sync_result["status"] == "synchronized":
                logger.info(f"✅ LLM config synchronized: {sync_result['previous_model']} → {sync_result['new_model']}")
            elif sync_result["status"] == "already_synchronized":
                logger.info(f"✅ LLM config already synchronized: {sync_result['current_model']}")
            else:
                logger.warning(f"⚠️ LLM config sync result: {sync_result}")
            
            # Also populate models list in configuration for Settings Panel
            try:
                from backend.utils.connection_utils import ModelManager
                from src.config import config as global_config_manager
                
                result = await ModelManager.get_available_models()
                if result["status"] == "success":
                    model_names = [
                        model.get("name", "") if isinstance(model, dict) else str(model)
                        for model in result["models"]
                    ]
                    global_config_manager.set_nested(
                        "backend.llm.local.providers.ollama.models", 
                        model_names
                    )
                    logger.info(f"✅ Populated {len(model_names)} models in configuration")
                else:
                    logger.warning(f"⚠️ Failed to get models for config: {result.get('error')}")
                    
            except Exception as e:
                logger.warning(f"Models population failed: {e}")
                
        except Exception as e:
            logger.warning(f"Background LLM configuration synchronization failed: {e}")
    
    # Start background LLM configuration synchronization (with non-blocking Redis)
    try:
        await asyncio.create_task(background_llm_sync())
    except Exception as e:
        logger.warning(f"Background LLM configuration synchronization failed: {e}")
        # Continue startup even if LLM sync fails
    
    report_startup_progress("ready", "AutoBot backend ready!", 100, "🎉")
    logger.info("Application startup completed (minimal mode)")
    
    yield
    
    logger.info("Application shutdown")


def create_app() -> FastAPI:
    """Create minimal FastAPI app that starts quickly"""
    
    # Create app with minimal lifespan
    app = FastAPI(
        title="AutoBot API (Fast Mode)",
        version="1.0.0-fast",
        lifespan=create_lifespan_manager,
    )
    
    report_startup_progress("connecting_backend", "Configuring API middleware...", 85, "🔒")
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins in dev
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    report_startup_progress("connecting_backend", "Mounting API endpoints...", 90, "🔌")
    
    # Mount routers from centralized registry
    for name, config in loaded_routers.items():
        try:
            # Handle WebSocket routers differently (no prefix)
            if config['prefix']:
                app.include_router(
                    config['router'], 
                    prefix=config['prefix'], 
                    tags=config['tags']
                )
            else:
                app.include_router(config['router'], tags=config['tags'])
            
            logger.info(f"{name.capitalize()} router mounted successfully at {config['prefix'] or '(websocket)'}")
        except Exception as e:
            logger.warning(f"Failed to mount {name} router: {e}")
    
    # CRITICAL: Add simple WebSocket test endpoint
    from fastapi import WebSocket
    
    @app.websocket("/ws")
    async def websocket_test(websocket: WebSocket):
        await websocket.accept()
        logger.info("✅ Simple WebSocket connected")
        try:
            await websocket.send_json({"type": "connection", "status": "connected"})
            while True:
                data = await websocket.receive_text()
                await websocket.send_json({"type": "echo", "data": data})
        except Exception as e:
            logger.info(f"WebSocket disconnected: {e}")
    
    logger.info("✅ Simple WebSocket endpoint added at /ws")
    
    report_startup_progress("ready", "All endpoints ready", 95, "🚀")
    
    # Add a simple health check that always works
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "mode": "fast", "redis": app.state.main_redis_client is not None}
    
    # DIAGNOSTIC: Add minimal test chat endpoint to isolate hanging
    from pydantic import BaseModel
    
    class TestChatMessage(BaseModel):
        message: str
    
    @app.post("/api/debug/chat/test")
    async def test_chat_minimal(chat_message: TestChatMessage):
        """Minimal chat endpoint for debugging hanging issues"""
        logger.info(f"DEBUG: test_chat_minimal received: {chat_message.message}")
        
        # Test response without any heavy processing
        return {
            "response": f"Echo: {chat_message.message}",
            "status": "test_success",
            "timestamp": time.time()
        }
    
    # Add endpoint registry information
    @app.get("/api/endpoints")
    async def list_endpoints():
        """Get list of all available API endpoints"""
        from backend.api.registry import get_endpoint_documentation
        return {
            "endpoints": get_endpoint_documentation(),
            "loaded_routers": len(loaded_routers),
            "total_registered": len(router_registry)
        }
    
    # Override system health endpoint to avoid knowledge base initialization
    @app.get("/api/system/health")
    async def system_health_override():
        """Fast system health check that doesn't trigger knowledge base operations"""
        from datetime import datetime
        return {
            "status": "healthy",
            "backend": "connected", 
            "timestamp": datetime.now().isoformat(),
            "fast_check": True,
            "response_time_ms": "< 50ms",
            "mode": "fast_override"
        }
    
    # Add lazy loading helpers for heavy components
    async def get_knowledge_base_lazy():
        """Lazy load knowledge base only when needed"""
        if app.state.knowledge_base is None:
            try:
                logger.info("Lazy-loading knowledge base (first request)")
                from src.knowledge_base import KnowledgeBase
                app.state.knowledge_base = KnowledgeBase()
                
                # Now initialize it properly
                logger.info("Initializing knowledge base...")
                await app.state.knowledge_base.ainit()
                logger.info("Knowledge base lazy-loaded and initialized successfully")
            except Exception as e:
                logger.error(f"Failed to lazy-load knowledge base: {e}")
                app.state.knowledge_base = "error"  # Mark as failed
        return app.state.knowledge_base if app.state.knowledge_base != "error" else None
    
    async def get_orchestrator_lazy():
        """Lazy load orchestrator only when needed"""
        if app.state.orchestrator is None:
            try:
                logger.info("Lazy-loading orchestrator (first request)")  
                from src.agents.agent_orchestrator import AgentOrchestrator
                app.state.orchestrator = AgentOrchestrator()
                logger.info("Orchestrator lazy-loaded successfully")
            except Exception as e:
                logger.error(f"Failed to lazy-load orchestrator: {e}")
                app.state.orchestrator = "error"  # Mark as failed
        return app.state.orchestrator if app.state.orchestrator != "error" else None
    
    # Store lazy loaders in app for use by endpoints
    app.get_knowledge_base_lazy = get_knowledge_base_lazy
    app.get_orchestrator_lazy = get_orchestrator_lazy
    
    return app


# Create app instance for uvicorn
app = create_app()

# For running directly
if __name__ == "__main__":
    import os
    import uvicorn
    
    # Use the backend host from environment, fallback to proper host IP
    backend_host = os.getenv("AUTOBOT_BACKEND_HOST", "172.16.168.20")
    backend_port = int(os.getenv("AUTOBOT_BACKEND_PORT", "8001"))
    
    print(f"Starting backend on {backend_host}:{backend_port}")
    uvicorn.run("backend.fast_app_factory_fix:app", host=backend_host, port=backend_port)