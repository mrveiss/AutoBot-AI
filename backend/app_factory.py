import os
import logging
import inspect
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
from pathlib import Path
import json
from contextlib import asynccontextmanager
import redis
import asyncio
import sys

# Add the project root to Python path for absolute imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from contextlib import asynccontextmanager
import uvicorn

from backend.dependencies import (
    get_config,
    get_knowledge_base
)

from src.unified_config_manager import UnifiedConfigManager
from backend.knowledge_factory import get_or_create_knowledge_base
from src.chat_workflow_manager import ChatWorkflowManager
from src.chat_history_manager import ChatHistoryManager
from src.utils.background_llm_sync import BackgroundLLMSync

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
from backend.api.agent_config import router as agent_config_router
from backend.api.intelligent_agent import router as intelligent_agent_router
from backend.api.files import router as files_router
from backend.api.developer import router as developer_router
from backend.api.frontend_config import router as frontend_config_router

# Enhanced routers with optional imports
optional_routers = []

# Try importing optional/enhanced routers
try:
    from backend.api.monitoring import router as monitoring_router
    optional_routers.append((monitoring_router, "/monitoring", ["monitoring"], "monitoring"))
    logging.info("✅ Optional router loaded: monitoring")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: monitoring - {e}")

try:
    from backend.api.terminal import router as terminal_router
    optional_routers.append((terminal_router, "/terminal", ["terminal"], "terminal"))
    logging.info("✅ Optional router loaded: terminal")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: terminal - {e}")

try:
    from backend.api.websockets import router as websockets_router
    # FIXED: No prefix needed - websocket route is already @router.websocket("/ws")
    optional_routers.append((websockets_router, "", ["websockets"], "websockets"))
    logging.info("✅ Optional router loaded: websockets")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: websockets - {e}")

try:
    from backend.api.analytics import router as analytics_router
    optional_routers.append((analytics_router, "/analytics", ["analytics"], "analytics"))
    logging.info("✅ Optional router loaded: analytics")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: analytics - {e}")

try:
    from backend.api.workflow import router as workflow_router
    optional_routers.append((workflow_router, "/workflow", ["workflow"], "workflow"))
    logging.info("✅ Optional router loaded: workflow")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: workflow - {e}")

try:
    from backend.api.batch import router as batch_router
    optional_routers.append((batch_router, "/batch", ["batch"], "batch"))
    logging.info("✅ Optional router loaded: batch")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: batch - {e}")

try:
    from backend.api.advanced_workflow_orchestrator import router as orchestrator_router
    optional_routers.append((orchestrator_router, "/orchestrator", ["orchestrator"], "orchestrator"))
    logging.info("✅ Optional router loaded: orchestrator")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: orchestrator - {e}")

try:
    from backend.api.logs import router as logs_router
    optional_routers.append((logs_router, "/logs", ["logs"], "logs"))
    logging.info("✅ Optional router loaded: logs")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: logs - {e}")

try:
    from backend.api.rum import router as rum_router
    optional_routers.append((rum_router, "/rum", ["rum"], "rum"))
    logging.info("✅ Optional router loaded: rum")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: rum - {e}")

try:
    from backend.api.secrets import router as secrets_router
    optional_routers.append((secrets_router, "/secrets", ["secrets"], "secrets"))
    logging.info("✅ Optional router loaded: secrets")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: secrets - {e}")

try:
    from backend.api.cache import router as cache_router
    optional_routers.append((cache_router, "/cache", ["cache"], "cache"))
    logging.info("✅ Optional router loaded: cache")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: cache - {e}")

try:
    from backend.api.registry import router as registry_router
    optional_routers.append((registry_router, "/registry", ["registry"], "registry"))
    logging.info("✅ Optional router loaded: registry")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: registry - {e}")

try:
    from backend.api.embeddings import router as embeddings_router
    optional_routers.append((embeddings_router, "/embeddings", ["embeddings"], "embeddings"))
    logging.info("✅ Optional router loaded: embeddings")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: embeddings - {e}")

try:
    from backend.api.workflow_automation import router as workflow_automation_router
    optional_routers.append((workflow_automation_router, "/workflow-automation", ["workflow-automation"], "workflow_automation"))
    logging.info("✅ Optional router loaded: workflow_automation")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: workflow_automation - {e}")

try:
    from backend.api.research_browser import router as research_browser_router
    optional_routers.append((research_browser_router, "/research-browser", ["research-browser"], "research_browser"))
    logging.info("✅ Optional router loaded: research_browser")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: research_browser - {e}")

try:
    from backend.api.web_research_settings import router as web_research_settings_router
    optional_routers.append((web_research_settings_router, "/web-research-settings", ["web-research-settings"], "web_research_settings"))
    logging.info("✅ Optional router loaded: web_research_settings")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: web_research_settings - {e}")

try:
    from backend.api.state_tracking import router as state_tracking_router
    optional_routers.append((state_tracking_router, "/state-tracking", ["state-tracking"], "state_tracking"))
    logging.info("✅ Optional router loaded: state_tracking")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: state_tracking - {e}")

try:
    from backend.api.services import router as services_router
    optional_routers.append((services_router, "/services", ["services"], "services"))
    logging.info("✅ Optional router loaded: services")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: services - {e}")

try:
    from backend.api.elevation import router as elevation_router
    optional_routers.append((elevation_router, "/elevation", ["elevation"], "elevation"))
    logging.info("✅ Optional router loaded: elevation")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: elevation - {e}")

try:
    from backend.api.auth import router as auth_router
    optional_routers.append((auth_router, "/auth", ["auth"], "auth"))
    logging.info("✅ Optional router loaded: auth")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: auth - {e}")

try:
    from backend.api.error_monitoring import router as error_monitoring_router
    optional_routers.append((error_monitoring_router, "/errors", ["errors"], "error_monitoring"))
    logging.info("✅ Optional router loaded: error_monitoring")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: error_monitoring - {e}")

try:
    from backend.api.multimodal import router as multimodal_router
    optional_routers.append((multimodal_router, "/multimodal", ["multimodal"], "multimodal"))
    logging.info("✅ Optional router loaded: multimodal")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: multimodal - {e}")

try:
    from backend.api.hot_reload import router as hot_reload_router
    optional_routers.append((hot_reload_router, "/hot-reload", ["hot-reload"], "hot_reload"))
    logging.info("✅ Optional router loaded: hot_reload")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: hot_reload - {e}")

try:
    from backend.api.enterprise_features import router as enterprise_router
    optional_routers.append((enterprise_router, "/enterprise", ["enterprise"], "enterprise"))
    logging.info("✅ Optional router loaded: enterprise")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: enterprise - {e}")

try:
    from backend.api.infrastructure_monitor import router as infrastructure_monitor_router
    optional_routers.append((infrastructure_monitor_router, "/infrastructure", ["infrastructure"], "infrastructure_monitor"))
    logging.info("✅ Optional router loaded: infrastructure_monitor")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: infrastructure_monitor - {e}")

try:
    from backend.api.scheduler import router as scheduler_router
    optional_routers.append((scheduler_router, "/scheduler", ["scheduler"], "scheduler"))
    logging.info("✅ Optional router loaded: scheduler")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: scheduler - {e}")

try:
    from backend.api.templates import router as templates_router
    optional_routers.append((templates_router, "/templates", ["templates"], "templates"))
    logging.info("✅ Optional router loaded: templates")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: templates - {e}")

try:
    from backend.api.sandbox import router as sandbox_router
    optional_routers.append((sandbox_router, "/sandbox", ["sandbox"], "sandbox"))
    logging.info("✅ Optional router loaded: sandbox")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: sandbox - {e}")

try:
    from backend.api.security import router as security_router
    optional_routers.append((security_router, "/security", ["security"], "security"))
    logging.info("✅ Optional router loaded: security")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: security - {e}")

try:
    from backend.api.code_search import router as code_search_router
    optional_routers.append((code_search_router, "/code-search", ["code-search"], "code_search"))
    logging.info("✅ Optional router loaded: code_search")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: code_search - {e}")

try:
    from backend.api.orchestration import router as orchestration_router
    optional_routers.append((orchestration_router, "/orchestration", ["orchestration"], "orchestration"))
    logging.info("✅ Optional router loaded: orchestration")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: orchestration - {e}")

try:
    from backend.api.cache_management import router as cache_management_router
    optional_routers.append((cache_management_router, "/cache-management", ["cache-management"], "cache_management"))
    logging.info("✅ Optional router loaded: cache_management")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: cache_management - {e}")

try:
    from backend.api.llm_optimization import router as llm_optimization_router
    optional_routers.append((llm_optimization_router, "/llm-optimization", ["llm-optimization"], "llm_optimization"))
    logging.info("✅ Optional router loaded: llm_optimization")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: llm_optimization - {e}")

try:
    from backend.api.enhanced_search import router as enhanced_search_router
    optional_routers.append((enhanced_search_router, "/enhanced-search", ["enhanced-search"], "enhanced_search"))
    logging.info("✅ Optional router loaded: enhanced_search")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: enhanced_search - {e}")

try:
    from backend.api.enhanced_memory import router as enhanced_memory_router
    optional_routers.append((enhanced_memory_router, "/enhanced-memory", ["enhanced-memory"], "enhanced_memory"))
    logging.info("✅ Optional router loaded: enhanced_memory")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: enhanced_memory - {e}")

try:
    from backend.api.development_speedup import router as development_speedup_router
    optional_routers.append((development_speedup_router, "/dev-speedup", ["dev-speedup"], "development_speedup"))
    logging.info("✅ Optional router loaded: development_speedup")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: development_speedup - {e}")

try:
    from backend.api.advanced_control import router as advanced_control_router
    optional_routers.append((advanced_control_router, "/advanced-control", ["advanced-control"], "advanced_control"))
    logging.info("✅ Optional router loaded: advanced_control")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: advanced_control - {e}")

try:
    from backend.api.codebase_analytics import router as codebase_analytics_router
    optional_routers.append((codebase_analytics_router, "/codebase-analytics", ["codebase-analytics"], "codebase_analytics"))
    logging.info("✅ Optional router loaded: codebase_analytics")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: codebase_analytics - {e}")

try:
    from backend.api.long_running_operations import router as long_running_operations_router
    optional_routers.append((long_running_operations_router, "/long-running", ["long-running"], "long_running_operations"))
    logging.info("✅ Optional router loaded: long_running_operations")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: long_running_operations - {e}")

try:
    from backend.api.system_validation import router as system_validation_router
    optional_routers.append((system_validation_router, "/system-validation", ["system-validation"], "system_validation"))
    logging.info("✅ Optional router loaded: system_validation")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: system_validation - {e}")

try:
    from backend.api.validation_dashboard import router as validation_dashboard_router
    optional_routers.append((validation_dashboard_router, "/validation-dashboard", ["validation-dashboard"], "validation_dashboard"))
    logging.info("✅ Optional router loaded: validation_dashboard")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: validation_dashboard - {e}")

try:
    from backend.api.llm_awareness import router as llm_awareness_router
    optional_routers.append((llm_awareness_router, "/llm-awareness", ["llm-awareness"], "llm_awareness"))
    logging.info("✅ Optional router loaded: llm_awareness")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: llm_awareness - {e}")

try:
    from backend.api.project_state import router as project_state_router
    optional_routers.append((project_state_router, "/project-state", ["project-state"], "project_state"))
    logging.info("✅ Optional router loaded: project_state")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: project_state - {e}")

try:
    from backend.api.metrics import router as metrics_router
    optional_routers.append((metrics_router, "/metrics", ["metrics"], "metrics"))
    logging.info("✅ Optional router loaded: metrics")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: metrics - {e}")

try:
    from backend.api.startup import router as startup_router
    optional_routers.append((startup_router, "/startup", ["startup"], "startup"))
    logging.info("✅ Optional router loaded: startup")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: startup - {e}")

try:
    from backend.api.phase_management import router as phase_management_router
    optional_routers.append((phase_management_router, "/phases", ["phases"], "phase_management"))
    logging.info("✅ Optional router loaded: phase_management")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: phase_management - {e}")

try:
    from backend.api.monitoring_alerts import router as monitoring_alerts_router
    optional_routers.append((monitoring_alerts_router, "/alerts", ["alerts"], "monitoring_alerts"))
    logging.info("✅ Optional router loaded: monitoring_alerts")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: monitoring_alerts - {e}")

try:
    from backend.api.knowledge_test import router as knowledge_test_router
    optional_routers.append((knowledge_test_router, "/knowledge-test", ["knowledge-test"], "knowledge_test"))
    logging.info("✅ Optional router loaded: knowledge_test")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: knowledge_test - {e}")

try:
    from backend.api.service_monitor import router as service_monitor_router
    optional_routers.append((service_monitor_router, "/service-monitor", ["service-monitor"], "service_monitor"))
    logging.info("✅ Optional router loaded: service_monitor")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: service_monitor - {e}")

