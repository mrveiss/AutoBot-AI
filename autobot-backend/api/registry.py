# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified API Endpoint Registry
Single source of truth for all API endpoints and routing configuration
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from fastapi import APIRouter

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

# Create FastAPI router
router = APIRouter()


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
    description: Optional[str] = None
    version: str = "v1"
    requires_auth: bool = False
    rate_limit: Optional[Dict] = None


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
            module_path="backend.api.system",
            prefix="/api/system",
            tags=["system", "health"],
            description="System health, metrics, and information",
        ),
        "chat_consolidated": RouterConfig(
            name="chat_consolidated",
            module_path="backend.api.chat_consolidated",
            prefix="/api",
            tags=["chat", "consolidated", "all"],
            description=(
                "CONSOLIDATED chat router with ALL functionality from 5 routers -"
                "ZERO functionality loss"
            ),
            version="v1.0",
        ),
        "settings": RouterConfig(
            name="settings",
            module_path="backend.api.settings",
            prefix="/api/settings",
            tags=["settings", "config"],
            description="Application settings and configuration",
        ),
        "cache": RouterConfig(
            name="cache",
            module_path="backend.api.cache",
            prefix="/api/cache",
            tags=["cache", "management"],
            description="Cache management and clearing operations",
        ),
        "rum": RouterConfig(
            name="rum",
            module_path="backend.api.rum",
            prefix="/api/rum",
            tags=["rum", "monitoring", "developer"],
            description="Real User Monitoring (RUM) for frontend event tracking",
        ),
        "developer": RouterConfig(
            name="developer",
            module_path="backend.api.developer",
            prefix="/api/developer",
            tags=["developer", "debug", "config"],
            description="Developer mode configuration and debugging utilities",
        ),
        "websockets": RouterConfig(
            name="websockets",
            module_path="backend.api.websockets",
            prefix="",  # WebSocket routes don't use prefix
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
            module_path="backend.api.knowledge",
            prefix="/api/knowledge_base",
            tags=["knowledge", "search"],
            status=RouterStatus.ENABLED,
            description="Knowledge base operations and search",
        ),
        "agent_config": RouterConfig(
            name="agent_config",
            module_path="backend.api.agent_config",
            prefix="/api/agent-config",
            tags=["agent", "config"],
            description="Agent configuration and management",
        ),
        "prompts": RouterConfig(
            name="prompts",
            module_path="backend.api.prompts",
            prefix="/api/prompts",
            tags=["prompts", "ai"],
            description="Prompt templates and management",
        ),
        "llm": RouterConfig(
            name="llm",
            module_path="backend.api.llm",
            prefix="/api/llm",
            tags=["llm", "ai"],
            status=RouterStatus.LAZY_LOAD,
            description="LLM integration and management",
        ),
        "intelligent_agent": RouterConfig(
            name="intelligent_agent",
            module_path="backend.api.intelligent_agent",
            prefix="/api/intelligent-agent",
            tags=["ai", "agent", "intelligence"],
            status=RouterStatus.LAZY_LOAD,  # Lazy load to avoid startup blocking
            description="Intelligent agent system for goal processing",
        ),
        "knowledge_mcp": RouterConfig(
            name="knowledge_mcp",
            module_path="backend.api.knowledge_mcp",
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
            module_path="backend.api.files",
            prefix="/api/files",
            tags=["files", "upload"],
            description="File operations and management",
        ),
        "templates": RouterConfig(
            name="templates",
            module_path="backend.api.templates",
            prefix="/api/templates",
            tags=["templates"],
            description="Template management and rendering",
        ),
        "secrets": RouterConfig(
            name="secrets",
            module_path="backend.api.secrets",
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
            module_path="backend.api.playwright",
            prefix="/api/playwright",
            tags=["automation", "browser"],
            description="Browser automation via Playwright",
        ),
        "terminal": RouterConfig(
            name="terminal",
            module_path="backend.api.terminal",
            prefix="/api/terminal",
            tags=["terminal", "execution"],
            status=RouterStatus.ENABLED,  # Enable for fast backend
            description="Terminal execution and management",
        ),
        "logs": RouterConfig(
            name="logs",
            module_path="backend.api.logs",
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
            module_path="backend.api.workflow",
            prefix="/api/workflow",
            tags=["workflow", "automation"],
            status=RouterStatus.DISABLED,  # Not in fast backend
            description="Workflow automation and orchestration",
        ),
        "batch": RouterConfig(
            name="batch",
            module_path="backend.api.batch",
            prefix="/api/batch",
            tags=["batch", "optimization"],
            description="Batch API endpoints for optimized initial loading",
        ),
        "research_browser": RouterConfig(
            name="research_browser",
            module_path="backend.api.research_browser",
            prefix="/api/research",
            tags=["research", "browser", "automation"],
            status=RouterStatus.ENABLED,
            description="Browser automation for research tasks with user interaction support",
        ),
        "hot_reload": RouterConfig(
            name="hot_reload",
            module_path="backend.api.hot_reload",
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
            module_path="backend.api.service_monitor",
            prefix="/api/monitoring",
            tags=["monitoring", "services"],
            description="Real-time service monitoring and health checks",
        ),
        "infrastructure_monitor": RouterConfig(
            name="infrastructure_monitor",
            module_path="backend.api.infrastructure_monitor",
            prefix="/api/infrastructure",
            tags=["monitoring", "infrastructure", "multi-machine"],
            status=RouterStatus.ENABLED,
            description="Multi-machine infrastructure monitoring with service hierarchies",
        ),
        # Issue #69: monitoring_alerts removed - replaced by Prometheus AlertManager
        # Alerts now handled via alertmanager_webhook (Issue #346)
        "monitoring": RouterConfig(
            name="monitoring",
            module_path="backend.api.monitoring",
            prefix="/api/monitoring",
            tags=["monitoring", "gpu", "npu", "performance"],
            status=RouterStatus.ENABLED,
            description=(
                "Comprehensive performance monitoring for GPU/NPU utilization and "
                "multi-modal AI"
            ),
        ),
        "system_validation": RouterConfig(
            name="system_validation",
            module_path="backend.api.system_validation",
            prefix="/api/system_validation",
            tags=["validation", "system", "testing"],
            description="Comprehensive system validation and integration testing",
        ),
        "validation_dashboard": RouterConfig(
            name="validation_dashboard",
            module_path="backend.api.validation_dashboard",
            prefix="/api/validation-dashboard",
            tags=["validation", "testing"],
            status=RouterStatus.ENABLED,  # Enable for fast backend
            description="Validation and testing dashboard",
        ),
        "startup": RouterConfig(
            name="startup",
            module_path="backend.api.startup",
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
            module_path="backend.api.user_management",
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
            module_path="backend.api.auth",
            prefix="/api/auth",
            tags=["auth", "security"],
            status=RouterStatus.ENABLED,
            description="Authentication endpoints for login/logout/session management",
        ),
    }


class APIRegistry:
    """Central registry for all API endpoints and routers"""

    def __init__(self):
        """Initialize API registry with all router configurations."""
        self.routers = self._initialize_routers()

    def _initialize_routers(self) -> Dict[str, RouterConfig]:
        """Initialize all router configurations"""
        # Issue #281: Use extracted helpers for router definitions by category
        routers = {}
        routers.update(_get_core_system_routers())
        routers.update(_get_knowledge_and_ai_routers())
        routers.update(_get_file_and_security_routers())
        routers.update(_get_development_automation_routers())
        routers.update(_get_monitoring_routers())
        routers.update(_get_user_management_routers())  # Issue #576
        return routers

    def get_enabled_routers(self) -> Dict[str, RouterConfig]:
        """Get all enabled routers"""
        return {
            name: config
            for name, config in self.routers.items()
            if config.status in ENABLED_ROUTER_STATUSES
        }

    def get_router_by_name(self, name: str) -> Optional[RouterConfig]:
        """Get router configuration by name"""
        return self.routers.get(name)

    def get_routers_by_tag(self, tag: str) -> Dict[str, RouterConfig]:
        """Get all routers with specific tag"""
        return {
            name: config for name, config in self.routers.items() if tag in config.tags
        }

    def get_endpoint_list(self) -> List[Dict]:
        """Get list of all endpoints for documentation"""
        endpoints = []
        for name, config in self.get_enabled_routers().items():
            endpoints.append(
                {
                    "name": name,
                    "prefix": config.prefix,
                    "tags": config.tags,
                    "description": config.description,
                    "status": config.status.value,
                    "requires_auth": config.requires_auth,
                    "version": config.version,
                }
            )
        return endpoints

    def validate_dependencies(self) -> Dict[str, List[str]]:
        """Validate router dependencies"""
        errors = {}
        for name, config in self.routers.items():
            missing_deps = []
            for dep in config.dependencies:
                if dep not in self.routers:
                    missing_deps.append(dep)
            if missing_deps:
                errors[name] = missing_deps
        return errors


