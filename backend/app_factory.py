import asyncio
import inspect
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import redis

# Add the project root to Python path for absolute imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contextlib import asynccontextmanager

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api.agent import router as agent_router
from backend.api.agent_config import router as agent_config_router

# Import API routers
from backend.api.chat import router as chat_router
from backend.api.developer import router as developer_router
from backend.api.files import router as files_router
from backend.api.frontend_config import router as frontend_config_router
from backend.api.intelligent_agent import router as intelligent_agent_router
from backend.api.knowledge import router as knowledge_router
from backend.api.llm import router as llm_router
from backend.api.memory import router as memory_router
from backend.api.prompts import router as prompts_router
from backend.api.redis import router as redis_router
from backend.api.settings import router as settings_router
from backend.api.system import router as system_router
from backend.api.voice import router as voice_router
from backend.dependencies import get_config, get_knowledge_base
from backend.knowledge_factory import get_or_create_knowledge_base
from src.chat_history_manager import ChatHistoryManager
from src.chat_workflow_manager import ChatWorkflowManager
from src.security_layer import SecurityLayer
from src.unified_config_manager import UnifiedConfigManager
from src.utils.background_llm_sync import BackgroundLLMSync

# Enhanced routers with optional imports
optional_routers = []

# Try importing optional/enhanced routers
try:
    from backend.api.monitoring import router as monitoring_router

    optional_routers.append(
        (monitoring_router, "/monitoring", ["monitoring"], "monitoring")
    )
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
    from backend.api.agent_terminal import router as agent_terminal_router

    optional_routers.append(
        (agent_terminal_router, "", ["agent-terminal"], "agent_terminal")
    )
    logging.info(
        "✅ Optional router loaded: agent_terminal (includes prefix /api/agent-terminal)"
    )
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: agent_terminal - {e}")

try:
    from backend.api.websockets import router as websockets_router

    # FIXED: No prefix needed - websocket route is already @router.websocket("/ws")
    optional_routers.append((websockets_router, "", ["websockets"], "websockets"))
    logging.info("✅ Optional router loaded: websockets")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: websockets - {e}")

try:
    from backend.api.analytics import router as analytics_router

    optional_routers.append(
        (analytics_router, "/analytics", ["analytics"], "analytics")
    )
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
    from backend.api.remote_terminal import router as remote_terminal_router

    optional_routers.append(
        (remote_terminal_router, "", ["remote-terminal"], "remote_terminal")
    )
    logging.info(
        "✅ Optional router loaded: remote_terminal (includes prefix /api/remote-terminal)"
    )
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: remote_terminal - {e}")

try:
    from backend.api.batch import router as batch_router

    optional_routers.append((batch_router, "/batch", ["batch"], "batch"))
    logging.info("✅ Optional router loaded: batch")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: batch - {e}")

try:
    from backend.api.advanced_workflow_orchestrator import router as orchestrator_router

    optional_routers.append(
        (orchestrator_router, "/orchestrator", ["orchestrator"], "orchestrator")
    )
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

    optional_routers.append(
        (embeddings_router, "/embeddings", ["embeddings"], "embeddings")
    )
    logging.info("✅ Optional router loaded: embeddings")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: embeddings - {e}")

try:
    from backend.api.workflow_automation import router as workflow_automation_router

    optional_routers.append(
        (
            workflow_automation_router,
            "/workflow-automation",
            ["workflow-automation"],
            "workflow_automation",
        )
    )
    logging.info("✅ Optional router loaded: workflow_automation")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: workflow_automation - {e}")

try:
    from backend.api.research_browser import router as research_browser_router

    optional_routers.append(
        (
            research_browser_router,
            "/research-browser",
            ["research-browser"],
            "research_browser",
        )
    )
    logging.info("✅ Optional router loaded: research_browser")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: research_browser - {e}")

try:
    from backend.api.web_research_settings import router as web_research_settings_router

    optional_routers.append(
        (
            web_research_settings_router,
            "/web-research-settings",
            ["web-research-settings"],
            "web_research_settings",
        )
    )
    logging.info("✅ Optional router loaded: web_research_settings")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: web_research_settings - {e}")