try:
    from backend.api.base_terminal import router as base_terminal_router
    optional_routers.append((base_terminal_router, "/base-terminal", ["base-terminal"], "base_terminal"))
    logging.info("✅ Optional router loaded: base_terminal")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: base_terminal - {e}")

# Store logger for app usage
logger = logging.getLogger(__name__)

# Global variables for background services
app_state = {
    "knowledge_base": None,
    "chat_workflow_manager": None,
    "chat_history_manager": None,
    "background_llm_sync": None,
    "config": None
}


class AppFactory:
    """Application factory for creating FastAPI instances with comprehensive configuration"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def create_fastapi_app(
        title: str = "AutoBot - Distributed Autonomous Agent",
        description: str = "Advanced AI-powered autonomous Linux administration platform with distributed VM architecture",
        version: str = "1.5.0",
        allow_origins: Optional[List[str]] = None
    ) -> FastAPI:
        """Create and configure FastAPI application with optimal performance settings"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Application lifespan manager with background initialization"""
            logger.info("🚀 AutoBot Backend starting up...")

            # Start background initialization
            logger.info("✅ [  0%] Background Init: Starting background initialization...")

            # Background task for heavy initialization
            async def background_init():
                try:
                    # Initialize configuration
                    logger.info("✅ [ 10%] Config: Loading unified configuration...")
                    config = UnifiedConfigManager()
                    app.state.config = config
                    app_state["config"] = config

                    # Initialize Redis (with timeout handling)
                    logger.info("✅ [ 20%] Redis: Initializing Redis connection...")
                    try:
                        from src.redis_pool_manager import RedisPoolManager
                        redis_manager = RedisPoolManager()
                        # Pools initialize automatically on first use
                        app.state.redis_manager = redis_manager
                        logger.info("✅ Redis Pool Manager initialized successfully")
                    except Exception as redis_error:
                        logger.error(f"Redis initialization failed: {redis_error}")
                        # Continue without Redis - some features may be limited

                    # Initialize Knowledge Base in background
                    logger.info("✅ [ 30%] Knowledge Base: Initializing knowledge base...")
                    try:
                        knowledge_base = await get_or_create_knowledge_base(app)
                        app.state.knowledge_base = knowledge_base
                        app_state["knowledge_base"] = knowledge_base
                        logger.info("✅ [ 90%] Knowledge Base: Knowledge base ready")
                    except Exception as kb_error:
                        logger.error(f"Knowledge base initialization failed: {kb_error}")
                        app.state.knowledge_base = None

                    # Initialize Chat History Manager
                    logger.info("✅ [ 85%] Chat History: Initializing chat history manager...")
                    try:
                        chat_history_manager = ChatHistoryManager()
                        app.state.chat_history_manager = chat_history_manager
                        app_state["chat_history_manager"] = chat_history_manager
                        logger.info("✅ [ 85%] Chat History: Chat history manager initialized")
                    except Exception as chat_history_error:
                        logger.error(f"Chat history manager initialization failed: {chat_history_error}")
                        app.state.chat_history_manager = None

                    # Initialize Chat Workflow Manager
                    logger.info("✅ [ 90%] Chat Workflow: Initializing chat workflow manager...")
                    try:
                        chat_workflow_manager = ChatWorkflowManager()
                        app.state.chat_workflow_manager = chat_workflow_manager
                        app_state["chat_workflow_manager"] = chat_workflow_manager
                        logger.info("✅ [ 90%] Chat Workflow: Chat workflow manager initialized")
                    except Exception as chat_error:
                        logger.error(f"Chat workflow manager initialization failed: {chat_error}")

                    # Initialize Background LLM Sync
                    try:
                        from backend.services.ai_stack_client import AIStackClient
                        ai_stack_client = AIStackClient()
                        app.state.ai_stack_client = ai_stack_client

                        background_llm_sync = BackgroundLLMSync()
                        await background_llm_sync.start()
                        app.state.background_llm_sync = background_llm_sync
                        app_state["background_llm_sync"] = background_llm_sync

                        # Test AI Stack availability
                        try:
                            ai_stack_health = await ai_stack_client.health_check()
                            if ai_stack_health.get('status') == 'healthy':
                                logger.info("✅ [ 90%] AI Stack: AI Stack fully available")
                            else:
                                logger.info("🔄 [ 90%] AI Stack: AI Stack partially available")
                        except Exception as ai_error:
                            logger.info("🔄 [ 90%] AI Stack: AI Stack partially available")

                    except Exception as sync_error:
                        logger.error(f"Background LLM sync initialization failed: {sync_error}")

                except Exception as e:
                    logger.error(f"Background initialization failed: {e}")
                    # App can still start without background services

            # Start background initialization task
            asyncio.create_task(background_init())

            yield  # Application runs here

            # Cleanup on shutdown
            logger.info("🛑 AutoBot Backend shutting down...")
            try:
                if hasattr(app.state, 'background_llm_sync') and app.state.background_llm_sync:
                    await app.state.background_llm_sync.stop()
                if hasattr(app.state, 'redis_manager') and app.state.redis_manager:
                    await app.state.redis_manager.close_all_pools()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")

        app = FastAPI(
            title=title,
            description=description,
            version=version,
            lifespan=lifespan,
            redoc_url=None  # Disable ReDoc to save resources
        )

        # Configure CORS with specific origins for security
        if allow_origins is None:
            allow_origins = [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://172.16.168.20:5173",
                "http://172.16.168.21:5173",
                "http://172.16.168.20:3000",
                "http://172.16.168.21:3000",
                "http://172.16.168.25:3000",
            ]

        app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Add GZip compression for better performance
        app.add_middleware(GZipMiddleware, minimum_size=1000)

        # Configure core routers - these should always be available
        core_routers = [
            (chat_router, "", ["chat"], "chat"),
            (system_router, "/system", ["system"], "system"),
            (settings_router, "/settings", ["settings"], "settings"),
            (prompts_router, "/prompts", ["prompts"], "prompts"),
            (knowledge_router, "/knowledge_base", ["knowledge"], "knowledge"),
            (llm_router, "/llm", ["llm"], "llm"),
            (redis_router, "/redis", ["redis"], "redis"),
            (voice_router, "/voice", ["voice"], "voice"),
            (agent_router, "/agent", ["agent"], "agent"),
            (agent_config_router, "/agent_config", ["agent_config"], "agent_config"),
            (intelligent_agent_router, "/intelligent_agent", ["intelligent_agent"], "intelligent_agent"),
            (files_router, "/files", ["files"], "files"),
            (developer_router, "/developer", ["developer"], "developer"),
            (frontend_config_router, "", ["frontend-config"], "frontend_config"),
        ]

        # Add root-level endpoints that frontend expects directly under /api
        @app.get("/api/health")
        async def root_health_check():
            """Root health endpoint that frontend expects"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "autobot-backend"
            }

        @app.get("/api/version")
        async def root_version():
            """Root version endpoint that frontend expects"""
            return {
                "version": "0.0.1",
                "build": "dev",
                "timestamp": datetime.now().isoformat()
            }

        # Register core routers
        for router, prefix, tags, name in core_routers:
            try:
                app.include_router(router, prefix=f"/api{prefix}", tags=tags)
                logger.info(f"✅ Registered core router: {name} at /api{prefix}")
            except Exception as e:
                logger.error(f"❌ Failed to register core router {name}: {e}")

        # Register optional routers
        for router, prefix, tags, name in optional_routers:
            try:
                app.include_router(router, prefix=f"/api{prefix}", tags=tags)
                logger.info(f"✅ Successfully registered optional router: {name} at /api{prefix}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to register optional router {name}: {e}")

        logger.info("✅ API routes configured with optional AI Stack integration")

        # Add root-level health endpoint that many clients expect
        @app.get("/api/health")
        async def root_health_check():
            """Root-level health check endpoint"""
            return {"status": "healthy", "timestamp": datetime.now(), "service": "autobot-backend"}

        # Mount static files for serving frontend assets
        try:
            static_dir = Path("static")
            if static_dir.exists():
                app.mount("/static", StaticFiles(directory="static"), name="static")
                logger.info("Static files mounted from static")
            else:
                logger.info("No static directory found, skipping static file mounting")
        except Exception as e:
            logger.warning(f"Could not mount static files: {e}")

        logger.info("✅ FastAPI application configured successfully")
        return app


def create_app(**kwargs) -> FastAPI:
    """Factory function to create the FastAPI application"""
    factory = AppFactory()
    return factory.create_fastapi_app(**kwargs)


# For direct usage in main.py or testing
if __name__ == "__main__":
    app = create_app()
    logger.info("✅ AutoBot Backend application ready")