# Global registry instance
registry = APIRegistry()


def get_router_configs() -> Dict[str, RouterConfig]:
    """Get all router configurations"""
    return registry.get_enabled_routers()


def get_endpoint_documentation() -> List[Dict]:
    """Get endpoint documentation for API docs"""
    return registry.get_endpoint_list()


# ============================================================================
# FastAPI Router Endpoints
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_endpoints",
    error_code_prefix="REGISTRY",
)
@router.get("/endpoints")
async def list_endpoints():
    """List all registered API endpoints"""
    return {
        "endpoints": registry.get_endpoint_list(),
        "total": len(registry.get_enabled_routers()),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_routers",
    error_code_prefix="REGISTRY",
)
@router.get("/routers")
async def list_routers():
    """List all registered routers with full configuration"""
    routers_data = {}
    for name, config in registry.get_enabled_routers().items():
        routers_data[name] = {
            "name": config.name,
            "module_path": config.module_path,
            "prefix": config.prefix,
            "tags": config.tags,
            "status": config.status.value,
            "description": config.description,
            "version": config.version,
            "requires_auth": config.requires_auth,
            "dependencies": config.dependencies,
        }
    return routers_data


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_router_details",
    error_code_prefix="REGISTRY",
)
@router.get("/router/{router_name}")
async def get_router_details(router_name: str):
    """Get details for a specific router"""
    config = registry.get_router_by_name(router_name)
    if not config:
        return {"error": f"Router '{router_name}' not found"}

    return {
        "name": config.name,
        "module_path": config.module_path,
        "prefix": config.prefix,
        "tags": config.tags,
        "status": config.status.value,
        "description": config.description,
        "version": config.version,
        "requires_auth": config.requires_auth,
        "dependencies": config.dependencies,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_tags",
    error_code_prefix="REGISTRY",
)
@router.get("/tags")
async def list_tags():
    """List all unique tags across all routers"""
    all_tags = set()
    for config in registry.routers.values():
        all_tags.update(config.tags)
    return {"tags": sorted(list(all_tags))}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_routers_by_tag",
    error_code_prefix="REGISTRY",
)
@router.get("/tags/{tag}")
async def get_routers_by_tag(tag: str):
    """Get all routers with a specific tag"""
    routers_with_tag = registry.get_routers_by_tag(tag)
    return {
        "tag": tag,
        "routers": list(routers_with_tag),
        "count": len(routers_with_tag),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="validate_dependencies",
    error_code_prefix="REGISTRY",
)
@router.get("/validate")
async def validate_dependencies():
    """Validate router dependencies"""
    errors = registry.validate_dependencies()
    return {"valid": len(errors) == 0, "errors": errors}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="registry_health",
    error_code_prefix="REGISTRY",
)
@router.get("/health")
async def registry_health():
    """Health check for registry system"""
    return {
        "status": "healthy",
        "total_routers": len(registry.routers),
        "enabled_routers": len(registry.get_enabled_routers()),
        "disabled_routers": len(
            [c for c in registry.routers.values() if c.status == RouterStatus.DISABLED]
        ),
    }
