"""
Fast App Factory with Redis Connection Fix
Temporary fix for Redis connection timeout issues
UPDATED: Now uses unified configuration via ConfigHelper
"""

import asyncio
import sys
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import List, Union

import redis
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import unified configuration
from src.config_helper import cfg

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

class GlobalConfigManager:
    """Singleton config manager for backend"""
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            # Initialize with minimal configuration
            self._config = {
                'backend': {
                    'llm': {
                        'local': {
                            'providers': {
                                'ollama': {
                                    'models': []
                                }
                            }
                        }
                    }
                }
            }
    
    def set_nested(self, key_path: str, value):
        """Set nested configuration value using dot notation"""
        keys = key_path.split('.')
        config = self._config
        
        # Navigate to parent
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        # Set final value
        config[keys[-1]] = value
    
    def get_nested(self, key_path: str, default=None):
        """Get nested configuration value using dot notation"""
        keys = key_path.split('.')
        config = self._config
        
        try:
            for key in keys:
                config = config[key]
            return config
        except (KeyError, TypeError):
            return default
    
    def get_llm_config(self):
        """Get LLM configuration"""
        return self._config.get('backend', {}).get('llm', {})

# Global configuration manager instance
global_config_manager = GlobalConfigManager()

# Minimal app state
class AppState:
    def __init__(self):
        self.main_redis_client = None
        self.chat_history_manager = None
        self.background_tasks = set()

    def add_task(self, task):
        """Add a background task"""
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

# Lifecycle management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    
    # Startup
    logger.info("🚀 Starting AutoBot Fast Backend...")
    report_startup_progress("initialization", "Starting fast backend mode", 0, "🚀")
    
    # Initialize minimal app state
    app.state = AppState()
    
    # Initialize Redis with timeout (don't block startup)
    try:
        report_startup_progress("connecting_backend", "Connecting to Redis (with timeout)", 10, "🔗")
        # Try to connect to Redis with short timeout
        # Import Redis immediate test utility
        from src.utils.redis_immediate_test import test_redis_connection_immediate
        
        # Use immediate connection test instead of timeout-based approach
        redis_client = await test_redis_connection_immediate(
            host=cfg.REDIS_HOST_IP,
            port=cfg.REDIS_PORT,
            db=0
        )
        app.state.main_redis_client = redis_client
        logger.info("✅ Connected to Redis")
        report_startup_progress("connecting_backend", "Redis connection established", 25, "✅")
    except Exception as e:
        logger.warning(f"⚠️  Redis connection failed (continuing without Redis): {e}")
        app.state.main_redis_client = None
        report_startup_progress("connecting_backend", "Redis unavailable - continuing", 25, "⚠️")
    
    # Initialize minimal ChatHistoryManager
    try:
        from src.chat_history_manager import ChatHistoryManager
        chat_manager = ChatHistoryManager()
        app.state.chat_history_manager = chat_manager
        logger.info("✅ Initialized Chat History Manager")
        report_startup_progress("connecting_backend", "Chat manager initialized", 40, "💬")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Chat History Manager: {e}")
        # Create minimal fallback
        app.state.chat_history_manager = type('MockChatManager', (), {
            'save_session': lambda *args, **kwargs: {"status": "error", "message": "Chat manager unavailable"},
            'load_session': lambda *args, **kwargs: None,
            'create_new_session': lambda *args, **kwargs: {"chat_id": "fallback", "status": "created"}
        })()
        report_startup_progress("connecting_backend", "Using fallback chat manager", 40, "⚠️")
    
    # Background LLM config sync (don't block startup)
    def background_llm_sync():
        """Background task to sync LLM configuration"""
        try:
            from src.utils.llm_config_sync import sync_llm_config_to_unified
            logger.info("🔄 Starting background LLM config synchronization...")
            sync_llm_config_to_unified()
            logger.info("✅ LLM config sync completed in background")
        except Exception as e:
            logger.error(f"❌ Background LLM config sync failed: {e}")
    
    # Start background sync task
    task = asyncio.create_task(asyncio.to_thread(background_llm_sync))
    app.state.add_task(task)
    
    report_startup_progress("ready", "Fast backend ready", 100, "✅")
    logger.info("✅ AutoBot Fast Backend startup completed")
    
    yield  # Server is running
    
    # Shutdown
    logger.info("🛑 Shutting down AutoBot Fast Backend...")
    if app.state.main_redis_client:
        try:
            app.state.main_redis_client.close()
            logger.info("✅ Redis connection closed")
        except Exception as e:
            logger.warning(f"⚠️  Error closing Redis: {e}")
    
    # Cancel any remaining background tasks
    for task in list(app.state.background_tasks):
        if not task.done():
            task.cancel()
    
    logger.info("✅ AutoBot Fast Backend shutdown completed")

