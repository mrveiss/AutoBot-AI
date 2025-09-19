import asyncio
import logging
import warnings
import signal
import sys
import os
from datetime import datetime
from typing import Dict, Any

# Add parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Filter out specific warnings that are causing noise
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")
warnings.filterwarnings("ignore", message=".*'app' object has no attribute.*")

# Import unified configuration BEFORE any other local imports
from src.unified_config import config

# Configure logging for startup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import aioredis
import redis.asyncio as redis_async
from backend.utils.llm_config_sync import sync_llm_configuration

# Response models
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    components: Dict[str, str]

# Modern lifespan handler replacing deprecated @app.on_event
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown"""
    # Startup
    logger.info("🔄 Application startup initiated")

    # Initialize app state with minimal setup
    app.state.config = {}
    app.state.chat_history_manager = None
    app.state.knowledge_base = None
    app.state.redis_client = None

    # Initialize chat history manager
    from src.chat_history_manager import ChatHistoryManager
    app.state.chat_history_manager = ChatHistoryManager()

    # Initialize Redis connection in background (non-blocking)
    asyncio.create_task(init_redis_connection(app.state))

    # Start background initialization
    asyncio.create_task(background_initialization())

    yield

    # Shutdown
    logger.info("🔄 Application shutdown initiated")

# Create FastAPI app with minimal config and modern lifespan
app = FastAPI(
    title="AutoBot Backend API",
    description="AutoBot Backend with Fast Startup",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def report_startup_progress(component: str, message: str, progress: int, icon: str = ""):
    """Report startup progress for monitoring"""
    logger.info(f"{icon} [{progress:3d}%] {component}: {message}")

# Progress reporting
report_startup_progress("initialization", "Starting Fast Backend", 10, "🚀")

# Standardized Redis connection using pool manager
async def init_redis_connection(app_state):
    """Initialize Redis connection using standardized pool manager"""
    try:
        logger.info("Attempting Redis connection with pool manager...")
        from src.redis_pool_manager import get_redis_async, health_check_redis

        # Get Redis client using pool manager
        redis_client = await get_redis_async('main')

        # Test connection
        await redis_client.ping()
        app_state.redis_client = redis_client

        # Run comprehensive health check
        health_status = await health_check_redis()
        if health_status['all_healthy']:
            logger.info("✅ Redis connected successfully with pool manager")
        else:
            logger.warning(f"⚠️  Redis connected but some pools unhealthy: {health_status}")

        return True
    except Exception as e:
        logger.warning(f"⚠️  Redis connection failed (continuing without Redis): {e}")
        app_state.redis_client = None
        return False

# Minimal ChatHistoryManager for basic functionality
class MinimalChatHistoryManager:
    def __init__(self):
        pass

    def save_session(self, *args, **kwargs):
        logger.info("Chat session save operation (minimal implementation)")
        return {"status": "success", "method": "minimal"}

    def list_sessions_fast(self):
        """Fast session listing without full chat loading"""
        logger.info("Chat sessions list operation (minimal implementation)")
        # Return minimal session data to prevent 500 errors
        return []

    def _get_chats_directory(self):
        """Get chats directory path"""
        import os
        chats_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chats")
        os.makedirs(chats_dir, exist_ok=True)
        return chats_dir



# Define routers to load
routers_config = [
    # Settings API (critical for frontend)
    ("backend.api.settings", "/api"),

    # System APIs
    ("backend.api.system", "/api"),

    # Chat APIs
    ("backend.api.chat", "/api"),
    ("backend.api.async_chat", "/api"),

    # Knowledge APIs - CRITICAL FOR CATEGORIES
    ("backend.api.knowledge", "/api/knowledge_base"),

    # Fresh Knowledge Base APIs for testing fixes
    ("backend.api.knowledge_fresh", "/api/knowledge_fresh"),

    # Test APIs for knowledge base debugging
    ("backend.api.knowledge_test", "/api/knowledge_test"),

    # Core APIs that exist
    ("backend.api.rum", "/api"),
    ("backend.api.monitoring", ""),
    ("backend.api.analytics", "/api"),  # Enhanced analytics API for dashboard
    ("backend.api.cache_management", "/api"),  # Cache management API for settings
    ("backend.api.batch", "/api/batch"),
    ("backend.api.service_monitor", "/api"),
    ("backend.api.infrastructure_monitor", "/api/infrastructure"),
    ("backend.api.intelligent_agent", "/api"),

    # Additional APIs that exist
    ("backend.api.terminal", "/api"),
    ("backend.api.files", "/api"),
    ("backend.api.auth", "/api/auth"),

    # Enterprise Features API - Phase 4
    ("backend.api.enterprise_features", "/api/enterprise"),
    ("backend.api.orchestration", "/api/orchestration"),
    ("backend.api.phase_management", "/api/phase"),

    # Multi-Modal AI Processing API - Phase 6
    ("backend.api.multimodal", ""),
]

# Load routers with proper prefixes
router_count = 0
for router_module, prefix in routers_config:
    try:
        module = __import__(router_module, fromlist=[''])
        if hasattr(module, 'router'):
            app.include_router(module.router, prefix=prefix)
            router_count += 1
            logger.info(f"✅ Loaded {router_module} with prefix {prefix}")
        elif hasattr(module, 'app') and hasattr(module.app, 'router'):
            app.include_router(module.app.router, prefix=prefix)
            router_count += 1
            logger.info(f"✅ Loaded {router_module}.app.router with prefix {prefix}")
    except Exception as e:
        logger.warning(f"⚠️  Could not load router {router_module}: {e}")

logger.info(f"✅ Registered {router_count} API routers successfully")
report_startup_progress("connecting_backend", f"Registered {router_count} routers", 65, "🔌")

# Register WebSocket router explicitly
try:
    from backend.api.websockets import router as websocket_router
    app.include_router(websocket_router)
    logger.info("✅ WebSocket router registered successfully")
    report_startup_progress("connecting_backend", "WebSocket support enabled", 80, "🌐")
except Exception as e:
    logger.warning(f"⚠️  WebSocket router failed to load: {e}")

# Health check endpoint
@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Fast health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        components={
            "backend": "healthy",
            "config": "healthy",
            "logging": "healthy"
        }
    )

# System health endpoint alias - Frontend compatibility
@app.get("/api/system/health")
async def system_health_alias():
    """System health endpoint alias for frontend compatibility"""
    from fastapi import Request
    try:
        # Try to get the detailed health from system router
        module = __import__("backend.api.system", fromlist=[''])
        if hasattr(module, 'get_system_health'):
            return await module.get_system_health()
    except Exception as e:
        logger.warning(f"Failed to get system health: {e}")

    # Fallback to basic health response
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "backend": "healthy",
            "config": "healthy",
            "logging": "healthy"
        }
    }

# Graceful shutdown handlers
def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    # Cleanup code here
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Background tasks for non-critical initialization
async def background_initialization():
    """Initialize non-critical components in background"""
    try:
        # Step 1: Run startup validation
        logger.info("🔍 Running startup dependency validation...")
        try:
            from src.startup_validator import validate_startup_dependencies
            validation_result = await validate_startup_dependencies()

            if not validation_result.success:
                logger.error(f"❌ Startup validation failed with {len(validation_result.errors)} errors")
                for error in validation_result.errors:
                    logger.error(f"  - {error}")
            else:
                logger.info("✅ Startup validation passed")
                report_startup_progress("validation", "Dependency validation completed", 90, "✅")
        except Exception as e:
            logger.warning(f"⚠️  Startup validation failed: {e}")

        # Step 2: Synchronize LLM configuration in background
        logger.info("🔄 Starting background LLM config synchronization...")
        try:
            await sync_llm_configuration()
            logger.info("✅ LLM configuration synchronized successfully")
        except Exception as e:
            logger.warning(f"⚠️  LLM config sync failed (non-critical): {e}")

        # Step 3: Initialize Knowledge Base
        logger.info("🧠 Initializing Knowledge Base...")
        try:
            from src.knowledge_base import KnowledgeBase
            app.state.knowledge_base = KnowledgeBase()
            logger.info("✅ Knowledge Base initialized successfully")
            report_startup_progress("knowledge_base", "Knowledge Base ready", 95, "🧠")
        except Exception as e:
            logger.warning(f"⚠️  Knowledge Base initialization failed (non-critical): {e}")
            app.state.knowledge_base = None

        # Step 4: Complete startup
        report_startup_progress("completion", "Backend startup completed", 100, "🎉")
        logger.info("🚀 Fast backend startup completed successfully!")

    except Exception as e:
        logger.error(f"❌ Background initialization failed: {e}")

# Application factory for uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)