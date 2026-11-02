# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The router catalogue: what routers exist, not the endpoints that serve them.

Split out of ``api/registry.py`` (#16375). That module held two things at once
-- a 330-line catalogue of ``RouterConfig`` literals and the read-only API that
publishes them -- and sat at 607 lines against a frozen ceiling of 604, so
gating its router could not land without splitting it. The catalogue is the half
that grows: every new router adds an entry here and nothing to the endpoints.

The types live here rather than in ``registry.py`` because the entries are the
only reason they exist. ``registry.py`` re-imports them, so ``registry.RouterConfig``
and ``registry.RouterStatus`` keep resolving for their existing readers.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class RouterStatus(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    LAZY_LOAD = "lazy_load"


# Performance optimization: O(1) lookup for enabled router statuses (Issue #326)
ENABLED_ROUTER_STATUSES = {RouterStatus.ENABLED, RouterStatus.LAZY_LOAD}


@dataclass
class RouterConfig:
    """Configuration for a single API router"""

    name: str
    module_path: str
    prefix: str
    tags: List[str]
    status: RouterStatus = RouterStatus.ENABLED
    dependencies: List[str] = field(default_factory=list)
    description: str | None = None
    version: str = "v1"
    requires_auth: bool = False
    rate_limit: Dict | None = None


def _get_core_system_routers() -> Dict[str, RouterConfig]:
    """
    Get core system router configurations.

    Issue #281: Extracted from _initialize_routers to reduce function length
    and improve maintainability of router definitions by category.

    Returns:
        Dict of core system router configurations
    """
    return {
        "system": RouterConfig(
            name="system",
            module_path="api.system",
            prefix="/api/system",
            tags=["system", "health"],
            description="System health, metrics, and information",
        ),
        "chat_consolidated": RouterConfig(
            name="chat_consolidated",
            module_path="api.chat",
            prefix="/api",
            tags=["chat", "consolidated", "all"],
            description=("CONSOLIDATED chat router with ALL functionality from 5 routers -" "ZERO functionality loss"),
            version="v1.0",
        ),
        "settings": RouterConfig(
            name="settings",
            module_path="api.settings",
            prefix="/api/settings",
            tags=["settings", "config"],
            description="Application settings and configuration",
        ),
        "cache": RouterConfig(
            name="cache",
            module_path="api.cache_management",
            prefix="/api/cache",
            tags=["cache", "management"],
            description="Cache management and clearing operations",
        ),
        "rum": RouterConfig(
            name="rum",
            module_path="api.rum",
            prefix="/api/rum",
            tags=["rum", "monitoring", "developer"],
            description="Real User Monitoring (RUM) for frontend event tracking",
        ),
        "developer": RouterConfig(
            name="developer",
            module_path="api.developer",
            prefix="/api/developer",
            tags=["developer", "debug", "config"],
            description="Developer mode configuration and debugging utilities",
        ),
        "websockets": RouterConfig(
            name="websockets",
            module_path="api.websockets",
            prefix="/api",  # routes carry their own /ws/... path below this
            tags=["websockets", "realtime"],
            description="WebSocket endpoints for real-time communication",
        ),
    }


def _get_knowledge_and_ai_routers() -> Dict[str, RouterConfig]:
    """
    Get knowledge management and AI-related router configurations.

    Issue #281: Extracted from _initialize_routers to reduce function length
    and improve maintainability of router definitions by category.

    Returns:
        Dict of knowledge and AI router configurations
    """
    return {
        "knowledge": RouterConfig(
            name="knowledge",
            module_path="api.knowledge",
            prefix="/api/knowledge_base",
            tags=["knowledge", "search"],
            status=RouterStatus.ENABLED,
            description="Knowledge base operations and search",
        ),
        "agent_config": RouterConfig(
            name="agent_config",
            module_path="api.agent_config",
            prefix="/api/agent_config",
            tags=["agent", "config"],
            description="Agent configuration and management",
        ),
        "prompts": RouterConfig(
            name="prompts",
            module_path="api.prompts",
            prefix="/api/prompts",
            tags=["prompts", "ai"],
            description="Prompt templates and management",
        ),
        "llm": RouterConfig(
            name="llm",
            module_path="api.llm",
            prefix="/api/llm",
            tags=["llm", "ai"],
            status=RouterStatus.LAZY_LOAD,
            description="LLM integration and management",
        ),
        "intelligent_agent": RouterConfig(
            name="intelligent_agent",
            module_path="api.intelligent_agent",
            prefix="/api/intelligent_agent",
            tags=["ai", "agent", "intelligence"],
            status=RouterStatus.LAZY_LOAD,  # Lazy load to avoid startup blocking
            description="Intelligent agent system for goal processing",
        ),
        "knowledge_mcp": RouterConfig(
            name="knowledge_mcp",
            module_path="api.knowledge_mcp",
            prefix="/api/knowledge",
            tags=["knowledge", "mcp", "llm"],
            status=RouterStatus.ENABLED,
            description="MCP bridge for LLM access to knowledge base via LlamaIndex",
        ),
    }


def _get_file_and_security_routers() -> Dict[str, RouterConfig]:
    """
    Get file management and security router configurations.

    Issue #281: Extracted from _initialize_routers to reduce function length
    and improve maintainability of router definitions by category.

    Returns:
        Dict of file and security router configurations
    """
    return {
        "files": RouterConfig(
            name="files",
            module_path="api.files",
            prefix="/api/files",
            tags=["files", "upload"],
            description="File operations and management",
        ),
        "templates": RouterConfig(
            name="templates",
            module_path="api.templates",
            prefix="/api/templates",
            tags=["templates"],
            description="Template management and rendering",
        ),
        "secrets": RouterConfig(
            name="secrets",
            module_path="api.secrets",
            prefix="/api/secrets",
            tags=["secrets", "security"],
            requires_auth=True,
            description="Secrets and credential management",
        ),
    }


def _get_dev_tool_routers() -> Dict[str, RouterConfig]:
    """Helper for _get_development_automation_routers. Ref: #1088.

    Return playwright, terminal, and logs router configs.
    """
    return {
        "playwright": RouterConfig(
            name="playwright",
            module_path="api.playwright",
            prefix="/api/playwright",
            tags=["automation", "browser"],
            description="Browser automation via Playwright",
        ),
        "terminal": RouterConfig(
            name="terminal",
            module_path="api.terminal",
            prefix="/api/terminal",
            tags=["terminal", "execution"],
            status=RouterStatus.ENABLED,  # Enable for fast backend
            description="Terminal execution and management",
        ),
        "logs": RouterConfig(
            name="logs",
            module_path="api.logs",
            prefix="/api/logs",
            tags=["logs", "monitoring"],
            status=RouterStatus.ENABLED,
            description="Log viewing and analysis",
        ),
    }


def _get_dev_workflow_routers() -> Dict[str, RouterConfig]:
    """Helper for _get_development_automation_routers. Ref: #1088.

    Return workflow, batch, research_browser, and hot_reload router configs.
    """
    return {
        "workflow": RouterConfig(
            name="workflow",
            module_path="api.workflow",
            prefix="/api/workflow",
            tags=["workflow", "automation"],
            status=RouterStatus.DISABLED,  # Not in fast backend
            description="Workflow automation and orchestration",
        ),
        "batch": RouterConfig(
            name="batch",
            module_path="api.batch_jobs",
            prefix="/api/batch-jobs",
            tags=["batch", "optimization"],
            description="Batch API endpoints for optimized initial loading",
        ),
        "research_browser": RouterConfig(
            name="research_browser",
            module_path="api.research_browser",
            prefix="/api/research-browser",
            tags=["research", "browser", "automation"],
            status=RouterStatus.ENABLED,
            description="Browser automation for research tasks with user interaction support",
        ),
        "hot_reload": RouterConfig(
            name="hot_reload",
            module_path="api.hot_reload",
            prefix="/api/hot-reload",
            tags=["development", "hot-reload"],
            status=RouterStatus.ENABLED,
            description="Hot reload functionality for chat workflow modules during development",
        ),
    }


def _get_development_automation_routers() -> Dict[str, RouterConfig]:
    """
    Get development and automation router configurations.

    Issue #281: Extracted from _initialize_routers to reduce function length
    and improve maintainability of router definitions by category.

    Returns:
        Dict of development and automation router configurations
    """
    return {**_get_dev_tool_routers(), **_get_dev_workflow_routers()}


def _get_monitoring_routers() -> Dict[str, RouterConfig]:
    """
    Get monitoring and analytics router configurations.

    Issue #281: Extracted from _initialize_routers to reduce function length
    and improve maintainability of router definitions by category.

    Returns:
        Dict of monitoring router configurations
    """
    return {
        "service_monitor": RouterConfig(
            name="service_monitor",
            module_path="api.service_monitor",
            prefix="/api/service-monitor",
            tags=["monitoring", "services"],
            description="Real-time service monitoring and health checks",
        ),
        "infrastructure_monitor": RouterConfig(
            name="infrastructure_monitor",
            module_path="api.infrastructure",
            prefix="/api/infrastructure",
            tags=["monitoring", "infrastructure", "multi-machine"],
            status=RouterStatus.ENABLED,
            description="Multi-machine infrastructure monitoring with service hierarchies",
        ),
        # Issue #69: monitoring_alerts removed - replaced by Prometheus AlertManager
        # Alerts now handled via alertmanager_webhook (Issue #346)
        "monitoring": RouterConfig(
            name="monitoring",
            module_path="api.monitoring",
            prefix="/api/monitoring",
            tags=["monitoring", "gpu", "npu", "performance"],
            status=RouterStatus.ENABLED,
            description=("Comprehensive performance monitoring for GPU/NPU utilization and " "multi-modal AI"),
        ),
        "system_validation": RouterConfig(
            name="system_validation",
            module_path="api.system_validation",
            prefix="/api/system-validation",
            tags=["validation", "system", "testing"],
            description="Comprehensive system validation and integration testing",
        ),
        "validation_dashboard": RouterConfig(
            name="validation_dashboard",
            module_path="api.validation_dashboard",
            prefix="/api/validation-dashboard",
            tags=["validation", "testing"],
            status=RouterStatus.ENABLED,  # Enable for fast backend
            description="Validation and testing dashboard",
        ),
        "startup": RouterConfig(
            name="startup",
            module_path="api.startup",
            prefix="/api/startup",
            tags=["startup", "status", "websockets"],
            status=RouterStatus.DISABLED,
            description="Friendly startup messages and status updates for frontend",
        ),
    }


def _get_user_management_routers() -> Dict[str, RouterConfig]:
    """
    Get user management router configurations.

    Issue #576: User management system with multi-tenancy support.

    Returns:
        Dict of user management router configurations
    """
    return {
        "user_management": RouterConfig(
            name="user_management",
            module_path="api.user_management",
            prefix="/api",
            tags=["users", "teams", "organizations", "auth"],
            status=RouterStatus.ENABLED,
            requires_auth=True,
            description=(
                "User management system with multi-tenancy, teams, RBAC, "
                "SSO integration, and MFA support (Issue #576)"
            ),
        ),
        "auth": RouterConfig(
            name="auth",
            module_path="api.auth",
            prefix="/api/auth",
            tags=["auth", "security"],
            status=RouterStatus.ENABLED,
            description="Authentication endpoints for login/logout/session management",
        ),
    }


def build_router_catalog() -> Dict[str, RouterConfig]:
    """Every router configuration, merged in category order (#281, #576).

    Later categories win on a duplicate name, as they did when these six calls
    sat inline in ``APIRegistry._initialize_routers``.
    """
    routers: Dict[str, RouterConfig] = {}
    routers.update(_get_core_system_routers())
    routers.update(_get_knowledge_and_ai_routers())
    routers.update(_get_file_and_security_routers())
    routers.update(_get_development_automation_routers())
    routers.update(_get_monitoring_routers())
    routers.update(_get_user_management_routers())
    return routers
