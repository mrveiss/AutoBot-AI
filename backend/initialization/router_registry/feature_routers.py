# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Feature Router Loader

This module handles loading of feature-specific API routers.
These routers provide various application features like workflow automation,
web research, security, code analysis, and more.
"""

import logging

logger = logging.getLogger(__name__)


def load_feature_routers():
    """
    Dynamically load feature API routers with graceful fallback.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    optional_routers = []

    # WebSockets router
    try:
        from backend.api.websockets import router as websockets_router

        optional_routers.append((websockets_router, "", ["websockets"], "websockets"))
        logger.info("✅ Optional router loaded: websockets")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: websockets - {e}")

    # Workflow router
    try:
        from backend.api.workflow import router as workflow_router

        optional_routers.append(
            (workflow_router, "/workflow", ["workflow"], "workflow")
        )
        logger.info("✅ Optional router loaded: workflow")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: workflow - {e}")

    # Batch router
    try:
        from backend.api.batch import router as batch_router

        optional_routers.append((batch_router, "/batch", ["batch"], "batch"))
        logger.info("✅ Optional router loaded: batch")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: batch - {e}")

    # Advanced Workflow Orchestrator router (refactored module)
    try:
        from backend.services.advanced_workflow import router as orchestrator_router

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

    # Workflow Automation router (refactored module)
    try:
        from backend.services.workflow_automation import router as workflow_automation_router

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
                "",
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
                "",
                ["captcha", "web-research"],
                "captcha",
            )
        )
        logger.info("✅ Optional router loaded: captcha")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: captcha - {e}")

    # Natural Language Code Search router (Issue #232)
    try:
        from backend.api.natural_language_search import router as nl_search_router

        optional_routers.append(
            (
                nl_search_router,
                "",
                ["natural-language-search", "code-search"],
                "natural_language_search",
            )
        )
        logger.info("✅ Optional router loaded: natural_language_search")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: natural_language_search - {e}")

    # IDE Integration router (Issue #240)
    try:
        from backend.api.ide_integration import router as ide_router

        optional_routers.append(
            (
                ide_router,
                "/ide",
                ["ide", "code-intelligence", "real-time"],
                "ide_integration",
            )
        )
        logger.info("✅ Optional router loaded: ide_integration")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: ide_integration - {e}")

    return optional_routers
