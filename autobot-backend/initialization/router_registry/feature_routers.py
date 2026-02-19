# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Feature Router Loader

This module handles loading of feature-specific API routers.
These routers provide various application features like workflow automation,
web research, security, code analysis, and more.

Issue #281: Refactored from 716 lines of repetitive try/except blocks to
data-driven configuration pattern for improved maintainability.
"""

import importlib
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


# Issue #281: Router configurations as data instead of repetitive code blocks
# Format: (module_path, prefix, tags, name)
FEATURE_ROUTER_CONFIGS: List[Tuple[str, str, List[str], str]] = [
    # Core workflow and batch processing
    ("backend.api.websockets", "", ["websockets"], "websockets"),
    ("backend.api.workflow", "/workflow", ["workflow"], "workflow"),
    ("backend.api.batch", "/batch", ["batch"], "batch"),
    (
        "backend.api.batch_jobs",
        "/batch-jobs",
        ["batch-jobs", "management"],
        "batch_jobs",
    ),
    (
        "backend.services.advanced_workflow",
        "/orchestrator",
        ["orchestrator"],
        "orchestrator",
    ),
    (
        "backend.services.workflow_automation",
        "/workflow-automation",
        ["workflow-automation"],
        "workflow_automation",
    ),
    # Logging and configuration
    ("backend.api.logs", "/logs", ["logs"], "logs"),
    (
        "backend.api.log_forwarding",
        "/log-forwarding",
        ["log-forwarding"],
        "log_forwarding",
    ),
    ("backend.api.secrets", "/secrets", ["secrets"], "secrets"),
    ("backend.api.cache", "/cache", ["cache"], "cache"),
    ("backend.api.registry", "/registry", ["registry"], "registry"),
    # AI and embeddings
    ("backend.api.embeddings", "/embeddings", ["embeddings"], "embeddings"),
    ("backend.api.multimodal", "/multimodal", ["multimodal"], "multimodal"),
    (
        "backend.api.llm_optimization",
        "/llm-optimization",
        ["llm-optimization"],
        "llm_optimization",
    ),
    ("backend.api.llm_awareness", "/llm-awareness", ["llm-awareness"], "llm_awareness"),
    # Web research and browser automation
    (
        "backend.api.research_browser",
        "/research-browser",
        ["research-browser"],
        "research_browser",
    ),
    ("backend.api.playwright", "/playwright", ["playwright"], "playwright"),
    ("backend.api.vision", "/vision", ["vision", "gui-automation"], "vision"),
    (
        "backend.api.web_research_settings",
        "/web-research-settings",
        ["web-research-settings"],
        "web_research_settings",
    ),
    ("backend.api.captcha", "", ["captcha", "web-research"], "captcha"),
    # State and project management
    (
        "backend.api.state_tracking",
        "/state-tracking",
        ["state-tracking"],
        "state_tracking",
    ),
    ("backend.api.project_state", "/project-state", ["project-state"], "project_state"),
    ("backend.api.phase_management", "/phases", ["phases"], "phase_management"),
    # Services and infrastructure
    ("backend.api.services", "/services", ["services"], "services"),
    ("backend.api.elevation", "/elevation", ["elevation"], "elevation"),
    ("backend.api.auth", "/auth", ["auth"], "auth"),
    ("backend.api.hot_reload", "/hot-reload", ["hot-reload"], "hot_reload"),
    ("backend.api.startup", "/startup", ["startup"], "startup"),
    # Enterprise and scheduling
    ("backend.api.enterprise_features", "/enterprise", ["enterprise"], "enterprise"),
    ("backend.api.scheduler", "/scheduler", ["scheduler"], "scheduler"),
    ("backend.api.templates", "/templates", ["templates"], "templates"),
    # Security and sandbox
    ("backend.api.sandbox", "/sandbox", ["sandbox"], "sandbox"),
    ("backend.api.security", "/security", ["security"], "security"),
    (
        "backend.api.security_assessment",
        "",
        ["security-assessment"],
        "security_assessment",
    ),
    # Permission system v2 (Claude Code-style)
    ("backend.api.permissions", "", ["permissions"], "permissions"),
    # Code analysis and search
    ("backend.api.code_search", "/code-search", ["code-search"], "code_search"),
    (
        "backend.api.anti_pattern",
        "/anti-pattern",
        ["anti-pattern", "code-analysis"],
        "anti_pattern",
    ),
    (
        "backend.api.code_intelligence",
        "/code-intelligence",
        ["code-intelligence", "code-analysis"],
        "code_intelligence",
    ),
    (
        "backend.api.merge_conflict_resolution",
        "/code-intelligence/merge-conflicts",
        ["merge-conflicts", "code-intelligence", "git"],
        "merge_conflict_resolution",
    ),
    (
        "backend.api.natural_language_search",
        "",
        ["natural-language-search", "code-search"],
        "natural_language_search",
    ),
    (
        "backend.api.ide_integration",
        "/ide",
        ["ide", "code-intelligence", "real-time"],
        "ide_integration",
    ),
    (
        "routers.code_completion",
        "/code-completion",
        ["code-completion", "patterns", "ml"],
        "code_completion",
    ),
    (
        "routers.model_management",
        "/code-completion/model",
        ["ml-models", "training", "serving"],
        "model_management",
    ),
    (
        "routers.feedback",
        "/code-completion/feedback",
        ["feedback", "learning-loop"],
        "feedback",
    ),
    # Orchestration and caching
    ("backend.api.orchestration", "/orchestration", ["orchestration"], "orchestration"),
    (
        "backend.api.cache_management",
        "/cache-management",
        ["cache-management"],
        "cache_management",
    ),
    # Enhanced features
    (
        "backend.api.enhanced_search",
        "/enhanced-search",
        ["enhanced-search"],
        "enhanced_search",
    ),
    (
        "backend.api.enhanced_memory",
        "/enhanced-memory",
        ["enhanced-memory"],
        "enhanced_memory",
    ),
    (
        "backend.api.development_speedup",
        "/dev-speedup",
        ["dev-speedup"],
        "development_speedup",
    ),
    (
        "backend.api.advanced_control",
        "/advanced-control",
        ["advanced-control"],
        "advanced_control",
    ),
    # Long-running and validation
    (
        "backend.api.long_running_operations",
        "/long-running",
        ["long-running"],
        "long_running_operations",
    ),
    (
        "backend.api.system_validation",
        "/system-validation",
        ["system-validation"],
        "system_validation",
    ),
    (
        "backend.api.validation_dashboard",
        "/validation-dashboard",
        ["validation-dashboard"],
        "validation_dashboard",
    ),
    # Knowledge and conversation
    (
        "backend.api.knowledge_test",
        "/knowledge-test",
        ["knowledge-test"],
        "knowledge_test",
    ),
    (
        "backend.api.knowledge_maintenance",
        "/knowledge-maintenance",
        ["knowledge-maintenance"],
        "knowledge_maintenance",
    ),
    # Issue #708: knowledge_search_aggregator, knowledge_ai_stack, knowledge_debug
    # consolidated into knowledge.py as sub-routers (backend.api.knowledge includes them)
    (
        "backend.api.conversation_files",
        "/conversation-files",
        ["conversation-files"],
        "conversation_files",
    ),
    (
        "backend.api.chat_knowledge",
        "/chat-knowledge",
        ["chat-knowledge"],
        "chat_knowledge",
    ),
    # NPU and Redis
    ("backend.api.npu_workers", "", ["npu-workers"], "npu_workers"),
    ("backend.api.redis_service", "/redis-service", ["redis-service"], "redis_service"),
    # Issue #729: infrastructure_nodes removed - now served by slm-server
    # Graph and entity features
    (
        "backend.api.entity_extraction",
        "/entities",
        ["entity-extraction"],
        "entity_extraction",
    ),
    ("backend.api.graph_rag", "/graph-rag", ["graph-rag"], "graph_rag"),
    # AI Stack integration (Issue #708 consolidation from app_factory_enhanced)
    (
        "backend.api.ai_stack_integration",
        "/ai-stack",
        ["ai-stack"],
        "ai_stack_integration",
    ),
    (
        "backend.api.knowledge_rag",
        "/knowledge_base/rag",
        ["knowledge-rag"],
        "knowledge_rag",
    ),
    # Admin feature flags and access control
    (
        "backend.api.feature_flags",
        "/admin",
        ["admin", "feature-flags"],
        "feature_flags",
    ),
    # External tool integrations (Issue #61)
    (
        "backend.api.integration_database",
        "/integrations/database",
        ["integrations-database"],
        "integration_database",
    ),
    (
        "backend.api.integration_cloud",
        "/integrations/cloud",
        ["integrations-cloud"],
        "integration_cloud",
    ),
    (
        "backend.api.integration_cicd",
        "/integrations/cicd",
        ["integrations-cicd"],
        "integration_cicd",
    ),
    (
        "backend.api.integration_project_management",
        "/integrations/project-management",
        ["integrations-project-management"],
        "integration_project_management",
    ),
    (
        "backend.api.integration_communication",
        "/integrations/communication",
        ["integrations-communication"],
        "integration_communication",
    ),
    (
        "backend.api.integration_version_control",
        "/integrations/version-control",
        ["integrations-version-control"],
        "integration_version_control",
    ),
    (
        "backend.api.integration_monitoring",
        "/integrations/monitoring",
        ["integrations-monitoring"],
        "integration_monitoring",
    ),
    # Skills repo management and governance MUST be registered before the base skills
    # router so their static path prefixes take precedence over skills' /{name} param.
    ("backend.api.skills_repos", "/skills/repos", ["skills"], "skills-repos"),
    (
        "backend.api.skills_governance",
        "/skills/governance",
        ["skills"],
        "skills-governance",
    ),
    # Skills system base (Issue #731) - registered AFTER sub-routers (see above)
    ("backend.api.skills", "/skills", ["skills"], "skills"),
    # A2A (Agent2Agent) protocol (Issue #961)
    ("backend.api.a2a", "/a2a", ["a2a"], "a2a"),
    # Knowledge graph pipeline (Issue #759)
    (
        "backend.api.knowledge_graph_routes",
        "/knowledge-graph",
        ["knowledge-graph", "ecl-pipeline"],
        "knowledge_graph",
    ),
    # Natural language database queries - Vanna.ai integration (Issue #723)
    (
        "backend.api.nl_database",
        "/nl-database",
        ["nl-database", "vanna", "natural-language-sql"],
        "nl_database",
    ),
]


def _load_single_router(
    module_path: str, prefix: str, tags: List[str], name: str
) -> Tuple | None:
    """
    Load a single router with graceful fallback.

    Issue #281: Extracted helper for loading individual routers to eliminate
    repetitive try/except blocks and enable data-driven router loading.

    Args:
        module_path: Full Python module path (e.g., 'backend.api.workflow')
        prefix: URL prefix for the router (e.g., '/workflow')
        tags: List of OpenAPI tags for the router
        name: Human-readable name for logging

    Returns:
        Tuple of (router, prefix, tags, name) if successful, None otherwise
    """
    try:
        module = importlib.import_module(module_path)
        router = getattr(module, "router")
        logger.info("✅ Optional router loaded: %s", name)
        return (router, prefix, tags, name)
    except ImportError as e:
        logger.warning("⚠️ Optional router not available: %s - %s", name, e)
        return None
    except AttributeError as e:
        logger.warning(
            "⚠️ Router not found in module %s: %s - %s", module_path, name, e
        )
        return None


def load_feature_routers() -> List[Tuple]:
    """
    Dynamically load feature API routers with graceful fallback.

    Issue #281: Refactored to use data-driven configuration pattern.
    Original implementation had 53 repetitive try/except blocks (~716 lines).
    Now uses FEATURE_ROUTER_CONFIGS list and _load_single_router helper.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    optional_routers = []

    for module_path, prefix, tags, name in FEATURE_ROUTER_CONFIGS:
        result = _load_single_router(module_path, prefix, tags, name)
        if result:
            optional_routers.append(result)

    logger.info(
        "📊 Loaded %s/%s feature routers",
        len(optional_routers),
        len(FEATURE_ROUTER_CONFIGS),
    )
    return optional_routers
