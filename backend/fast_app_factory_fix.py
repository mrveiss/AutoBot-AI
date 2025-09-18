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
from pydantic import BaseModel
import aioredis
import redis.asyncio as redis_async
from backend.utils.llm_config_sync import sync_llm_configuration

# Response models
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    components: Dict[str, str]

# Create FastAPI app with minimal config
app = FastAPI(
    title="AutoBot Backend API",
    description="AutoBot Backend with Fast Startup",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
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

# Initialize app state with minimal setup
app.state.config = {}
app.state.chat_history_manager = None
app.state.knowledge_base = None
app.state.redis_client = None

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
        self.sessions = {}

    async def save_session(self, session_id: str, data: dict):
        self.sessions[session_id] = data
        return {"status": "success"}

# Initialize minimal components
report_startup_progress("components", "Initializing minimal components", 30, "🔧")

# Set up minimal chat history manager
app.state.chat_history_manager = MinimalChatHistoryManager()

# Knowledge base will be initialized on first use
report_startup_progress("knowledge_base", "Deferred knowledge base initialization", 50, "📚")

# Router configurations - critical APIs only for fast startup
routers_config = [
    # System APIs - highest priority
    ("backend.api.system", "/api"),

    # Settings and configuration APIs
    ("backend.api.settings", "/api/settings"),

    # LLM APIs - critical for settings page
    ("backend.api.llm", "/api/llm"),

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
    ("backend.api.monitoring", "/api"),
    ("backend.api.analytics", "/api"),  # Enhanced analytics API for dashboard
    ("backend.api.batch", "/api"),
    ("backend.api.service_monitor", "/api"),
    ("backend.api.phase9_monitoring", "/api"),
    ("backend.api.intelligent_agent", "/api"),

    # Additional APIs that exist
    ("backend.api.terminal", "/api"),
    ("backend.api.files", "/api"),
    ("backend.api.auth", "/api/auth"),

    # Enterprise Features API - Phase 4
    ("backend.api.enterprise_features", "/api/enterprise"),
    ("backend.api.orchestration", "/api/orchestration"),
    ("backend.api.phase_management", "/api/phase"),
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
                logger.info("✅ Startup validation completed successfully")

            if validation_result.warnings:
                logger.warning(f"⚠️  Startup validation found {len(validation_result.warnings)} warnings")
                for warning in validation_result.warnings:
                    logger.warning(f"  - {warning}")

        except Exception as e:
            logger.warning(f"⚠️  Startup validation failed to run: {e}")

        # Step 2: Redis connection
        await init_redis_connection(app.state)

        # Step 3: Run LLM config sync in background (non-blocking)
        try:
            asyncio.create_task(sync_llm_configuration())
            logger.info("✅ LLM config sync started in background")
        except Exception as e:
            logger.warning(f"⚠️  LLM config sync failed: {e}")

    except Exception as e:
        logger.warning(f"⚠️  Background initialization partial failure: {e}")

# Background initialization will be handled by startup event

# Knowledge base factory with force refresh capability
async def get_or_create_knowledge_base(app, force_refresh=False):
    """Get or create knowledge base instance with optional force refresh"""
    if force_refresh or app.state.knowledge_base is None:
        try:
            from src.knowledge_base import KnowledgeBase
            logger.info("Creating fresh knowledge base instance")
            app.state.knowledge_base = KnowledgeBase()
            # Wait for async initialization
            await asyncio.sleep(2)
            return app.state.knowledge_base
        except Exception as e:
            logger.error(f"Failed to create knowledge base: {e}")
            return None
    return app.state.knowledge_base

# Final progress report
report_startup_progress("startup_complete", "Fast backend ready", 100, "✅")

if __name__ == "__main__":
    import uvicorn

    # Run the server
    try:
        backend_host = config.get_host('backend')
        backend_port = config.get_port('backend')
        logger.info(f"🚀 Starting FastAPI server on {backend_host}:{backend_port}")
        uvicorn.run(
            app,
            host=backend_host,
            port=backend_port,
            log_level="info",
            access_log=True,
            reload=False
        )
    except KeyboardInterrupt:
        logger.info("🛑 Server shutdown requested")
    except Exception as e:
        logger.error(f"❌ Server startup failed: {e}")
        sys.exit(1)