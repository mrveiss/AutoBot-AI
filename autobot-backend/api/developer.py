# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Developer API Router

Provides developer mode functionality including:
- API endpoint registry listing all available endpoints
- Enhanced error responses for undefined endpoints
- Debug information and system diagnostics
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api.schemas_system import (
    DeveloperConfigResponse,
    DeveloperConfigUpdateResponse,
    DeveloperEndpointsResponse,
    DeveloperSystemInfoResponse,
)
from api.self_capabilities import discover_endpoints
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from config import config_manager
from services.config_manager_writer import merge_nested_and_save
from services.config_service import ConfigService
from type_defs.common import Metadata

router = APIRouter(dependencies=[Depends(check_admin_permission)])
logger = get_logger(__name__)


def find_similar_endpoints(endpoints: List[Metadata], path: str, method: str) -> List[str]:
    """Find similar endpoints for helpful error messages (#22274: over the canonical route records)."""
    similar = []
    path_lower = path.lower()
    for ep in endpoints:
        endpoint_path = ep["path"].lower()
        if endpoint_path == path_lower and ep["method"] != method:
            similar.append(f"{ep['method']} {ep['path']} (different method)")
        elif path_lower in endpoint_path or endpoint_path in path_lower:
            similar.append(f"{ep['method']} {ep['path']} (similar path)")
    return similar[:5]  # Limit to 5 suggestions


async def runtime_endpoint_view(app) -> Metadata:
    """The developer endpoint view, derived from the one route registry (#22274).

    ``RuntimeEndpointRegistry`` was retired: its ``register_router`` had no caller, so it was
    always empty; ``api.self_capabilities.discover_endpoints`` crawls the served app instead.
    """
    payload = await discover_endpoints(app)
    return {
        "total_endpoints": payload["total_endpoints"],
        "routers": sorted(payload["by_tag"]),
        "endpoints": {f"{ep['method']} {ep['path']}": ep for ep in payload["endpoints"]},
        "list": payload["endpoints"],
    }


@router.get("/endpoints", response_model=DeveloperEndpointsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_api_endpoints",
    error_code_prefix="DEVELOPER",
)
async def get_api_endpoints(request: Request):
    """Get all registered API endpoints (developer mode)"""
    developer_mode = config_manager.get_nested("developer.enabled", False)

    if not developer_mode:
        raise HTTPException(status_code=403, detail="Developer mode is not enabled")

    view = await runtime_endpoint_view(request.app)
    return {k: view[k] for k in ("total_endpoints", "routers", "endpoints")}


@router.get("/config", response_model=DeveloperConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_developer_config",
    error_code_prefix="DEVELOPER",
)
async def get_developer_config():
    """Get developer mode configuration"""
    developer_config = config_manager.get_nested("developer", {})
    return {
        "enabled": developer_config.get("enabled", False),
        # Back-compat: fall back to the legacy ``enhanced_errors`` key for configs written before #10792.
        "detailed_errors": developer_config.get("detailed_errors", developer_config.get("enhanced_errors", True)),
        "endpoint_suggestions": developer_config.get("endpoint_suggestions", True),
        "debug_logging": developer_config.get("debug_logging", False),
    }


@router.post("/config", response_model=DeveloperConfigUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_developer_config",
    error_code_prefix="DEVELOPER",
)
async def update_developer_config(config: dict):
    """Update developer mode configuration"""
    # Update the configuration
    current_config = merge_nested_and_save(config_manager, "developer", config)
    ConfigService.clear_cache()

    logger.info("Developer configuration updated: %s", config)
    return {"status": "success", "config": current_config}


@router.get("/system-info", response_model=DeveloperSystemInfoResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_info",
    error_code_prefix="DEVELOPER",
)
async def get_system_info(request: Request):
    """Get system information for debugging"""
    developer_mode = config_manager.get_nested("developer.enabled", False)

    if not developer_mode:
        raise HTTPException(status_code=403, detail="Developer mode is not enabled")

    return {
        "config_loaded": bool(config_manager.to_dict()),
        "backend_config": config_manager.get_backend_config(),
        "redis_config": config_manager.get_redis_config(),
        "llm_config": config_manager.get_nested("llm_config", {}),
        "available_routers": (await runtime_endpoint_view(request.app))["routers"],
    }


# Custom exception handler for 404 errors with developer mode enhancements
async def not_found_handler(request: Request, exc: HTTPException):
    """404 handler that provides helpful suggestions in developer mode"""
    developer_mode = config_manager.get_nested("developer.enabled", False)
    # Back-compat: fall back to the legacy ``enhanced_errors`` key for configs written before #10792.
    detailed_errors = config_manager.get_nested(
        "developer.detailed_errors",
        config_manager.get_nested("developer.enhanced_errors", True),
    )

    if not developer_mode or not detailed_errors:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    path = request.url.path
    method = request.method

    # Find similar endpoints
    view = await runtime_endpoint_view(request.app)
    similar_endpoints = find_similar_endpoints(view["list"], path, method)

    response_content = {
        "detail": f"Endpoint not found: {method} {path}",
        "developer_info": {
            "requested_method": method,
            "requested_path": path,
            "similar_endpoints": similar_endpoints,
            "total_available_endpoints": view["total_endpoints"],
            "available_routers": view["routers"],
        },
    }

    if not similar_endpoints:
        response_content["developer_info"]["suggestion"] = "Check available endpoints at /api/developer/endpoints"

    return JSONResponse(status_code=404, content=response_content)


# Custom exception handler for 405 errors (Method Not Allowed)
async def method_not_allowed_handler(request: Request, exc: HTTPException):
    """405 handler for developer mode"""
    developer_mode = config_manager.get_nested("developer.enabled", False)
    # Back-compat: fall back to the legacy ``enhanced_errors`` key for configs written before #10792.
    detailed_errors = config_manager.get_nested(
        "developer.detailed_errors",
        config_manager.get_nested("developer.enhanced_errors", True),
    )

    if not developer_mode or not detailed_errors:
        return JSONResponse(status_code=405, content={"detail": "Method Not Allowed"})

    path = request.url.path
    method = request.method

    # Find endpoints with same path but different methods
    allowed_methods = []
    for ep in (await runtime_endpoint_view(request.app))["list"]:
        if ep["path"] == path:
            allowed_methods.append(ep["method"])

    response_content = {
        "detail": f"Method {method} not allowed for {path}",
        "developer_info": {
            "requested_method": method,
            "requested_path": path,
            "allowed_methods": allowed_methods,
            "suggestion": (
                f"Try one of: {', '.join(allowed_methods)}" if allowed_methods else "No methods available for this path"
            ),
        },
    }

    return JSONResponse(status_code=405, content=response_content)