try:
    from backend.api.state_tracking import router as state_tracking_router

    optional_routers.append(
        (state_tracking_router, "/state-tracking", ["state-tracking"], "state_tracking")
    )
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

    optional_routers.append(
        (elevation_router, "/elevation", ["elevation"], "elevation")
    )
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

    optional_routers.append(
        (error_monitoring_router, "/errors", ["errors"], "error_monitoring")
    )
    logging.info("✅ Optional router loaded: error_monitoring")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: error_monitoring - {e}")

try:
    from backend.api.multimodal import router as multimodal_router

    optional_routers.append(
        (multimodal_router, "/multimodal", ["multimodal"], "multimodal")
    )
    logging.info("✅ Optional router loaded: multimodal")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: multimodal - {e}")

try:
    from backend.api.hot_reload import router as hot_reload_router

    optional_routers.append(
        (hot_reload_router, "/hot-reload", ["hot-reload"], "hot_reload")
    )
    logging.info("✅ Optional router loaded: hot_reload")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: hot_reload - {e}")

try:
    from backend.api.enterprise_features import router as enterprise_router

    optional_routers.append(
        (enterprise_router, "/enterprise", ["enterprise"], "enterprise")
    )
    logging.info("✅ Optional router loaded: enterprise")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: enterprise - {e}")

try:
    from backend.api.infrastructure_monitor import (
        router as infrastructure_monitor_router,
    )

    optional_routers.append(
        (
            infrastructure_monitor_router,
            "/infrastructure",
            ["infrastructure"],
            "infrastructure_monitor",
        )
    )
    logging.info("✅ Optional router loaded: infrastructure_monitor")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: infrastructure_monitor - {e}")

try:
    from backend.api.scheduler import router as scheduler_router

    optional_routers.append(
        (scheduler_router, "/scheduler", ["scheduler"], "scheduler")
    )
    logging.info("✅ Optional router loaded: scheduler")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: scheduler - {e}")

try:
    from backend.api.templates import router as templates_router

    optional_routers.append(
        (templates_router, "/templates", ["templates"], "templates")
    )
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

    optional_routers.append(
        (code_search_router, "/code-search", ["code-search"], "code_search")
    )
    logging.info("✅ Optional router loaded: code_search")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: code_search - {e}")

try:
    from backend.api.orchestration import router as orchestration_router

    optional_routers.append(
        (orchestration_router, "/orchestration", ["orchestration"], "orchestration")
    )
    logging.info("✅ Optional router loaded: orchestration")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: orchestration - {e}")

try:
    from backend.api.cache_management import router as cache_management_router

    optional_routers.append(
        (
            cache_management_router,
            "/cache-management",
            ["cache-management"],
            "cache_management",
        )
    )
    logging.info("✅ Optional router loaded: cache_management")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: cache_management - {e}")

try:
    from backend.api.llm_optimization import router as llm_optimization_router

    optional_routers.append(
        (
            llm_optimization_router,
            "/llm-optimization",
            ["llm-optimization"],
            "llm_optimization",
        )
    )
    logging.info("✅ Optional router loaded: llm_optimization")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: llm_optimization - {e}")

try:
    from backend.api.enhanced_search import router as enhanced_search_router

    optional_routers.append(
        (
            enhanced_search_router,
            "/enhanced-search",
            ["enhanced-search"],
            "enhanced_search",
        )
    )
    logging.info("✅ Optional router loaded: enhanced_search")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: enhanced_search - {e}")

try:
    from backend.api.enhanced_memory import router as enhanced_memory_router

    optional_routers.append(
        (
            enhanced_memory_router,
            "/enhanced-memory",
            ["enhanced-memory"],
            "enhanced_memory",
        )
    )
    logging.info("✅ Optional router loaded: enhanced_memory")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: enhanced_memory - {e}")

try:
    from backend.api.development_speedup import router as development_speedup_router

    optional_routers.append(
        (
            development_speedup_router,
            "/dev-speedup",
            ["dev-speedup"],
            "development_speedup",
        )
    )
    logging.info("✅ Optional router loaded: development_speedup")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: development_speedup - {e}")

try:
    from backend.api.advanced_control import router as advanced_control_router

    optional_routers.append(
        (
            advanced_control_router,
            "/advanced-control",
            ["advanced-control"],
            "advanced_control",
        )
    )
    logging.info("✅ Optional router loaded: advanced_control")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: advanced_control - {e}")

try:
    from backend.api.codebase_analytics import router as codebase_analytics_router

    optional_routers.append(
        (
            codebase_analytics_router,
            "/analytics",  # FIXED: Changed from /codebase-analytics to /analytics (router has /codebase prefix)
            ["codebase-analytics"],
            "codebase_analytics",
        )
    )
    logging.info("✅ Optional router loaded: codebase_analytics")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: codebase_analytics - {e}")

try:
    from backend.api.long_running_operations import (
        router as long_running_operations_router,
    )

    optional_routers.append(
        (
            long_running_operations_router,
            "/long-running",
            ["long-running"],
            "long_running_operations",
        )
    )
    logging.info("✅ Optional router loaded: long_running_operations")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: long_running_operations - {e}")

try:
    from backend.api.system_validation import router as system_validation_router

    optional_routers.append(
        (
            system_validation_router,
            "/system-validation",
            ["system-validation"],
            "system_validation",
        )
    )
    logging.info("✅ Optional router loaded: system_validation")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: system_validation - {e}")

try:
    from backend.api.validation_dashboard import router as validation_dashboard_router

    optional_routers.append(
        (
            validation_dashboard_router,
            "/validation-dashboard",
            ["validation-dashboard"],
            "validation_dashboard",
        )
    )
    logging.info("✅ Optional router loaded: validation_dashboard")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: validation_dashboard - {e}")

try:
    from backend.api.llm_awareness import router as llm_awareness_router

    optional_routers.append(
        (llm_awareness_router, "/llm-awareness", ["llm-awareness"], "llm_awareness")
    )
    logging.info("✅ Optional router loaded: llm_awareness")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: llm_awareness - {e}")

try:
    from backend.api.project_state import router as project_state_router

    optional_routers.append(
        (project_state_router, "/project-state", ["project-state"], "project_state")
    )
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

    optional_routers.append(
        (phase_management_router, "/phases", ["phases"], "phase_management")
    )
    logging.info("✅ Optional router loaded: phase_management")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: phase_management - {e}")

try:
    from backend.api.monitoring_alerts import router as monitoring_alerts_router

    optional_routers.append(
        (monitoring_alerts_router, "/alerts", ["alerts"], "monitoring_alerts")
    )
    logging.info("✅ Optional router loaded: monitoring_alerts")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: monitoring_alerts - {e}")

try:
    from backend.api.knowledge_test import router as knowledge_test_router

    optional_routers.append(
        (knowledge_test_router, "/knowledge-test", ["knowledge-test"], "knowledge_test")
    )
    logging.info("✅ Optional router loaded: knowledge_test")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: knowledge_test - {e}")

try:
    from backend.api.service_monitor import router as service_monitor_router

    optional_routers.append(
        (
            service_monitor_router,
            "/service-monitor",
            ["service-monitor"],
            "service_monitor",
        )
    )
    logging.info("✅ Optional router loaded: service_monitor")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: service_monitor - {e}")

try:
    from backend.api.base_terminal import router as base_terminal_router

    optional_routers.append(
        (base_terminal_router, "/base-terminal", ["base-terminal"], "base_terminal")
    )
    logging.info("✅ Optional router loaded: base_terminal")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: base_terminal - {e}")

try:
    from backend.api.conversation_files import router as conversation_files_router

    optional_routers.append(
        (
            conversation_files_router,
            "/conversation-files",
            ["conversation-files"],
            "conversation_files",
        )
    )
    logging.info("✅ Optional router loaded: conversation_files")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: conversation_files - {e}")

try:
    from backend.api.chat_knowledge import router as chat_knowledge_router

    optional_routers.append(
        (chat_knowledge_router, "/chat-knowledge", ["chat-knowledge"], "chat_knowledge")
    )
    logging.info("✅ Optional router loaded: chat_knowledge")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: chat_knowledge - {e}")

try:
    from backend.api.npu_workers import router as npu_workers_router

    optional_routers.append((npu_workers_router, "", ["npu-workers"], "npu_workers"))
    logging.info("✅ Optional router loaded: npu_workers (includes prefix /api/npu)")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: npu_workers - {e}")

try:
    from backend.api.redis_service import router as redis_service_router

    optional_routers.append(
        (redis_service_router, "/redis-service", ["redis-service"], "redis_service")
    )
    logging.info("✅ Optional router loaded: redis_service")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: redis_service - {e}")

try:
    from backend.api.infrastructure import router as infrastructure_router

    optional_routers.append(
        (infrastructure_router, "/iac", ["Infrastructure as Code"], "infrastructure")
    )
    logging.info("✅ Optional router loaded: infrastructure")
