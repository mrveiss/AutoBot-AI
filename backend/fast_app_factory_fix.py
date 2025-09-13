#!/usr/bin/env python3
"""
FastAPI Backend with Optimizations
Created for AutoBot - Fast startup with minimal dependencies
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging immediately
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Quick startup progress tracker
def report_startup_progress(phase: str, message: str, progress: int, emoji: str = "⏳"):
    """Report startup progress"""
    logger.info(f"Startup: [{phase}] {emoji} {message} ({progress}%)")

# Health check model
class HealthResponse(BaseModel):
    status: str
    mode: str
    timestamp: datetime
    redis: bool
    ollama: str
    chat_manager: bool

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan with fast startup and graceful shutdown"""
    
    logger.info("🚀 Starting AutoBot Fast Backend...")
    
    # Phase 1: Minimal Redis setup (with timeout)
    report_startup_progress("connecting_backend", "Connecting to Redis (with timeout)", 10, "📡")
    
    try:
        from src.utils.redis_immediate_test import test_redis_connection_immediate
        redis_available = await asyncio.wait_for(test_redis_connection_immediate(), timeout=2.0)
        app.state.redis_available = redis_available
        if redis_available:
            report_startup_progress("connecting_backend", "Redis connected", 25, "✅")
        else:
            report_startup_progress("connecting_backend", "Redis unavailable - continuing", 25, "⚠️")
    except Exception as e:
        logger.warning(f"⚠️  Redis connection failed (continuing without Redis): {e}")
        app.state.redis_available = False
        report_startup_progress("connecting_backend", "Redis unavailable - continuing", 25, "⚠️")
    
    # Phase 2: Minimal Chat History Manager
    try:
        from src.chat_history_manager import ChatHistoryManager
        app.state.chat_history_manager = ChatHistoryManager(mode='fast')
        logger.info("✅ Initialized Chat History Manager")
        report_startup_progress("connecting_backend", "Chat manager initialized", 40, "💬")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Chat History Manager: {e}")
        # Create fallback chat manager
        app.state.chat_history_manager = type('FallbackChatManager', (), {
            'save_session': lambda *args, **kwargs: True,
            'get_session_history': lambda *args, **kwargs: [],
            'create_new_session': lambda *args, **kwargs: {"chat_id": "fallback", "status": "created"}
        })()
        report_startup_progress("connecting_backend", "Using fallback chat manager", 40, "⚠️")
    
    # Background LLM config sync (don't block startup)
    def background_llm_sync():
        """Background task to sync LLM configuration"""
        try:
            from src.utils.llm_config_sync import LLMConfigurationSynchronizer
            logger.info("🔄 Starting background LLM config synchronization...")
            asyncio.create_task(LLMConfigurationSynchronizer.full_synchronization())
            logger.info("✅ LLM config sync started in background")
        except Exception as e:
            logger.error(f"❌ Background LLM config sync failed: {e}")
    
    # Start background sync task
    task = asyncio.create_task(asyncio.to_thread(background_llm_sync))
    
    report_startup_progress("ready", "Fast backend ready", 100, "✅")
    logger.info("✅ AutoBot Fast Backend startup completed")
    
    yield  # Application runs
    
    # Cleanup on shutdown
    logger.info("🛑 Shutting down AutoBot Fast Backend...")
    
    # Cancel background task if still running
    if not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    logger.info("✅ AutoBot Fast Backend shutdown completed")

# Create the FastAPI app with lifespan
app = FastAPI(
    title="AutoBot Fast Backend",
    description="High-performance backend for AutoBot with optimized startup",
    version="2.0.0",
    lifespan=lifespan
)

# Configure CORS
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000", 
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://172.16.168.21:5173",
    "http://172.16.168.20:8001"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info(f"✅ CORS configured for origins: {CORS_ORIGINS}")

# Load routers with LAZY_LOAD pattern
logger.info("Loading router configurations...")

# Router configurations with prefixes
routers_config = [
    # Core system APIs - always needed
    ("backend.api.system", "/api"),
    ("backend.api.health", "/api"), 
    ("backend.api.config", "/api"),
    
    # Settings and configuration APIs - CRITICAL FIX
    ("backend.api.settings", "/api/settings"),
    
    # LLM APIs - critical for settings page
    ("backend.api.llm", "/api/llm"),
    
    # Chat APIs
    ("backend.api.chat", "/api"),
    ("backend.api.async_chat", "/api"),
    
    # Knowledge APIs
    ("backend.api.knowledge", "/api"),
    
    # Other core APIs
    ("backend.api.rum", "/api"),
    ("backend.api.monitoring", "/api"),
    ("backend.api.batch", "/api"),
    ("backend.api.service_monitor", "/api"),
    ("backend.api.phase9_monitoring", "/api"),
    ("backend.api.intelligent_agent", "/api"),
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
    
    # Quick Ollama check
    ollama_status = "unknown"
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.0)) as session:
            async with session.get("http://localhost:11434/api/tags") as response:
                if response.status == 200:
                    ollama_status = "connected"
                else:
                    ollama_status = "disconnected"
    except:
        ollama_status = "disconnected"
    
    return HealthResponse(
        status="ok",
        mode="fast", 
        timestamp=datetime.now(timezone.utc),
        redis=getattr(app.state, 'redis_available', False),
        ollama=ollama_status,
        chat_manager=hasattr(app.state, 'chat_history_manager')
    )

logger.info("🎯 Fast backend application created successfully")

# Main execution
if __name__ == "__main__":
    print("🚀 Starting AutoBot Backend Server on 0.0.0.0:8001")
    
    uvicorn.run(
        "backend.fast_app_factory_fix:app",
        host="0.0.0.0",
        port=8001,
        reload=False,  # Disable reload for faster startup
        log_level="info",
        access_log=False  # Disable access logs for performance
    )