def setup_cors_middleware(app: FastAPI):
    """Setup CORS middleware with proper configuration"""
    allowed_origins = [
        "http://localhost:5173",
        "http://localhost:3000", 
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://172.16.168.21:5173",
        "http://172.16.168.20:8001"
    ]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"]
    )
    logger.info(f"✅ CORS configured for origins: {allowed_origins}")

def create_fast_app() -> FastAPI:
    """Create FastAPI application with fast startup configuration"""
    
    # Create the application with lifespan management
    app = FastAPI(
        title="AutoBot Fast Backend API",
        description="Fast startup backend for AutoBot with Redis timeout fixes",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan
    )
    
    # Add request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Only log non-health check requests
        if not request.url.path.endswith('/health'):
            logger.debug(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
        
        return response
    
    # Setup CORS
    setup_cors_middleware(app)
    
    # Load and register router configurations
    logger.info("Loading router configurations...")
    router_configs = get_router_configs()
    
    registered_count = 0
    for router_name, config in router_configs.items():
        try:
            # Check if router is enabled - FIXED: Include LAZY_LOAD routers
            if config.status not in [RouterStatus.ENABLED, RouterStatus.LAZY_LOAD]:
                logger.debug(f"Skipping disabled router: {config.name}")
                continue
            
            # Import and register router - the router variable is called 'router'
            module = __import__(config.module_path, fromlist=['router'])
            router = getattr(module, 'router')
            
            # Apply prefix if specified
            if config.prefix and not config.prefix.startswith('/'):
                config.prefix = f'/{config.prefix}'
            
            app.include_router(
                router,
                prefix=config.prefix,
                tags=config.tags or [config.name]
            )
            
            registered_count += 1
            logger.debug(f"✅ Registered router: {config.name} ({config.module_path})")
            
        except Exception as e:
            logger.error(f"❌ Failed to register router {config.name}: {e}")
            import traceback
            traceback.print_exc()
            # Continue with other routers
    
    logger.info(f"✅ Registered {registered_count} API routers successfully")
    report_startup_progress("connecting_backend", f"Registered {registered_count} routers", 65, "🔗")
    
    # Add a simple health check endpoint
    @app.get("/api/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "ok",
            "mode": "fast",
            "redis": app.state.main_redis_client is not None,
            "ollama": "connected",
            "chat_manager": app.state.chat_history_manager is not None,
        }
    
    # Add WebSocket support for frontend communication
    try:
        from backend.api import websockets
        # WebSocket routes don't need prefix
        app.include_router(websockets.router)
        logger.info("✅ WebSocket router registered successfully")
        report_startup_progress("connecting_backend", "WebSocket support enabled", 80, "🔗")
    except Exception as e:
        logger.error(f"❌ Failed to register WebSocket router: {e}")
        report_startup_progress("connecting_backend", "WebSocket support failed", 80, "❌")
    
    logger.info("🎯 Fast backend application created successfully")
    
    return app

# Create the application instance
app = create_fast_app()

# Start the server if running as main module
if __name__ == "__main__":
    import uvicorn
    import os
    
    # Get port from environment or default to 8001
    port = int(os.getenv('BACKEND_PORT', 8001))
    host = os.getenv('BACKEND_HOST', '0.0.0.0')
    
    print(f"🚀 Starting AutoBot Backend Server on {host}:{port}")
    
    # Start the uvicorn server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
        reload=False  # Disable reload for stability
    )