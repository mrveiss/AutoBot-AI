# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unified API Endpoint Registry
Single source of truth for all API endpoints and routing configuration
"""

from typing import Dict, List

from fastapi import APIRouter, Depends, Request

from api.registry_catalog import (
    ENABLED_ROUTER_STATUSES,
    RouterConfig,
    RouterStatus,
    build_router_catalog,
)
from api.schemas_workflows import (
    RegistryEndpointsResponse,
    RegistryRouterDetailResponse,
    RegistryRoutersResponse,
    RegistryTagRoutersResponse,
    RegistryTagsResponse,
    RegistryValidateResponse,
)
from api.system_health import ComponentHealth, register_health_probe
from api.user_management.dependencies import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

# Re-exported, not merely imported: `api_endpoint_migrations_test.py` reads
# `registry.RouterConfig` and `registry.RouterStatus` off this module, so the
# catalogue split (#16375) must not move them out of this namespace.
__all__ = [
    "ENABLED_ROUTER_STATUSES",
    "APIRegistry",
    "RouterConfig",
    "RouterStatus",
    "get_endpoint_documentation",
    "get_router_configs",
    "registry",
    "router",
]

# #16375: every route here was reachable anonymously. Gated at the ROUTER so a
# route added later inherits it. Authentication only:
# a read-only map of the API's own routes.
router = APIRouter(dependencies=[Depends(get_current_user)])


class APIRegistry:
    """Central registry for all API endpoints and routers"""

    def __init__(self):
        """Initialize API registry with all router configurations."""
        self.routers = self._initialize_routers()

    def _initialize_routers(self) -> Dict[str, RouterConfig]:
        """Initialize all router configurations (#281, #576)."""
        return build_router_catalog()

    def get_enabled_routers(self) -> Dict[str, RouterConfig]:
        """Get all enabled routers"""
        return {name: config for name, config in self.routers.items() if config.status in ENABLED_ROUTER_STATUSES}

    def get_router_by_name(self, name: str) -> RouterConfig | None:
        """Get router configuration by name"""
        return self.routers.get(name)

    def get_routers_by_tag(self, tag: str) -> Dict[str, RouterConfig]:
        """Get all routers with specific tag"""
        return {name: config for name, config in self.routers.items() if tag in config.tags}

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


@router.get("/endpoints", response_model=RegistryEndpointsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_endpoints",
    error_code_prefix="REGISTRY",
)
async def list_endpoints():
    """List all registered API endpoints"""
    return {
        "endpoints": registry.get_endpoint_list(),
        "total": len(registry.get_enabled_routers()),
    }


@router.get("/routers", response_model=RegistryRoutersResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_routers",
    error_code_prefix="REGISTRY",
)
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


@router.get("/router/{router_name}", response_model=RegistryRouterDetailResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_router_details",
    error_code_prefix="REGISTRY",
)
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


@router.get("/tags", response_model=RegistryTagsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_tags",
    error_code_prefix="REGISTRY",
)
async def list_tags():
    """List all unique tags across all routers"""
    all_tags = set()
    for config in registry.routers.values():
        all_tags.update(config.tags)
    return {"tags": sorted(list(all_tags))}


@router.get("/tags/{tag}", response_model=RegistryTagRoutersResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_routers_by_tag",
    error_code_prefix="REGISTRY",
)
async def get_routers_by_tag(tag: str):
    """Get all routers with a specific tag"""
    routers_with_tag = registry.get_routers_by_tag(tag)
    return {
        "tag": tag,
        "routers": list(routers_with_tag),
        "count": len(routers_with_tag),
    }


@router.get("/validate", response_model=RegistryValidateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="validate_dependencies",
    error_code_prefix="REGISTRY",
)
async def validate_dependencies():
    """Validate router dependencies"""
    errors = registry.validate_dependencies()
    return {"valid": len(errors) == 0, "errors": errors}


@register_health_probe("registry")
async def probe_registry(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for the API endpoint registry."""
    try:
        if not registry.routers:
            return ComponentHealth(
                name="registry",
                status="degraded",
                detail="no routers registered",
            )
        return ComponentHealth(
            name="registry",
            status="ok",
            data={"total_routers": len(registry.routers)},
        )
    except Exception as exc:
        return ComponentHealth(
            name="registry",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )
