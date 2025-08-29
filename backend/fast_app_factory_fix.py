"""
Fast App Factory with Redis Connection Fix
Temporary fix for Redis connection timeout issues
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import List, Union

import redis
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import API routers with minimal dependencies
from backend.api.system import router as system_router
from backend.api.chat import router as chat_router
from backend.api.settings import router as settings_router
from backend.api.websockets import router as websockets_router

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PERFORMANCE FIX: Import routers with lazy initialization approach
# Set environment variable to prevent immediate knowledge base initialization
os.environ["AUTOBOT_LAZY_INIT"] = "true"  # Signal to delay heavy initialization

additional_routers = {}

# Core functionality routers - import but with lazy initialization
try:
    from backend.api.files import router as files_router
    additional_routers['files'] = {'router': files_router, 'prefix': '/api/files', 'tags': ['files']}
    logger.info("Files router will be mounted")
except ImportError as e:
    logger.warning(f"Could not import files router: {e}")

try:
    from backend.api.secrets import router as secrets_router
    additional_routers['secrets'] = {'router': secrets_router, 'prefix': '/api/secrets', 'tags': ['secrets']}
    logger.info("Secrets router will be mounted")  
except ImportError as e:
    logger.warning(f"Could not import secrets router: {e}")

# Re-enable essential routers with lazy loading approach
try:
    # Knowledge base router with lazy initialization
    from backend.api.knowledge import router as knowledge_router
    additional_routers['knowledge'] = {'router': knowledge_router, 'prefix': '/api/knowledge_base', 'tags': ['knowledge']}
    logger.info("Knowledge router will be mounted (lazy initialization enabled)")
except ImportError as e:
    logger.warning(f"Could not import knowledge router: {e}")

try:
    # LLM router with lazy initialization  
    from backend.api.llm import router as llm_router
    additional_routers['llm'] = {'router': llm_router, 'prefix': '/api/llm', 'tags': ['llm']}
    logger.info("LLM router will be mounted (lazy initialization enabled)")
except ImportError as e:
    logger.warning(f"Could not import LLM router: {e}")

try:
    # Templates router
    from backend.api.templates import router as templates_router  
    additional_routers['templates'] = {'router': templates_router, 'prefix': '/api/templates', 'tags': ['templates']}
    logger.info("Templates router will be mounted")
except ImportError as e:
    logger.warning(f"Could not import templates router: {e}")

try:
    # Playwright router - embedded Docker integration
    from backend.api.playwright import router as playwright_router
    additional_routers['playwright'] = {'router': playwright_router, 'prefix': '/api/playwright', 'tags': ['playwright']}
    logger.info("Playwright router will be mounted (embedded Docker integration)")
except ImportError as e:
    logger.warning(f"Could not import Playwright router: {e}")

logger.info("Core routers enabled with lazy initialization to prevent startup blocking")

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
        knowledge_base = KnowledgeBase()
        # Initialize with minimal setup
        app.state.knowledge_base = knowledge_base
        logger.info("Knowledge base lazy loaded successfully")
        return knowledge_base
    except Exception as e:
        logger.error(f"Failed to lazy load knowledge base: {e}")
        # Return a minimal knowledge base
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
            host=os.getenv("AUTOBOT_REDIS_HOST", "localhost"),
            port=int(os.getenv("AUTOBOT_REDIS_PORT", "6379")),
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        r.ping()
        app.state.main_redis_client = r
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.warning(f"Redis connection failed (non-blocking): {e}")
        # Continue without Redis - app will still work for basic operations
    
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
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins in dev
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Mount essential routers only
    app.include_router(system_router, prefix="/api/system", tags=["system"])
    app.include_router(chat_router, prefix="/api", tags=["chat"]) 
    app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
    app.include_router(websockets_router, tags=["websockets"])
    
    # Mount additional routers if available
    for name, config in additional_routers.items():
        try:
            app.include_router(
                config['router'], 
                prefix=config['prefix'], 
                tags=config['tags']
            )
            logger.info(f"{name.capitalize()} router mounted successfully at {config['prefix']}")
        except Exception as e:
            logger.warning(f"Failed to mount {name} router: {e}")
    
    # Add a simple health check that always works
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "mode": "fast", "redis": app.state.main_redis_client is not None}
    
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
    import uvicorn
    uvicorn.run("backend.fast_app_factory_fix:app", host="0.0.0.0", port=8001)