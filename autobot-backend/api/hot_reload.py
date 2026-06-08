# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hot Reload API Endpoints
Provides REST endpoints for hot reloading chat workflow modules during development
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas_common import DataResponse
from api.schemas_system import HotReloadStatusData, ReloadRequest, ReloadResponse
from api.system_health import ComponentHealth, register_health_probe
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from type_defs.common import Metadata

logger = get_logger(__name__)

# Initialize router
router = APIRouter(
    tags=["hot-reload", "development"],
    dependencies=[Depends(check_admin_permission)],
)


@router.post("/chat-workflow", response_model=ReloadResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reload_chat_workflow",
    error_code_prefix="HOT_RELOAD",
)
async def reload_chat_workflow():
    """
    Reload all chat workflow modules without restarting the backend
    """
    try:
        # Import hot reload manager (lazy import to avoid circular dependencies)
        from utils.hot_reload_manager import hot_reload_manager

        logger.info("Hot reload request: chat workflow modules")

        # Perform the reload
        reload_results = await hot_reload_manager.reload_chat_workflow()

        # Process results
        successful_reloads = [module for module, success in reload_results.items() if success]
        failed_reloads = [module for module, success in reload_results.items() if not success]

        overall_success = len(successful_reloads) > 0

        message = f"Reloaded {len(successful_reloads)} chat workflow modules"
        if failed_reloads:
            message += f", {len(failed_reloads)} failed"

        return ReloadResponse(
            success=overall_success,
            message=message,
            results=reload_results,
            reloaded_modules=successful_reloads,
            errors=failed_reloads,
        )

    except Exception as e:
        logger.error("Chat workflow reload failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to reload chat workflow")


@router.post("/module", response_model=ReloadResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reload_module",
    error_code_prefix="HOT_RELOAD",
)
async def reload_module(request: ReloadRequest):
    """
    Reload a specific module
    """
    try:
        if not request.module_name:
            raise HTTPException(status_code=400, detail="module_name is required")

        # Import hot reload manager
        from utils.hot_reload_manager import hot_reload_manager

        logger.info("Hot reload request: %s", request.module_name)

        # Check if module is registered
        if not hot_reload_manager.is_watching(request.module_name):
            # Try to register it first
            hot_reload_manager.register_module(request.module_name)

        # Perform the reload
        success = await hot_reload_manager.reload_module(request.module_name)

        if success:
            return ReloadResponse(
                success=True,
                message=f"Successfully reloaded {request.module_name}",
                reloaded_modules=[request.module_name],
            )
        else:
            return ReloadResponse(
                success=False,
                message=f"Failed to reload {request.module_name}",
                errors=[request.module_name],
            )

    except Exception as e:
        logger.error("Module reload failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to reload module")


@router.get("/status", response_model=Metadata)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_reload_status",
    error_code_prefix="HOT_RELOAD",
)
async def get_reload_status():
    """
    Get hot reload manager status
    """
    try:
        from utils.hot_reload_manager import hot_reload_manager

        status = await hot_reload_manager.get_status()
        return status

    except Exception as e:
        logger.error("Failed to get reload status: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get status")


@router.post("/start", response_model=DataResponse[HotReloadStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_hot_reload",
    error_code_prefix="HOT_RELOAD",
)
async def start_hot_reload():
    """
    Start the hot reload manager
    """
    try:
        from utils.hot_reload_manager import hot_reload_manager

        await hot_reload_manager.start()

        # Register chat workflow modules
        hot_reload_manager.register_chat_workflow_modules()

        return {
            "success": True,
            "message": ("Hot reload manager started and chat workflow modules registered"),
        }

    except Exception as e:
        logger.error("Failed to start hot reload: %s", e)
        raise HTTPException(status_code=500, detail="Failed to start hot reload")


@router.post("/stop", response_model=DataResponse[HotReloadStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_hot_reload",
    error_code_prefix="HOT_RELOAD",
)
async def stop_hot_reload():
    """
    Stop the hot reload manager
    """
    try:
        from utils.hot_reload_manager import hot_reload_manager

        await hot_reload_manager.stop()

        return {"success": True, "message": "Hot reload manager stopped"}

    except Exception as e:
        logger.error("Failed to stop hot reload: %s", e)
        raise HTTPException(status_code=500, detail="Failed to stop hot reload")


@register_health_probe("hot_reload")
async def probe_hot_reload(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for hot-reload file watcher."""
    try:
        from utils.hot_reload_manager import hot_reload_manager

        status = await hot_reload_manager.get_status()
        if status.get("running"):
            return ComponentHealth(name="hot_reload", status="ok")
        return ComponentHealth(
            name="hot_reload",
            status="degraded",
            detail="watcher not running",
        )
    except Exception as exc:
        return ComponentHealth(
            name="hot_reload",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )
