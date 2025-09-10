"""
Hot Reload API Endpoints
Provides REST endpoints for hot reloading chat workflow modules during development
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(tags=["hot-reload", "development"])


class ReloadRequest(BaseModel):
    """Request model for module reload"""
    module_name: str = None
    force: bool = False


class ReloadResponse(BaseModel):
    """Response model for reload operations"""
    success: bool
    message: str
    results: Dict[str, Any] = {}
    reloaded_modules: list = []
    errors: list = []


@router.post("/chat-workflow", response_model=ReloadResponse)
async def reload_chat_workflow():
    """
    Reload all chat workflow modules without restarting the backend
    """
    try:
        # Import hot reload manager (lazy import to avoid circular dependencies)
        from src.utils.hot_reload_manager import hot_reload_manager
        
        logger.info("Hot reload request: chat workflow modules")
        
        # Perform the reload
        reload_results = await hot_reload_manager.reload_chat_workflow()
        
        # Process results
        successful_reloads = [
            module for module, success in reload_results.items() if success
        ]
        failed_reloads = [
            module for module, success in reload_results.items() if not success
        ]
        
        overall_success = len(successful_reloads) > 0
        
        message = f"Reloaded {len(successful_reloads)} chat workflow modules"
        if failed_reloads:
            message += f", {len(failed_reloads)} failed"
        
        return ReloadResponse(
            success=overall_success,
            message=message,
            results=reload_results,
            reloaded_modules=successful_reloads,
            errors=failed_reloads
        )
        
    except Exception as e:
        logger.error(f"Chat workflow reload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload chat workflow: {str(e)}"
        )


@router.post("/module", response_model=ReloadResponse)
async def reload_module(request: ReloadRequest):
    """
    Reload a specific module
    """
    try:
        if not request.module_name:
            raise HTTPException(
                status_code=400,
                detail="module_name is required"
            )
        
        # Import hot reload manager
        from src.utils.hot_reload_manager import hot_reload_manager
        
        logger.info(f"Hot reload request: {request.module_name}")
        
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
                reloaded_modules=[request.module_name]
            )
        else:
            return ReloadResponse(
                success=False,
                message=f"Failed to reload {request.module_name}",
                errors=[request.module_name]
            )
        
    except Exception as e:
        logger.error(f"Module reload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload module: {str(e)}"
        )


@router.get("/status", response_model=Dict[str, Any])
async def get_reload_status():
    """
    Get hot reload manager status
    """
    try:
        from src.utils.hot_reload_manager import hot_reload_manager
        
        status = await hot_reload_manager.get_status()
        return status
        
    except Exception as e:
        logger.error(f"Failed to get reload status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
        )


@router.post("/start")
async def start_hot_reload():
    """
    Start the hot reload manager
    """
    try:
        from src.utils.hot_reload_manager import hot_reload_manager
        
        await hot_reload_manager.start()
        
        # Register chat workflow modules
        hot_reload_manager.register_chat_workflow_modules()
        
        return {
            "success": True,
            "message": "Hot reload manager started and chat workflow modules registered"
        }
        
    except Exception as e:
        logger.error(f"Failed to start hot reload: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start hot reload: {str(e)}"
        )


@router.post("/stop")
async def stop_hot_reload():
    """
    Stop the hot reload manager
    """
    try:
        from src.utils.hot_reload_manager import hot_reload_manager
        
        await hot_reload_manager.stop()
        
        return {
            "success": True,
            "message": "Hot reload manager stopped"
        }
        
    except Exception as e:
        logger.error(f"Failed to stop hot reload: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop hot reload: {str(e)}"
        )


@router.get("/health")
async def hot_reload_health():
    """
    Health check for hot reload functionality
    """
    try:
        from src.utils.hot_reload_manager import hot_reload_manager
        
        status = await hot_reload_manager.get_status()
        
        health_status = "healthy" if status["running"] else "stopped"
        
        return {
            "status": health_status,
            "running": status["running"],
            "watched_modules": len(status["watched_modules"]),
            "watched_paths": len(status["watched_paths"]),
            "service": "hot_reload"
        }
        
    except Exception as e:
        logger.error(f"Hot reload health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "service": "hot_reload"
        }