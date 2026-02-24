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
    ("api.websockets", "", ["websockets"], "websockets"),
    ("api.workflow", "/workflow", ["workflow"], "workflow"),
    ("api.batch", "/batch", ["batch"], "batch"),
    (
        "api.batch_jobs",
        "/batch-jobs",
        ["batch-jobs", "management"],
        "batch_jobs",
    ),
    (
        "api.orchestration",
        "/orchestrator",
        ["orchestrator"],
        "orchestrator",
    ),
    (
        "api.workflow_automation",
        "/workflow-automation",
        ["workflow-automation"],
        "workflow_automation",
    ),
    # Logging and configuration
    ("api.logs", "/logs", ["logs"], "logs"),
    (
        "api.log_forwarding",
        "/log-forwarding",
        ["log-forwarding"],
        "log_forwarding",
    ),
    ("api.secrets", "/secrets", ["secrets"], "secrets"),
    ("api.cache", "/cache", ["cache"], "cache"),
    ("api.registry", "/registry", ["registry"], "registry"),
    # AI and embeddings
    ("api.embeddings", "/embeddings", ["embeddings"], "embeddings"),
    ("api.multimodal", "/multimodal", ["multimodal"], "multimodal"),
    (
        "api.llm_optimization",
        "/llm-optimization",
        ["llm-optimization"],
        "llm_optimization",
    ),
    ("api.llm_awareness", "/llm-awareness", ["llm-awareness"], "llm_awareness"),
    # Web research and browser automation
    (
        "api.research_browser",
        "/research-browser",
        ["research-browser"],
        "research_browser",
    ),
    ("api.playwright", "/playwright", ["playwright"], "playwright"),
    ("api.vision", "/vision", ["vision", "gui-automation"], "vision"),
    (
        "api.web_research_settings",
        "/web-research-settings",
        ["web-research-settings"],
        "web_research_settings",
    ),
    ("api.captcha", "", ["captcha", "web-research"], "captcha"),
    # State and project management
    (
        "api.state_tracking",
        "/state-tracking",
        ["state-tracking"],
        "state_tracking",
    ),
    ("api.project_state", "/project-state", ["project-state"], "project_state"),
    ("api.phase_management", "/phases", ["phases"], "phase_management"),
    # Services and infrastructure
    ("api.services", "/services", ["services"], "services"),
    ("api.elevation", "/elevation", ["elevation"], "elevation"),
    ("api.auth", "/auth", ["auth"], "auth"),
    ("api.hot_reload", "/hot-reload", ["hot-reload"], "hot_reload"),
    ("api.startup", "/startup", ["startup"], "startup"),
    # Enterprise and scheduling
    ("api.enterprise_features", "/enterprise", ["enterprise"], "enterprise"),
    ("api.scheduler", "/scheduler", ["scheduler"], "scheduler"),
    ("api.templates", "/templates", ["templates"], "templates"),
    # Security and sandbox
    ("api.sandbox", "/sandbox", ["sandbox"], "sandbox"),
    ("api.security", "/security", ["security"], "security"),
    (
        "api.security_assessment",
        "",
        ["security-assessment"],
        "security_assessment",
    ),
    # Permission system v2 (Claude Code-style)
    ("api.permissions", "", ["permissions"], "permissions"),
    # Personality profiles (Issue #964)
    ("api.personality", "/personality", ["personality"], "personality"),
    # Self-improving tasks — adaptive task refinement and outcome learning (Issue #930)
    (
        "api.agents_self_improvement",
        "/agents",
        ["self-improvement", "agents"],
        "agents_self_improvement",
    ),
    # Code analysis and search
    ("api.code_search", "/code-search", ["code-search"], "code_search"),
    (
        "api.anti_pattern",
        "/anti-pattern",
        ["anti-pattern", "code-analysis"],
        "anti_pattern",
    ),
    (
        "api.code_intelligence",
        "/code-intelligence",
        ["code-intelligence", "code-analysis"],
        "code_intelligence",
    ),
    (
        "api.merge_conflict_resolution",
        "/code-intelligence/merge-conflicts",
        ["merge-conflicts", "code-intelligence", "git"],
        "merge_conflict_resolution",
    ),
    (
        "api.natural_language_search",
        "",
        ["natural-language-search", "code-search"],
        "natural_language_search",
    ),
    (
        "api.ide_integration",
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
    # Caching
    (
        "api.cache_management",
        "/cache-management",
        ["cache-management"],
        "cache_management",
    ),
    # Enhanced features
    (
        "api.enhanced_search",
        "/enhanced-search",
        ["enhanced-search"],
        "enhanced_search",
    ),
    (
        "api.enhanced_memory",
        "/enhanced-memory",
        ["enhanced-memory"],
        "enhanced_memory",
    ),
    (
        "api.development_speedup",
        "/dev-speedup",
        ["dev-speedup"],
        "development_speedup",
    ),
    (
        "api.advanced_control",
        "/advanced-control",
        ["advanced-control"],
        "advanced_control",
    ),
    # Long-running and validation
    (
        "api.long_running_operations",
        "/long-running",
        ["long-running"],
        "long_running_operations",
    ),
    (
        "api.system_validation",
        "/system-validation",
        ["system-validation"],
        "system_validation",
    ),
    (
        "api.validation_dashboard",
        "/validation-dashboard",
        ["validation-dashboard"],
        "validation_dashboard",
    ),
    # Knowledge and conversation
    (
        "api.knowledge_test",
        "/knowledge-test",
        ["knowledge-test"],
        "knowledge_test",
    ),
    (
        "api.knowledge_maintenance",
        "/knowledge-maintenance",
        ["knowledge-maintenance"],
        "knowledge_maintenance",
    ),
    # Issue #708: knowledge_search_aggregator, knowledge_ai_stack, knowledge_debug
    # consolidated into knowledge.py as sub-routers (backend.api.knowledge includes them)
    (
        "api.conversation_files",
        "/conversation-files",
        ["conversation-files"],
        "conversation_files",
    ),
    (
        "api.chat_knowledge",
        "/chat-knowledge",
        ["chat-knowledge"],
        "chat_knowledge",
    ),
    # NPU and Redis
    ("api.npu_workers", "", ["npu-workers"], "npu_workers"),
    ("api.redis_service", "/redis-service", ["redis-service"], "redis_service"),
    # Issue #729: infrastructure_nodes removed - now served by slm-server
    # Fleet host list for HostSelector (SSH/VNC terminal in chat)
    (
        "api.infrastructure",
        "/infrastructure",
        ["infrastructure"],
        "infrastructure",
    ),
    # Graph and entity features
    (
        "api.entity_extraction",
        "/entities",
        ["entity-extraction"],
        "entity_extraction",
    ),
    ("api.graph_rag", "/graph-rag", ["graph-rag"], "graph_rag"),
    # AI Stack integration (Issue #708 consolidation from app_factory_enhanced)
    (
        "api.ai_stack_integration",
        "/ai-stack",
        ["ai-stack"],
        "ai_stack_integration",
    ),
    (
        "api.knowledge_rag",
        "/knowledge_base/rag",
        ["knowledge-rag"],
        "knowledge_rag",
    ),
    # Admin feature flags and access control
    (
        "api.feature_flags",
        "/admin",
        ["admin", "feature-flags"],
        "feature_flags",
    ),
    # External tool integrations (Issue #61)
    (
        "api.integration_database",
        "/integrations/database",
        ["integrations-database"],
        "integration_database",
    ),
    (
        "api.integration_cloud",
        "/integrations/cloud",
        ["integrations-cloud"],
        "integration_cloud",
    ),
    (
        "api.integration_cicd",
        "/integrations/cicd",
        ["integrations-cicd"],
        "integration_cicd",
    ),
    (
        "api.integration_project_management",
        "/integrations/project-management",
        ["integrations-project-management"],
        "integration_project_management",
    ),
    (
        "api.integration_communication",
        "/integrations/communication",
        ["integrations-communication"],
        "integration_communication",
    ),
    (
        "api.integration_version_control",
        "/integrations/version-control",
        ["integrations-version-control"],
        "integration_version_control",
    ),
    (
        "api.integration_monitoring",
        "/integrations/monitoring",
        ["integrations-monitoring"],
        "integration_monitoring",
    ),
    # Skills repo management and governance MUST be registered before the base skills
    # router so their static path prefixes take precedence over skills' /{name} param.
    ("api.skills_repos", "/skills/repos", ["skills"], "skills-repos"),
    (
        "api.skills_governance",
        "/skills/governance",
        ["skills"],
        "skills-governance",
    ),
    # Skills system base (Issue #731) - registered AFTER sub-routers (see above)
    ("api.skills", "/skills", ["skills"], "skills"),
    # A2A (Agent2Agent) protocol (Issue #961)
    ("api.a2a", "/a2a", ["a2a"], "a2a"),
    # Knowledge graph pipeline (Issue #759)
    (
        "api.knowledge_graph_routes",
        "/knowledge-graph",
        ["knowledge-graph", "ecl-pipeline"],
        "knowledge_graph",
    ),
    # Natural language database queries - Vanna.ai integration (Issue #723)
    (
        "api.nl_database",
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
