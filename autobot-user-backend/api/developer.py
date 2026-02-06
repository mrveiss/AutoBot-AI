# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Developer API Router

Provides developer mode functionality including:
- API endpoint registry listing all available endpoints
- Enhanced error responses for undefined endpoints
- Debug information and system diagnostics
"""

import logging
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.services.config_service import ConfigService
from backend.type_defs.common import Metadata
from src.config import unified_config_manager
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)


class APIRegistry:
    """Registry to track all API endpoints across routers"""

    def __init__(self):
        """Initialize API registry with empty endpoints and routers."""
        self.endpoints: Dict[str, Metadata] = {}
        self.routers: List[str] = []

    def register_router(self, router_name: str, router_instance, prefix: str = ""):
        """Register a router and its endpoints"""
        self.routers.append(router_name)

        for route in router_instance.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                for method in route.methods:
                    if method != "HEAD":  # Skip HEAD methods
                        endpoint_key = f"{method} {prefix}{route.path}"
                        self.endpoints[endpoint_key] = {
                            "router": router_name,
                            "path": f"{prefix}{route.path}",
                            "method": method,
                            "name": getattr(route, "name", "unnamed"),
                            "summary": getattr(route, "summary", ""),
                            "tags": getattr(route, "tags", []),
                        }

    def get_all_endpoints(self) -> Metadata:
        """Get all registered endpoints"""
        return {
            "total_endpoints": len(self.endpoints),
            "routers": self.routers,
            "endpoints": self.endpoints,
        }

    def find_similar_endpoints(self, path: str, method: str) -> List[str]:
        """Find similar endpoints for helpful error messages"""
        similar = []
        path_lower = path.lower()

        for endpoint_key, endpoint_info in self.endpoints.items():
            endpoint_path = endpoint_info["path"].lower()
            endpoint_method = endpoint_info["method"]

            # Exact path match but different method
            if endpoint_path == path_lower and endpoint_method != method:
                similar.append(
                    f"{endpoint_method} {endpoint_info['path']} (different method)"
                )

            # Similar path (contains or partial match)
            elif path_lower in endpoint_path or endpoint_path in path_lower:
                similar.append(
                    f"{endpoint_method} {endpoint_info['path']} (similar path)"
                )

        return similar[:5]  # Limit to 5 suggestions


# Global registry instance
api_registry = APIRegistry()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_api_endpoints",
    error_code_prefix="DEVELOPER",
)
@router.get("/endpoints")
async def get_api_endpoints():
    """Get all registered API endpoints (developer mode)"""
    developer_mode = unified_config_manager.get_nested("developer.enabled", False)

    if not developer_mode:
        raise HTTPException(status_code=403, detail="Developer mode is not enabled")

    return api_registry.get_all_endpoints()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_developer_config",
    error_code_prefix="DEVELOPER",
)
@router.get("/config")
async def get_developer_config():
    """Get developer mode configuration"""
    developer_config = unified_config_manager.get_nested("developer", {})
    return {
        "enabled": developer_config.get("enabled", False),
        "enhanced_errors": developer_config.get("enhanced_errors", True),
        "endpoint_suggestions": developer_config.get("endpoint_suggestions", True),
        "debug_logging": developer_config.get("debug_logging", False),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_developer_config",
    error_code_prefix="DEVELOPER",
)
@router.post("/config")
async def update_developer_config(config: dict):
    """Update developer mode configuration"""
    # Update the configuration
    current_config = unified_config_manager.get_nested("developer", {})
    current_config.update(config)

    # Save to config file
    unified_config_manager.set_nested("developer", current_config)
    unified_config_manager.save_settings()
    ConfigService.clear_cache()

    logger.info("Developer configuration updated: %s", config)
    return {"status": "success", "config": current_config}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_info",
    error_code_prefix="DEVELOPER",
)
@router.get("/system-info")
async def get_system_info():
    """Get system information for debugging"""
    developer_mode = unified_config_manager.get_nested("developer.enabled", False)

    if not developer_mode:
        raise HTTPException(status_code=403, detail="Developer mode is not enabled")

    return {
        "config_loaded": bool(unified_config_manager.to_dict()),
        "backend_config": unified_config_manager.get_backend_config(),
        "redis_config": unified_config_manager.get_redis_config(),
        "llm_config": unified_config_manager.get_nested("llm_config", {}),
        "available_routers": api_registry.routers,
    }


# Custom exception handler for 404 errors with developer mode enhancements
async def enhanced_404_handler(request: Request, exc: HTTPException):
    """Enhanced 404 handler that provides helpful suggestions in developer mode"""
    developer_mode = unified_config_manager.get_nested("developer.enabled", False)
    enhanced_errors = unified_config_manager.get_nested(
        "developer.enhanced_errors", True
    )

    if not developer_mode or not enhanced_errors:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    path = request.url.path
    method = request.method

    # Find similar endpoints
    similar_endpoints = api_registry.find_similar_endpoints(path, method)

    response_content = {
        "detail": f"Endpoint not found: {method} {path}",
        "developer_info": {
            "requested_method": method,
            "requested_path": path,
            "similar_endpoints": similar_endpoints,
            "total_available_endpoints": len(api_registry.endpoints),
            "available_routers": api_registry.routers,
        },
    }

    if not similar_endpoints:
        response_content["developer_info"][
            "suggestion"
        ] = "Check available endpoints at /api/developer/endpoints"

    return JSONResponse(status_code=404, content=response_content)


# Custom exception handler for 405 errors (Method Not Allowed)
async def enhanced_405_handler(request: Request, exc: HTTPException):
    """Enhanced 405 handler for developer mode"""
    developer_mode = unified_config_manager.get_nested("developer.enabled", False)
    enhanced_errors = unified_config_manager.get_nested(
        "developer.enhanced_errors", True
    )

    if not developer_mode or not enhanced_errors:
        return JSONResponse(status_code=405, content={"detail": "Method Not Allowed"})

    path = request.url.path
    method = request.method

    # Find endpoints with same path but different methods
    allowed_methods = []
    for endpoint_key, endpoint_info in api_registry.endpoints.items():
        if endpoint_info["path"] == path:
            allowed_methods.append(endpoint_info["method"])

    response_content = {
        "detail": f"Method {method} not allowed for {path}",
        "developer_info": {
            "requested_method": method,
            "requested_path": path,
            "allowed_methods": allowed_methods,
            "suggestion": (
                f"Try one of: {', '.join(allowed_methods)}"
                if allowed_methods
                else "No methods available for this path"
            ),
        },
    }

    return JSONResponse(status_code=405, content=response_content)