except ImportError as e:
    logging.warning(f"⚠️ Optional router not available: infrastructure - {e}")

# Store logger for app usage
logger = logging.getLogger(__name__)

# Global variables for background services
app_state = {
    "knowledge_base": None,
    "chat_workflow_manager": None,
    "chat_history_manager": None,
    "background_llm_sync": None,
    "config": None,
    "initialization_status": "starting",  # starting, phase1, phase2, ready, error
    "initialization_message": "Backend starting..."
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
        allow_origins: Optional[List[str]] = None,
    ) -> FastAPI:
        """Create and configure FastAPI application with optimal performance settings"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Application lifespan manager with critical and background initialization"""

            # Configure logging level from environment variable
            LOG_LEVEL = os.getenv("AUTOBOT_LOG_LEVEL", "INFO").upper()
            LOG_LEVEL_VALUE = getattr(logging, LOG_LEVEL, logging.INFO)
            logging.root.setLevel(LOG_LEVEL_VALUE)

            # Set level for all backend loggers
            for logger_name in ["backend", "backend.api", "backend.api.codebase_analytics"]:
                logging.getLogger(logger_name).setLevel(LOG_LEVEL_VALUE)

            logger.info(f"📊 Logging level set to: {LOG_LEVEL} ({LOG_LEVEL_VALUE})")
            logger.info("🚀 AutoBot Backend starting up...")

            # ================================================================
            # PHASE 1: CRITICAL INITIALIZATION (BLOCKING - Must complete before serving requests)
            # ================================================================
            app_state["initialization_status"] = "phase1"
            app_state["initialization_message"] = "Initializing critical services..."
            logger.info("=== PHASE 1: Critical Services Initialization ===")

            try:
                # Initialize configuration - CRITICAL
                logger.info("✅ [ 10%] Config: Loading unified configuration...")
                config = UnifiedConfigManager()
                app.state.config = config
                app_state["config"] = config
                logger.info("✅ [ 10%] Config: Configuration loaded successfully")

                # Initialize Security Layer - CRITICAL
                logger.info("✅ [ 15%] Security: Initializing security layer...")
                security_layer = SecurityLayer()
                app.state.security_layer = security_layer
                app_state["security_layer"] = security_layer
                logger.info("✅ [ 15%] Security: Security layer initialized successfully")

                # Initialize Redis Stack - CRITICAL (but with graceful degradation)
                logger.info(
                    "✅ [ 20%] Redis Stack: Initializing Redis Stack connection..."
                )
                try:
                    from src.redis_pool_manager import RedisPoolManager

                    redis_manager = RedisPoolManager()
                    app.state.redis_manager = redis_manager
                    logger.info(
                        "✅ [ 20%] Redis Stack: Pool Manager initialized successfully"
                    )
                except Exception as redis_error:
                    logger.error(f"Redis Stack initialization failed: {redis_error}")
                    logger.warning(
                        "⚠️ Continuing without Redis Stack - some features may be limited"
                    )

                # Initialize Chat History Manager - CRITICAL
                logger.info(
                    "✅ [ 30%] Chat History: Initializing chat history manager..."
                )
                try:
                    chat_history_manager = ChatHistoryManager()
                    app.state.chat_history_manager = chat_history_manager
                    app_state["chat_history_manager"] = chat_history_manager
                    logger.info(
                        "✅ [ 30%] Chat History: Manager initialized successfully"
                    )
                except Exception as chat_history_error:
                    logger.error(
                        f"❌ CRITICAL: Chat history manager initialization failed: {chat_history_error}"
                    )
                    raise RuntimeError(
                        f"Chat history manager initialization failed: {chat_history_error}"
                    )

                # Initialize Conversation File Manager Database - CRITICAL
                logger.info(
                    "✅ [ 40%] Conversation Files DB: Initializing database schema..."
                )
                try:
                    from src.conversation_file_manager import (
                        get_conversation_file_manager,
                    )

                    conversation_file_manager = await get_conversation_file_manager()
                    await conversation_file_manager.initialize()
                    app.state.conversation_file_manager = conversation_file_manager
                    app_state["conversation_file_manager"] = conversation_file_manager
                    logger.info(
                        "✅ [ 40%] Conversation Files DB: Database initialized and verified"
                    )
                except Exception as conv_file_error:
                    logger.error(
                        f"❌ CRITICAL: Conversation files database initialization failed: {conv_file_error}"
                    )
                    logger.error(
                        "Backend startup ABORTED - database must be operational"
                    )
                    raise RuntimeError(
                        f"Database initialization failed: {conv_file_error}"
                    )

                # Initialize Chat Workflow Manager - CRITICAL
                logger.info("✅ [ 50%] Chat Workflow: Initializing workflow manager...")
                try:
                    chat_workflow_manager = ChatWorkflowManager()
                    await chat_workflow_manager.initialize()
                    app.state.chat_workflow_manager = chat_workflow_manager
                    app_state["chat_workflow_manager"] = chat_workflow_manager
                    logger.info(
                        "✅ [ 50%] Chat Workflow: Manager initialized with async Redis"
                    )
                except Exception as chat_error:
                    logger.error(
                        f"❌ CRITICAL: Chat workflow manager initialization failed: {chat_error}"
                    )
                    raise RuntimeError(
                        f"Chat workflow manager initialization failed: {chat_error}"
                    )

                logger.info(
                    "✅ [ 60%] PHASE 1 COMPLETE: All critical services operational"
                )

            except Exception as critical_error:
                logger.error(f"❌ CRITICAL INITIALIZATION FAILED: {critical_error}")
                logger.error(
                    "Backend startup ABORTED - critical services must be operational"
                )
                raise  # Re-raise to prevent app from starting

            # ================================================================
            # PHASE 2: BACKGROUND INITIALIZATION (NON-BLOCKING - Can complete while serving)
            # ================================================================
            async def background_init():
                """Initialize non-critical services in background"""
                try:
                    app_state["initialization_status"] = "phase2"
                    app_state["initialization_message"] = "Loading knowledge base and AI models..."
                    logger.info("=== PHASE 2: Background Services Initialization ===")

                    # Initialize Knowledge Base - NON-CRITICAL (slow, can fail gracefully)
                    logger.info(
                        "✅ [ 70%] Knowledge Base: Initializing knowledge base..."
                    )
                    try:
                        knowledge_base = await get_or_create_knowledge_base(app)
                        app.state.knowledge_base = knowledge_base
                        app_state["knowledge_base"] = knowledge_base
                        logger.info("✅ [ 70%] Knowledge Base: Knowledge base ready")
                    except Exception as kb_error:
                        logger.warning(
                            f"Knowledge base initialization failed: {kb_error}"
                        )
                        app.state.knowledge_base = None

                    # Initialize NPU Worker WebSocket subscriptions - NON-CRITICAL
                    logger.info(
                        "✅ [ 80%] NPU Workers: Initializing WebSocket event subscriptions..."
                    )
                    try:
                        from backend.api.websockets import init_npu_worker_websocket

                        init_npu_worker_websocket()
                        logger.info(
                            "✅ [ 80%] NPU Workers: WebSocket subscriptions initialized"
                        )
                    except Exception as npu_ws_error:
                        logger.warning(
                            f"NPU worker WebSocket initialization failed: {npu_ws_error}"
                        )

                    # Initialize Memory Graph - NON-CRITICAL
                    logger.info("✅ [ 85%] Memory Graph: Initializing memory graph...")
                    try:
                        from src.autobot_memory_graph import AutoBotMemoryGraph

                        memory_graph = AutoBotMemoryGraph(
                            chat_history_manager=app.state.chat_history_manager
                        )
                        await memory_graph.initialize()
                        app.state.memory_graph = memory_graph
                        app_state["memory_graph"] = memory_graph
                        logger.info(
                            "✅ [ 85%] Memory Graph: Memory graph initialized successfully"
                        )
                    except Exception as memory_error:
                        logger.warning(
                            f"Memory graph initialization failed: {memory_error}"
                        )
                        app.state.memory_graph = None

                    # Initialize Background LLM Sync - NON-CRITICAL
                    logger.info(
                        "✅ [ 90%] Background LLM Sync: Initializing AI Stack integration..."
                    )
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
                            if ai_stack_health.get("status") == "healthy":
                                logger.info(
                                    "✅ [ 90%] AI Stack: AI Stack fully available"
                                )
                            else:
                                logger.info(
                                    "🔄 [ 90%] AI Stack: AI Stack partially available"
                                )
                        except Exception as ai_error:
                            logger.info(
                                "🔄 [ 90%] AI Stack: AI Stack partially available"
                            )

                    except Exception as sync_error:
                        logger.warning(
                            f"Background LLM sync initialization failed: {sync_error}"
                        )

                    app_state["initialization_status"] = "ready"
                    app_state["initialization_message"] = "All services ready"
                    logger.info(
                        "✅ [100%] PHASE 2 COMPLETE: All background services initialized"
                    )

                except Exception as e:
                    logger.error(f"Background initialization encountered errors: {e}")
                    logger.info(
                        "App remains operational with degraded background services"
                    )

            # Start background initialization (non-blocking)
            logger.info("🔄 Starting background services initialization...")
            asyncio.create_task(background_init())

            yield  # Application starts serving requests here

            # ================================================================
            # CLEANUP ON SHUTDOWN
            # ================================================================
            logger.info("🛑 AutoBot Backend shutting down...")
            try:
                if (
                    hasattr(app.state, "background_llm_sync")
                    and app.state.background_llm_sync
                ):
                    await app.state.background_llm_sync.stop()
                if hasattr(app.state, "memory_graph") and app.state.memory_graph:
                    await app.state.memory_graph.close()
                if hasattr(app.state, "redis_manager") and app.state.redis_manager:
                    await app.state.redis_manager.close_all_pools()
                logger.info("✅ Cleanup completed successfully")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")

        app = FastAPI(
            title=title,
            description=description,
            version=version,
            lifespan=lifespan,
            redoc_url=None,  # Disable ReDoc to save resources
        )

        # Configure CORS with specific origins for security
        # Generate from centralized configuration instead of hardcoded list
        if allow_origins is None:
            from src.unified_config import config
            allow_origins = config.get_cors_origins()

        app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Add GZip compression for better performance
        app.add_middleware(GZipMiddleware, minimum_size=1000)

        # BEGIN SERVICE AUTH MIDDLEWARE - ANSIBLE MANAGED
        # Service authentication middleware - ENFORCEMENT MODE (Week 3 Phase 3)
        try:
            from starlette.middleware.base import BaseHTTPMiddleware

            from backend.middleware.service_auth_enforcement import (
                enforce_service_auth,
                log_enforcement_status,
            )

            app.add_middleware(BaseHTTPMiddleware, dispatch=enforce_service_auth)
            log_enforcement_status()
            logger.info(
                "✅ Service Authentication Middleware (ENFORCEMENT MODE) enabled"
            )
        except ImportError as e:
            logger.warning(f"⚠️ Service auth enforcement middleware not available: {e}")
            # Fallback to logging mode if enforcement not available
            try:
                from backend.middleware.service_auth_logging import (
                    ServiceAuthLoggingMiddleware,
                )

                app.add_middleware(ServiceAuthLoggingMiddleware)
                logger.info(
                    "✅ Service Authentication Middleware (LOGGING MODE - fallback) enabled"
                )
            except ImportError as e2:
                logger.warning(f"⚠️ Service auth middleware not available: {e2}")
        # END SERVICE AUTH MIDDLEWARE - ANSIBLE MANAGED

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
            (
                intelligent_agent_router,
                "/intelligent_agent",
                ["intelligent_agent"],
                "intelligent_agent",
            ),
            (files_router, "/files", ["files"], "files"),
            (developer_router, "/developer", ["developer"], "developer"),
            (frontend_config_router, "", ["frontend-config"], "frontend_config"),
            (memory_router, "/memory", ["memory"], "memory"),
        ]

        # Add root-level endpoints that frontend expects directly under /api
        @app.get("/api/health")
        async def root_health_check():
            """Root health endpoint that frontend expects"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "autobot-backend",
            }

        @app.get("/api/version")
        async def root_version():
            """Root version endpoint that frontend expects"""
            return {
                "version": "0.0.1",
                "build": "dev",
                "timestamp": datetime.now().isoformat(),
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
                logger.info(
                    f"✅ Successfully registered optional router: {name} at /api{prefix}"
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to register optional router {name}: {e}")

        logger.info("✅ API routes configured with optional AI Stack integration")

        # Add root-level health endpoint that many clients expect
        @app.get("/api/health")
        async def root_health_check():
            """Root-level health check endpoint"""
            return {
                "status": "healthy",
                "timestamp": datetime.now(),
                "service": "autobot-backend",
            }

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


# Create app instance for uvicorn
app = create_app()

# For direct usage in main.py or testing
if __name__ == "__main__":
    logger.info("✅ AutoBot Backend application ready")
