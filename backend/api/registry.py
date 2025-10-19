"""
Unified API Endpoint Registry
Single source of truth for all API endpoints and routing configuration
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter

from src.constants.network_constants import NetworkConstants

# Create FastAPI router
router = APIRouter()


class RouterStatus(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    LAZY_LOAD = "lazy_load"


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


class APIRegistry:
    """Central registry for all API endpoints and routers"""

    def __init__(self):
        self.routers = self._initialize_routers()

    def _initialize_routers(self) -> Dict[str, RouterConfig]:
        """Initialize all router configurations"""
        return {
            # Core System Routers
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
                description="CONSOLIDATED chat router with ALL functionality from 5 routers - ZERO functionality loss",
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
            # Chat and Communication - NOW CONSOLIDATED
            # OLD: Separate chat.py, async_chat.py, chat_unified.py, chat_improved.py, chat_knowledge.py
            # NEW: All functionality consolidated into single router with ZERO loss
            "websockets": RouterConfig(
                name="websockets",
                module_path="backend.api.websockets",
                prefix="",  # WebSocket routes don't use prefix
                tags=["websockets", "realtime"],
                description="WebSocket endpoints for real-time communication",
            ),
            # Knowledge Management
            "knowledge": RouterConfig(
                name="knowledge",
                module_path="backend.api.knowledge",
                prefix="/api/knowledge_base",
                tags=["knowledge", "search"],
                status=RouterStatus.ENABLED,
                description="Knowledge base operations and search",
            ),
            # chat_knowledge functionality now included in consolidated chat router
            # Agent and AI
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
            # File and Content Management
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
            # Security
            "secrets": RouterConfig(
                name="secrets",
                module_path="backend.api.secrets",
                prefix="/api/secrets",
                tags=["secrets", "security"],
                requires_auth=True,
                description="Secrets and credential management",
            ),
            # Development and Automation
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
            "workflow": RouterConfig(
                name="workflow",
                module_path="backend.api.workflow",
                prefix="/api/workflow",
                tags=["workflow", "automation"],
                status=RouterStatus.DISABLED,  # Not in fast backend
                description="Workflow automation and orchestration",
            ),
            # Performance Optimization
            "batch": RouterConfig(
                name="batch",
                module_path="backend.api.batch",
                prefix="/api/batch",
                tags=["batch", "optimization"],
                description="Batch API endpoints for optimized initial loading",
            ),
            # Monitoring and Analytics
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
            "monitoring_alerts": RouterConfig(
                name="monitoring_alerts",
                module_path="backend.api.monitoring_alerts",
                prefix="/api/alerts",
                tags=["alerts", "notifications", "monitoring"],
                status=RouterStatus.ENABLED,
                description="Advanced monitoring alerts and notifications system",
            ),
            "monitoring": RouterConfig(
                name="monitoring",
                module_path="backend.api.monitoring",
                prefix="/api/monitoring/phase9",
                tags=["monitoring", "phase9", "gpu", "npu", "performance"],
                status=RouterStatus.ENABLED,
                description="Phase 9 comprehensive performance monitoring for GPU/NPU utilization and multi-modal AI",
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
            # Intelligence and AI Agent
            "intelligent_agent": RouterConfig(
                name="intelligent_agent",
                module_path="backend.api.intelligent_agent",
                prefix="/api/intelligent-agent",
                tags=["ai", "agent", "intelligence"],
                status=RouterStatus.LAZY_LOAD,  # Lazy load to avoid startup blocking
                description="Intelligent agent system for goal processing",
            ),
            # MCP Bridge for Knowledge Base
            "knowledge_mcp": RouterConfig(
                name="knowledge_mcp",
                module_path="backend.api.knowledge_mcp",
                prefix="/api/knowledge",
                tags=["knowledge", "mcp", "llm"],
                status=RouterStatus.ENABLED,
                description="MCP bridge for LLM access to knowledge base via LlamaIndex",
            ),
            # Research and Browser Automation
            "research_browser": RouterConfig(
                name="research_browser",
                module_path="backend.api.research_browser",
                prefix="/api/research",
                tags=["research", "browser", "automation"],
                status=RouterStatus.ENABLED,
                description="Browser automation for research tasks with user interaction support",
            ),
            # Startup Status and Messages - DISABLED per user request to remove splash screen
            "startup": RouterConfig(
                name="startup",
                module_path="backend.api.startup",
                prefix="/api/startup",
                tags=["startup", "status", "websockets"],
                status=RouterStatus.DISABLED,
                description="Friendly startup messages and status updates for frontend",
            ),
            # Hot Reload for Development
            "hot_reload": RouterConfig(
                name="hot_reload",
                module_path="backend.api.hot_reload",
                prefix="/api/hot-reload",
                tags=["development", "hot-reload"],
                status=RouterStatus.ENABLED,
                description="Hot reload functionality for chat workflow modules during development",
            ),
        }

    def get_enabled_routers(self) -> Dict[str, RouterConfig]:
        """Get all enabled routers"""
        return {
            name: config
            for name, config in self.routers.items()
            if config.status in [RouterStatus.ENABLED, RouterStatus.LAZY_LOAD]
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


@router.get("/endpoints")
async def list_endpoints():
    """List all registered API endpoints"""
    return {
        "endpoints": registry.get_endpoint_list(),
        "total": len(registry.get_enabled_routers()),
    }


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


@router.get("/tags")
async def list_tags():
    """List all unique tags across all routers"""
    all_tags = set()
    for config in registry.routers.values():
        all_tags.update(config.tags)
    return {"tags": sorted(list(all_tags))}


@router.get("/tags/{tag}")
async def get_routers_by_tag(tag: str):
    """Get all routers with a specific tag"""
    routers_with_tag = registry.get_routers_by_tag(tag)
    return {
        "tag": tag,
        "routers": [name for name in routers_with_tag.keys()],
        "count": len(routers_with_tag),
    }


@router.get("/validate")
async def validate_dependencies():
    """Validate router dependencies"""
    errors = registry.validate_dependencies()
    return {"valid": len(errors) == 0, "errors": errors}


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
