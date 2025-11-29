# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Router Loading Module

This module handles the dynamic loading of core and optional API routers
for the AutoBot backend. It separates router configuration from the main
application factory to improve maintainability and organization.

Core routers are essential for basic functionality and should always load.
Optional routers provide enhanced features and gracefully fall back if unavailable.
"""

import logging

# Core router imports - these are required for basic functionality
from backend.api.agent import router as agent_router
from backend.api.agent_config import router as agent_config_router
from backend.api.browser_mcp import router as browser_mcp_router
from backend.api.chat import router as chat_router
from backend.api.database_mcp import router as database_mcp_router
from backend.api.developer import router as developer_router
from backend.api.files import router as files_router
from backend.api.filesystem_mcp import router as filesystem_mcp_router
from backend.api.frontend_config import router as frontend_config_router
from backend.api.git_mcp import router as git_mcp_router
from backend.api.http_client_mcp import router as http_client_mcp_router
from backend.api.intelligent_agent import router as intelligent_agent_router
from backend.api.knowledge import router as knowledge_router
from backend.api.knowledge_mcp import router as knowledge_mcp_router
from backend.api.knowledge_search import router as knowledge_search_router
from backend.api.knowledge_tags import router as knowledge_tags_router
from backend.api.knowledge_population import router as knowledge_population_router
from backend.api.llm import router as llm_router
from backend.api.mcp_registry import router as mcp_registry_router
from backend.api.memory import router as memory_router
from backend.api.prompts import router as prompts_router
from backend.api.redis import router as redis_router
from backend.api.sequential_thinking_mcp import router as sequential_thinking_mcp_router
from backend.api.settings import router as settings_router
from backend.api.structured_thinking_mcp import router as structured_thinking_mcp_router
from backend.api.system import router as system_router
from backend.api.vnc_manager import router as vnc_router
from backend.api.vnc_mcp import router as vnc_mcp_router
from backend.api.vnc_proxy import router as vnc_proxy_router
from backend.api.voice import router as voice_router
from backend.api.wake_word import router as wake_word_router

logger = logging.getLogger(__name__)


def load_core_routers():
    """
    Load and return core API routers.

    Core routers provide essential functionality and should always be available.
    These routers are imported at module level to ensure they fail fast if missing.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              - router: FastAPI APIRouter instance
              - prefix: URL prefix for the router (e.g., "/system")
              - tags: List of OpenAPI tags for documentation
              - name: Identifier for logging/debugging
    """
    return [
        (chat_router, "", ["chat"], "chat"),
        (system_router, "/system", ["system"], "system"),
        (settings_router, "/settings", ["settings"], "settings"),
        (prompts_router, "/prompts", ["prompts"], "prompts"),
        (knowledge_router, "/knowledge_base", ["knowledge"], "knowledge"),
        (knowledge_search_router, "/knowledge_base", ["knowledge-search"], "knowledge_search"),
        (knowledge_tags_router, "/knowledge_base", ["knowledge-tags"], "knowledge_tags"),
        (knowledge_population_router, "/knowledge_base", ["knowledge-population"], "knowledge_population"),
        (llm_router, "/llm", ["llm"], "llm"),
        (redis_router, "/redis", ["redis"], "redis"),
        (voice_router, "/voice", ["voice"], "voice"),
        (wake_word_router, "/wake_word", ["wake_word", "voice"], "wake_word"),
        (vnc_router, "/vnc", ["vnc"], "vnc"),
        (vnc_proxy_router, "/vnc-proxy", ["vnc-proxy"], "vnc_proxy"),
        (knowledge_mcp_router, "/knowledge", ["knowledge_mcp", "mcp"], "knowledge_mcp"),
        (vnc_mcp_router, "/vnc", ["vnc", "mcp"], "vnc_mcp"),
        (mcp_registry_router, "/mcp", ["mcp", "registry"], "mcp_registry"),
        (
            sequential_thinking_mcp_router,
            "/sequential_thinking",
            ["sequential_thinking_mcp", "mcp"],
            "sequential_thinking_mcp",
        ),
        (
            structured_thinking_mcp_router,
            "/structured_thinking",
            ["structured_thinking_mcp", "mcp"],
            "structured_thinking_mcp",
        ),
        (
            filesystem_mcp_router,
            "/filesystem",
            ["filesystem_mcp", "mcp"],
            "filesystem_mcp",
        ),
        (browser_mcp_router, "/browser", ["browser_mcp", "mcp"], "browser_mcp"),
        (
            http_client_mcp_router,
            "/http_client",
            ["http_client_mcp", "mcp"],
            "http_client_mcp",
        ),
        (database_mcp_router, "/database", ["database_mcp", "mcp"], "database_mcp"),
        (git_mcp_router, "/git", ["git_mcp", "mcp"], "git_mcp"),
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


def load_optional_routers():
    """
    Dynamically load optional API routers with graceful fallback.

    Optional routers provide enhanced features but are not required for basic
    functionality. Each router is loaded in a try-except block to gracefully
    handle missing dependencies or implementation.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    optional_routers = []

    # Monitoring router
    try:
        from backend.api.monitoring import router as monitoring_router

        optional_routers.append(
            (monitoring_router, "/monitoring", ["monitoring"], "monitoring")
        )
        logger.info("✅ Optional router loaded: monitoring")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: monitoring - {e}")

    # Terminal router
    try:
        from backend.api.terminal import router as terminal_router

        optional_routers.append(
            (terminal_router, "/terminal", ["terminal"], "terminal")
        )
        logger.info("✅ Optional router loaded: terminal")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: terminal - {e}")

    # Agent Terminal router
    try:
        from backend.api.agent_terminal import router as agent_terminal_router

        optional_routers.append(
            (agent_terminal_router, "", ["agent-terminal"], "agent_terminal")
        )
        logger.info(
            "✅ Optional router loaded: agent_terminal (includes prefix /api/agent-terminal)"
        )
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: agent_terminal - {e}")

    # WebSockets router
    try:
        from backend.api.websockets import router as websockets_router

        # FIXED: No prefix needed - websocket route is already @router.websocket("/ws")
        optional_routers.append((websockets_router, "", ["websockets"], "websockets"))
        logger.info("✅ Optional router loaded: websockets")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: websockets - {e}")

    # Analytics router
    try:
        from backend.api.analytics import router as analytics_router

        optional_routers.append(
            (analytics_router, "/analytics", ["analytics"], "analytics")
        )
        logger.info("✅ Optional router loaded: analytics")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics - {e}")

    # Workflow router
    try:
        from backend.api.workflow import router as workflow_router

        optional_routers.append(
            (workflow_router, "/workflow", ["workflow"], "workflow")
        )
        logger.info("✅ Optional router loaded: workflow")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: workflow - {e}")

    # Remote Terminal router
    try:
        from backend.api.remote_terminal import router as remote_terminal_router

        optional_routers.append(
            (remote_terminal_router, "", ["remote-terminal"], "remote_terminal")
        )
        logger.info(
            "✅ Optional router loaded: remote_terminal (includes prefix /api/remote-terminal)"
        )
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: remote_terminal - {e}")

    # Batch router
    try:
        from backend.api.batch import router as batch_router

        optional_routers.append((batch_router, "/batch", ["batch"], "batch"))
        logger.info("✅ Optional router loaded: batch")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: batch - {e}")

    # Advanced Workflow Orchestrator router
    try:
        from backend.api.advanced_workflow_orchestrator import (
            router as orchestrator_router,
        )

        optional_routers.append(
            (orchestrator_router, "/orchestrator", ["orchestrator"], "orchestrator")
        )
        logger.info("✅ Optional router loaded: orchestrator")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: orchestrator - {e}")

    # Logs router
    try:
        from backend.api.logs import router as logs_router

        optional_routers.append((logs_router, "/logs", ["logs"], "logs"))
        logger.info("✅ Optional router loaded: logs")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: logs - {e}")

    # RUM (Real User Monitoring) router
    try:
        from backend.api.rum import router as rum_router

        optional_routers.append((rum_router, "/rum", ["rum"], "rum"))
        logger.info("✅ Optional router loaded: rum")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: rum - {e}")

    # Secrets router
    try:
        from backend.api.secrets import router as secrets_router

        optional_routers.append((secrets_router, "/secrets", ["secrets"], "secrets"))
        logger.info("✅ Optional router loaded: secrets")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: secrets - {e}")

    # Cache router
    try:
        from backend.api.cache import router as cache_router

        optional_routers.append((cache_router, "/cache", ["cache"], "cache"))
        logger.info("✅ Optional router loaded: cache")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: cache - {e}")

    # Registry router
    try:
        from backend.api.registry import router as registry_router

        optional_routers.append(
            (registry_router, "/registry", ["registry"], "registry")
        )
        logger.info("✅ Optional router loaded: registry")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: registry - {e}")

    # Embeddings router
    try:
        from backend.api.embeddings import router as embeddings_router

        optional_routers.append(
            (embeddings_router, "/embeddings", ["embeddings"], "embeddings")
        )
        logger.info("✅ Optional router loaded: embeddings")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: embeddings - {e}")

    # Workflow Automation router
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
        logger.info("✅ Optional router loaded: workflow_automation")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: workflow_automation - {e}")

    # Research Browser router
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
        logger.info("✅ Optional router loaded: research_browser")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: research_browser - {e}")

    # Playwright router
    try:
        from backend.api.playwright import router as playwright_router

        optional_routers.append(
            (
                playwright_router,
                "/playwright",
                ["playwright"],
                "playwright",
            )
        )
        logger.info("✅ Optional router loaded: playwright")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: playwright - {e}")

    # Vision router
    try:
        from backend.api.vision import router as vision_router

        optional_routers.append(
            (
                vision_router,
                "/vision",
                ["vision", "gui-automation"],
                "vision",
            )
        )
        logger.info("✅ Optional router loaded: vision")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: vision - {e}")

    # Web Research Settings router
    try:
        from backend.api.web_research_settings import (
            router as web_research_settings_router,
        )

        optional_routers.append(
            (
                web_research_settings_router,
                "/web-research-settings",
                ["web-research-settings"],
                "web_research_settings",
            )
        )
        logger.info("✅ Optional router loaded: web_research_settings")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: web_research_settings - {e}")

    # State Tracking router
    try:
        from backend.api.state_tracking import router as state_tracking_router

        optional_routers.append(
            (
                state_tracking_router,
                "/state-tracking",
                ["state-tracking"],
                "state_tracking",
            )
        )
        logger.info("✅ Optional router loaded: state_tracking")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: state_tracking - {e}")

    # Services router
    try:
        from backend.api.services import router as services_router

        optional_routers.append(
            (services_router, "/services", ["services"], "services")
        )
        logger.info("✅ Optional router loaded: services")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: services - {e}")

    # Elevation router
    try:
        from backend.api.elevation import router as elevation_router

        optional_routers.append(
            (elevation_router, "/elevation", ["elevation"], "elevation")
        )
        logger.info("✅ Optional router loaded: elevation")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: elevation - {e}")

    # Auth router
    try:
        from backend.api.auth import router as auth_router

        optional_routers.append((auth_router, "/auth", ["auth"], "auth"))
        logger.info("✅ Optional router loaded: auth")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: auth - {e}")

    # Error Monitoring router
    try:
        from backend.api.error_monitoring import router as error_monitoring_router

        optional_routers.append(
            (error_monitoring_router, "/errors", ["errors"], "error_monitoring")
        )
        logger.info("✅ Optional router loaded: error_monitoring")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: error_monitoring - {e}")

    # Multimodal router
    try:
        from backend.api.multimodal import router as multimodal_router

        optional_routers.append(
            (multimodal_router, "/multimodal", ["multimodal"], "multimodal")
        )
        logger.info("✅ Optional router loaded: multimodal")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: multimodal - {e}")

    # Hot Reload router
    try:
        from backend.api.hot_reload import router as hot_reload_router

        optional_routers.append(
            (hot_reload_router, "/hot-reload", ["hot-reload"], "hot_reload")
        )
        logger.info("✅ Optional router loaded: hot_reload")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: hot_reload - {e}")

    # Enterprise Features router
    try:
        from backend.api.enterprise_features import router as enterprise_router

        optional_routers.append(
            (enterprise_router, "/enterprise", ["enterprise"], "enterprise")
        )
        logger.info("✅ Optional router loaded: enterprise")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: enterprise - {e}")

    # Infrastructure Monitor router
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
        logger.info("✅ Optional router loaded: infrastructure_monitor")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: infrastructure_monitor - {e}")

    # Scheduler router
    try:
        from backend.api.scheduler import router as scheduler_router

        optional_routers.append(
            (scheduler_router, "/scheduler", ["scheduler"], "scheduler")
        )
        logger.info("✅ Optional router loaded: scheduler")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: scheduler - {e}")

    # Templates router
    try:
        from backend.api.templates import router as templates_router

        optional_routers.append(
            (templates_router, "/templates", ["templates"], "templates")
        )
        logger.info("✅ Optional router loaded: templates")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: templates - {e}")

    # Sandbox router
    try:
        from backend.api.sandbox import router as sandbox_router

        optional_routers.append((sandbox_router, "/sandbox", ["sandbox"], "sandbox"))
        logger.info("✅ Optional router loaded: sandbox")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: sandbox - {e}")

    # Security router
    try:
        from backend.api.security import router as security_router

        optional_routers.append(
            (security_router, "/security", ["security"], "security")
        )
        logger.info("✅ Optional router loaded: security")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: security - {e}")

    # Code Search router
    try:
        from backend.api.code_search import router as code_search_router

        optional_routers.append(
            (code_search_router, "/code-search", ["code-search"], "code_search")
        )
        logger.info("✅ Optional router loaded: code_search")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: code_search - {e}")

    # Orchestration router
    try:
        from backend.api.orchestration import router as orchestration_router

        optional_routers.append(
            (orchestration_router, "/orchestration", ["orchestration"], "orchestration")
        )
        logger.info("✅ Optional router loaded: orchestration")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: orchestration - {e}")

    # Cache Management router
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
        logger.info("✅ Optional router loaded: cache_management")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: cache_management - {e}")

    # LLM Optimization router
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
        logger.info("✅ Optional router loaded: llm_optimization")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: llm_optimization - {e}")

    # Enhanced Search router
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
        logger.info("✅ Optional router loaded: enhanced_search")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: enhanced_search - {e}")

    # Enhanced Memory router
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
        logger.info("✅ Optional router loaded: enhanced_memory")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: enhanced_memory - {e}")

    # Development Speedup router
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
        logger.info("✅ Optional router loaded: development_speedup")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: development_speedup - {e}")

    # Advanced Control router
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
        logger.info("✅ Optional router loaded: advanced_control")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: advanced_control - {e}")

    # Codebase Analytics router
    try:
        from backend.api.codebase_analytics import router as codebase_analytics_router

        optional_routers.append(
            (
                codebase_analytics_router,
                # FIXED: Changed from /codebase-analytics to /analytics (router has
                # /codebase prefix)
                "/analytics",
                ["codebase-analytics"],
                "codebase_analytics",
            )
        )
        logger.info("✅ Optional router loaded: codebase_analytics")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: codebase_analytics - {e}")

    # Long Running Operations router
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
        logger.info("✅ Optional router loaded: long_running_operations")
    except ImportError as e:
        logger.warning(
            f"⚠️ Optional router not available: long_running_operations - {e}"
        )

    # System Validation router
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
        logger.info("✅ Optional router loaded: system_validation")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: system_validation - {e}")

    # Validation Dashboard router
    try:
        from backend.api.validation_dashboard import (
            router as validation_dashboard_router,
        )

        optional_routers.append(
            (
                validation_dashboard_router,
                "/validation-dashboard",
                ["validation-dashboard"],
                "validation_dashboard",
            )
        )
        logger.info("✅ Optional router loaded: validation_dashboard")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: validation_dashboard - {e}")

    # LLM Awareness router
    try:
        from backend.api.llm_awareness import router as llm_awareness_router

        optional_routers.append(
            (llm_awareness_router, "/llm-awareness", ["llm-awareness"], "llm_awareness")
        )
        logger.info("✅ Optional router loaded: llm_awareness")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: llm_awareness - {e}")

    # Project State router
    try:
        from backend.api.project_state import router as project_state_router

        optional_routers.append(
            (project_state_router, "/project-state", ["project-state"], "project_state")
        )
        logger.info("✅ Optional router loaded: project_state")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: project_state - {e}")

    # Metrics router
    try:
        from backend.api.metrics import router as metrics_router

        optional_routers.append((metrics_router, "/metrics", ["metrics"], "metrics"))
        logger.info("✅ Optional router loaded: metrics")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: metrics - {e}")

    # Startup router
    try:
        from backend.api.startup import router as startup_router

        optional_routers.append((startup_router, "/startup", ["startup"], "startup"))
        logger.info("✅ Optional router loaded: startup")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: startup - {e}")

    # Phase Management router
    try:
        from backend.api.phase_management import router as phase_management_router

        optional_routers.append(
            (phase_management_router, "/phases", ["phases"], "phase_management")
        )
        logger.info("✅ Optional router loaded: phase_management")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: phase_management - {e}")

    # Monitoring Alerts router
    try:
        from backend.api.monitoring_alerts import router as monitoring_alerts_router

        optional_routers.append(
            (monitoring_alerts_router, "/alerts", ["alerts"], "monitoring_alerts")
        )
        logger.info("✅ Optional router loaded: monitoring_alerts")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: monitoring_alerts - {e}")

    # Knowledge Test router
    try:
        from backend.api.knowledge_test import router as knowledge_test_router

        optional_routers.append(
            (
                knowledge_test_router,
                "/knowledge-test",
                ["knowledge-test"],
                "knowledge_test",
            )
        )
        logger.info("✅ Optional router loaded: knowledge_test")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: knowledge_test - {e}")

    # Service Monitor router
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
        logger.info("✅ Optional router loaded: service_monitor")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: service_monitor - {e}")

    # Base Terminal router
    try:
        from backend.api.base_terminal import router as base_terminal_router

        optional_routers.append(
            (base_terminal_router, "/base-terminal", ["base-terminal"], "base_terminal")
        )
        logger.info("✅ Optional router loaded: base_terminal")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: base_terminal - {e}")

    # Conversation Files router
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
        logger.info("✅ Optional router loaded: conversation_files")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: conversation_files - {e}")

    # Chat Knowledge router
    try:
        from backend.api.chat_knowledge import router as chat_knowledge_router

        optional_routers.append(
            (
                chat_knowledge_router,
                "/chat-knowledge",
                ["chat-knowledge"],
                "chat_knowledge",
            )
        )
        logger.info("✅ Optional router loaded: chat_knowledge")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: chat_knowledge - {e}")

    # NPU Workers router
    try:
        from backend.api.npu_workers import router as npu_workers_router

        optional_routers.append(
            (npu_workers_router, "", ["npu-workers"], "npu_workers")
        )
        logger.info("✅ Optional router loaded: npu_workers (includes prefix /api/npu)")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: npu_workers - {e}")

    # Redis Service router
    try:
        from backend.api.redis_service import router as redis_service_router

        optional_routers.append(
            (redis_service_router, "/redis-service", ["redis-service"], "redis_service")
        )
        logger.info("✅ Optional router loaded: redis_service")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: redis_service - {e}")

    # Infrastructure router
    try:
        from backend.api.infrastructure import router as infrastructure_router

        optional_routers.append(
            (
                infrastructure_router,
                "/iac",
                ["Infrastructure as Code"],
                "infrastructure",
            )
        )
        logger.info("✅ Optional router loaded: infrastructure")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: infrastructure - {e}")

    # Entity Extraction router
    try:
        from backend.api.entity_extraction import router as entity_extraction_router

        optional_routers.append(
            (
                entity_extraction_router,
                "/entities",
                ["entity-extraction"],
                "entity_extraction",
            )
        )
        logger.info("✅ Optional router loaded: entity_extraction")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: entity_extraction - {e}")

    # Graph-RAG router
    try:
        from backend.api.graph_rag import router as graph_rag_router

        optional_routers.append(
            (
                graph_rag_router,
                "/graph-rag",
                ["graph-rag"],
                "graph_rag",
            )
        )
        logger.info("✅ Optional router loaded: graph_rag")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: graph_rag - {e}")

    # Security Assessment Workflow router (Issue #260)
    try:
        from backend.api.security_assessment import router as security_assessment_router

        optional_routers.append(
            (
                security_assessment_router,
                "",  # Router has /security prefix internally
                ["security-assessment"],
                "security_assessment",
            )
        )
        logger.info("✅ Optional router loaded: security_assessment")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: security_assessment - {e}")

    # Anti-Pattern Detection router (Issue #221)
    try:
        from backend.api.anti_pattern import router as anti_pattern_router

        optional_routers.append(
            (
                anti_pattern_router,
                "/anti-pattern",
                ["anti-pattern", "code-analysis"],
                "anti_pattern",
            )
        )
        logger.info("✅ Optional router loaded: anti_pattern")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: anti_pattern - {e}")

    # Code Intelligence / Code Smell Detection router (Issue #221)
    try:
        from backend.api.code_intelligence import router as code_intelligence_router

        optional_routers.append(
            (
                code_intelligence_router,
                "/code-intelligence",
                ["code-intelligence", "code-analysis"],
                "code_intelligence",
            )
        )
        logger.info("✅ Optional router loaded: code_intelligence")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: code_intelligence - {e}")

    # CAPTCHA Human-in-the-Loop router (Issue #206)
    try:
        from backend.api.captcha import router as captcha_router

        optional_routers.append(
            (
                captcha_router,
                "",  # Router has /captcha prefix internally
                ["captcha", "web-research"],
                "captcha",
            )
        )
        logger.info("✅ Optional router loaded: captcha")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: captcha - {e}")

    # Code Evolution Timeline router (Issue #247)
    try:
        from backend.api.analytics_evolution import router as evolution_router

        optional_routers.append(
            (
                evolution_router,
                "",  # Router has /evolution prefix internally
                ["code-evolution", "analytics"],
                "analytics_evolution",
            )
        )
        logger.info("✅ Optional router loaded: analytics_evolution")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_evolution - {e}")

    # Technical Debt Calculator router (Issue #231)
    try:
        from backend.api.analytics_debt import router as debt_router

        optional_routers.append(
            (
                debt_router,
                "",  # Router has /debt prefix internally
                ["technical-debt", "analytics"],
                "analytics_debt",
            )
        )
        logger.info("✅ Optional router loaded: analytics_debt")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_debt - {e}")

    # Real-time Code Quality Dashboard router (Issue #230)
    try:
        from backend.api.analytics_quality import router as quality_router

        optional_routers.append(
            (
                quality_router,
                "",
                ["code-quality", "analytics"],
                "analytics_quality",
            )
        )
        logger.info("✅ Optional router loaded: analytics_quality")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_quality - {e}")

    # Bug Prediction System router (Issue #224)
    try:
        from backend.api.analytics_bug_prediction import router as bug_prediction_router

        optional_routers.append(
            (
                bug_prediction_router,
                "",
                ["bug-prediction", "analytics"],
                "analytics_bug_prediction",
            )
        )
        logger.info("✅ Optional router loaded: analytics_bug_prediction")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_bug_prediction - {e}")

    # AI-Powered Code Review router (Issue #225)
    try:
        from backend.api.analytics_code_review import router as code_review_router

        optional_routers.append(
            (
                code_review_router,
                "",
                ["code-review", "analytics"],
                "analytics_code_review",
            )
        )
        logger.info("✅ Optional router loaded: analytics_code_review")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_code_review - {e}")

    # Git Pre-commit Hook Analyzer router (Issue #223)
    try:
        from backend.api.analytics_precommit import router as precommit_router

        optional_routers.append(
            (
                precommit_router,
                "",
                ["precommit", "analytics"],
                "analytics_precommit",
            )
        )
        logger.info("✅ Optional router loaded: analytics_precommit")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_precommit - {e}")

    # Performance Pattern Analysis router (Issue #222)
    try:
        from backend.api.analytics_performance import router as performance_router

        optional_routers.append(
            (
                performance_router,
                "",
                ["performance", "analytics"],
                "analytics_performance",
            )
        )
        logger.info("✅ Optional router loaded: analytics_performance")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_performance - {e}")

    # Dynamic Pattern Mining from Logs router (Issue #226)
    try:
        from backend.api.analytics_log_patterns import router as log_patterns_router

        optional_routers.append(
            (
                log_patterns_router,
                "",
                ["log-patterns", "analytics"],
                "analytics_log_patterns",
            )
        )
        logger.info("✅ Optional router loaded: analytics_log_patterns")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_log_patterns - {e}")

    # Conversation Flow Analyzer router (Issue #227)
    try:
        from backend.api.analytics_conversation import router as conversation_router

        optional_routers.append(
            (
                conversation_router,
                "",
                ["conversation-flow", "analytics"],
                "analytics_conversation",
            )
        )
        logger.info("✅ Optional router loaded: analytics_conversation")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_conversation - {e}")

    # LLM-Powered Code Generation router (Issue #228)
    try:
        from backend.api.analytics_code_generation import router as code_generation_router

        optional_routers.append(
            (
                code_generation_router,
                "",
                ["code-generation", "analytics"],
                "analytics_code_generation",
            )
        )
        logger.info("✅ Optional router loaded: analytics_code_generation")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_code_generation - {e}")

    # LLM Pattern Analyzer router (Issue #229)
    try:
        from backend.api.analytics_llm_patterns import router as llm_patterns_router

        optional_routers.append(
            (
                llm_patterns_router,
                "",
                ["llm-patterns", "analytics"],
                "analytics_llm_patterns",
            )
        )
        logger.info("✅ Optional router loaded: analytics_llm_patterns")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_llm_patterns - {e}")

    return optional_routers
