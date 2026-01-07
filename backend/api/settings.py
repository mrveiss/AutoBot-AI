# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import datetime
import logging
from pathlib import Path
from typing import Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.celery_app import celery_app
from backend.services.config_service import ConfigService
from backend.tasks.deployment_tasks import (
    initialize_rbac,
    run_system_update,
    check_available_updates,
)
from src.auth_middleware import check_admin_permission
from src.utils.catalog_http_exceptions import raise_server_error
from src.utils.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()

logger = logging.getLogger(__name__)


# Issue #687: RBAC initialization request model
import re


# Issue #687: RBAC marker path constant
RBAC_MARKER_PATH = Path("/etc/autobot/rbac-initialized")


class RBACInitRequest(BaseModel):
    """Request model for RBAC initialization."""
    create_admin: bool = False
    admin_username: str = "admin"

    @classmethod
    def validate_admin_username(cls, v: str) -> str:
        """Validate admin username format."""
        if len(v) < 3 or len(v) > 32:
            raise ValueError("Username must be 3-32 characters")
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', v):
            raise ValueError(
                "Username must start with a letter and contain only letters, numbers, and underscores"
            )
        return v

    def __init__(self, **data):
        super().__init__(**data)
        if self.create_admin:
            self.admin_username = self.validate_admin_username(self.admin_username)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_settings",
    error_code_prefix="SETTINGS",
)
@router.get("/")
async def get_settings():
    """Get application settings - now uses full config from config.yaml"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting settings: %s", str(e))
        raise_server_error("API_0003", f"Error getting settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_settings_explicit",
    error_code_prefix="SETTINGS",
)
@router.get("/settings")
async def get_settings_explicit():
    """Get application settings - explicit /settings endpoint for frontend compatibility"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting settings: %s", str(e))
        raise_server_error("API_0003", f"Error getting settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_settings",
    error_code_prefix="SETTINGS",
)
@router.post("/")
async def save_settings(settings_data: dict):
    """Save application settings"""
    try:
        # Only save if there's actual data to save
        if not settings_data:
            logger.warning("Received empty settings data, skipping save")
            return {"status": "skipped", "message": "No data to save"}

        result = ConfigService.save_full_config(settings_data)
        return result
    except Exception as e:
        logger.error("Error saving settings: %s", str(e))
        raise_server_error("API_0003", f"Error saving settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_settings_explicit",
    error_code_prefix="SETTINGS",
)
@router.post("/settings")
async def save_settings_explicit(settings_data: dict):
    """Save application settings - explicit /settings endpoint for frontend compatibility"""
    try:
        # Only save if there's actual data to save
        if not settings_data:
            logger.warning("Received empty settings data, skipping save")
            return {"status": "skipped", "message": "No data to save"}

        result = ConfigService.save_full_config(settings_data)
        return result
    except Exception as e:
        logger.error("Error saving settings: %s", str(e))
        raise_server_error("API_0003", f"Error saving settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_backend_settings",
    error_code_prefix="SETTINGS",
)
@router.get("/backend")
async def get_backend_settings():
    """Get backend-specific settings"""
    try:
        return ConfigService.get_backend_settings()
    except Exception as e:
        logger.error("Error getting backend settings: %s", str(e))
        raise_server_error("API_0003", f"Error getting backend settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_backend_settings",
    error_code_prefix="SETTINGS",
)
@router.post("/backend")
async def save_backend_settings(backend_settings: dict):
    """Save backend-specific settings"""
    try:
        result = ConfigService.update_backend_settings(backend_settings)
        return result
    except Exception as e:
        logger.error("Error saving backend settings: %s", str(e))
        raise_server_error("API_0003", f"Error saving backend settings: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_full_config",
    error_code_prefix="SETTINGS",
)
@router.get("/config")
async def get_full_config():
    """Get complete application configuration"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting full config: %s", str(e))
        raise_server_error("API_0003", f"Error getting full config: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_full_config",
    error_code_prefix="SETTINGS",
)
@router.post("/config")
async def save_full_config(config_data: dict):
    """Save complete application configuration to config.yaml"""
    try:
        # Save the complete configuration to config.yaml and reload
        result = ConfigService.save_full_config(config_data)
        return result
    except Exception as e:
        logger.error("Error saving full config: %s", str(e))
        raise_server_error("API_0003", f"Error saving full config: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_cache",
    error_code_prefix="SETTINGS",
)
@router.post("/clear-cache")
async def clear_cache():
    """Clear application cache - includes config cache"""
    try:
        logger.info("Settings clear-cache endpoint called - clearing config cache")

        # Clear the ConfigService cache to force reload of settings
        ConfigService.clear_cache()

        return {
            "status": "success",
            "message": (
                "Configuration cache cleared. Settings will be reloaded on next request."
            ),
            "available_endpoints": {
                "clear_all_redis": "/api/cache/redis/clear/all",
                "clear_specific_redis": "/api/cache/redis/clear/{database_name}",
                "clear_cache_type": "/api/cache/clear/{cache_type}",
            },
        }
    except Exception as e:
        logger.error("Error in clear-cache endpoint: %s", str(e))
        raise_server_error("API_0003", f"Error in clear-cache endpoint: {str(e)}")


# ==================== RBAC Management Endpoints (Issue #687) ====================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="initialize_rbac",
    error_code_prefix="RBAC",
)
@router.post("/rbac/initialize")
async def initialize_rbac_endpoint(
    request: RBACInitRequest,
    _: None = Depends(check_admin_permission),
):
    """
    Initialize RBAC system via Ansible playbook (Issue #687).

    Triggers async Celery task to run setup-rbac.yml which creates:
    - System permissions (23 permissions across 8 resources)
    - System roles (admin, user, readonly, guest)
    - Role-permission mappings
    - Optional admin user

    Requires admin:access permission.

    Returns:
        task_id: Celery task ID for status polling
        status: 'queued' when task is submitted
    """
    try:
        logger.info(
            "RBAC initialization requested (create_admin=%s, admin_username=%s)",
            request.create_admin,
            request.admin_username,
        )

        # Queue the Celery task
        task = initialize_rbac.delay(
            create_admin=request.create_admin,
            admin_username=request.admin_username,
        )

        return {
            "task_id": task.id,
            "status": "queued",
            "message": "RBAC initialization task queued",
        }

    except Exception as e:
        logger.error("Error queuing RBAC initialization: %s", str(e))
        raise_server_error("RBAC_0001", f"Error queuing RBAC initialization: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_rbac_task_status",
    error_code_prefix="RBAC",
)
@router.get("/rbac/status/{task_id}")
async def get_rbac_task_status(
    task_id: str,
    _: None = Depends(check_admin_permission),
):
    """
    Get status of RBAC initialization task (Issue #687).

    Poll this endpoint to check progress of RBAC initialization.

    Args:
        task_id: Celery task ID from initialize endpoint

    Returns:
        status: Task state (PENDING, PROGRESS, SUCCESS, FAILURE)
        result: Task result when completed
        progress: Progress info during execution
    """
    try:
        result = AsyncResult(task_id, app=celery_app)

        response = {
            "task_id": task_id,
            "status": result.state,
        }

        if result.state == "PENDING":
            response["message"] = "Task is pending or unknown"
        elif result.state == "PROGRESS":
            response["progress"] = result.info
        elif result.state == "SUCCESS":
            response["result"] = result.result
        elif result.state == "FAILURE":
            response["error"] = str(result.result)

        return response

    except Exception as e:
        logger.error("Error getting RBAC task status: %s", str(e))
        raise_server_error("RBAC_0002", f"Error getting task status: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_rbac_status",
    error_code_prefix="RBAC",
)
@router.get("/rbac/status")
async def get_rbac_status(
    _: None = Depends(check_admin_permission),
):
    """
    Get current RBAC initialization status (Issue #687).

    Checks if RBAC has been initialized by looking for marker file.

    Returns:
        initialized: Whether RBAC setup has been run
        marker_exists: Whether marker file exists
    """
    try:
        # Check for RBAC initialization marker
        marker_exists = RBAC_MARKER_PATH.exists()

        return {
            "initialized": marker_exists,
            "message": (
                "RBAC system is initialized"
                if marker_exists
                else "RBAC system has not been initialized"
            ),
        }

    except Exception as e:
        logger.error("Error checking RBAC status: %s", str(e))
        raise_server_error("RBAC_0003", f"Error checking RBAC status: {str(e)}")


# ==================== System Updates Endpoints (Issue #544) ====================

# Issue #544: System update marker path constant
UPDATES_MARKER_PATH = Path("/etc/autobot/last-update")


class SystemUpdateRequest(BaseModel):
    """Request model for system updates (Issue #544)."""
    update_type: str = "dependencies"  # 'dependencies' or 'system'
    target_groups: Optional[list] = None  # Host groups to update (None = all)
    dry_run: bool = False  # Preview mode
    force_update: bool = False  # Skip version checks

    def __init__(self, **data):
        super().__init__(**data)
        if self.update_type not in ("dependencies", "system"):
            raise ValueError("update_type must be 'dependencies' or 'system'")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_system_update",
    error_code_prefix="UPDATES",
)
@router.post("/updates/run")
async def run_system_update_endpoint(
    request: SystemUpdateRequest,
    _: None = Depends(check_admin_permission),
):
    """
    Run system updates via Ansible playbook (Issue #544).

    Triggers async Celery task to run patch-dependencies.yml or
    patch-system-packages.yml which performs:
    - Python dependency updates (CVE fixes via pip)
    - System package updates (apt upgrade)

    Requires admin:access permission.

    Returns:
        task_id: Celery task ID for status polling
        status: 'queued' when task is submitted
    """
    try:
        logger.info(
            "System update requested (type=%s, dry_run=%s, force=%s, targets=%s)",
            request.update_type,
            request.dry_run,
            request.force_update,
            request.target_groups,
        )

        # Queue the Celery task
        task = run_system_update.delay(
            update_type=request.update_type,
            target_groups=request.target_groups,
            dry_run=request.dry_run,
            force_update=request.force_update,
        )

        return {
            "task_id": task.id,
            "status": "queued",
            "message": f"System {request.update_type} update task queued",
            "dry_run": request.dry_run,
        }

    except Exception as e:
        logger.error("Error queuing system update: %s", str(e))
        raise_server_error("UPDATES_0001", f"Error queuing system update: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_update_task_status",
    error_code_prefix="UPDATES",
)
@router.get("/updates/status/{task_id}")
async def get_update_task_status(
    task_id: str,
    _: None = Depends(check_admin_permission),
):
    """
    Get status of system update task (Issue #544).

    Poll this endpoint to check progress of system updates.

    Args:
        task_id: Celery task ID from run endpoint

    Returns:
        status: Task state (PENDING, PROGRESS, SUCCESS, FAILURE)
        result: Task result when completed
        progress: Progress info during execution
    """
    try:
        result = AsyncResult(task_id, app=celery_app)

        response = {
            "task_id": task_id,
            "status": result.state,
        }

        if result.state == "PENDING":
            response["message"] = "Task is pending or unknown"
        elif result.state == "PROGRESS":
            response["progress"] = result.info
        elif result.state == "SUCCESS":
            response["result"] = result.result
        elif result.state == "FAILURE":
            response["error"] = str(result.result)

        return response

    except Exception as e:
        logger.error("Error getting update task status: %s", str(e))
        raise_server_error("UPDATES_0002", f"Error getting task status: {str(e)}")


def _check_celery_worker_available() -> tuple[bool, str]:
    """
    Check if Celery workers are available to process tasks.

    Issue #705: Helper to detect worker availability before queuing tasks.

    Returns:
        Tuple of (is_available, error_message)
    """
    try:
        # Ping Celery workers with a short timeout
        inspector = celery_app.control.inspect(timeout=2.0)
        active_workers = inspector.active_queues()

        if not active_workers:
            return False, (
                "No Celery workers available. Please start the Celery worker with: "
                "bash scripts/start-celery-worker.sh"
            )

        # Check if deployments queue is being consumed
        deployments_handled = False
        for worker_name, queues in active_workers.items():
            for queue in queues:
                if queue.get("name") == "deployments":
                    deployments_handled = True
                    break
            if deployments_handled:
                break

        if not deployments_handled:
            return False, (
                "Celery worker running but not listening on 'deployments' queue. "
                "Restart worker with: bash scripts/start-celery-worker.sh"
            )

        return True, ""
    except Exception as e:
        logger.warning("Celery worker check failed: %s", str(e))
        return False, f"Cannot verify worker status: {str(e)}"


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_celery_health",
    error_code_prefix="UPDATES",
)
@router.get("/updates/worker-status")
async def check_celery_worker_status(
    _: None = Depends(check_admin_permission),
):
    """
    Check if Celery workers are available (Issue #705).

    Returns:
        available: Whether workers can process tasks
        message: Status message or error details
    """
    is_available, error_msg = _check_celery_worker_available()
    return {
        "available": is_available,
        "message": "Workers ready" if is_available else error_msg,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_available_updates",
    error_code_prefix="UPDATES",
)
@router.post("/updates/check")
async def check_updates_endpoint(
    _: None = Depends(check_admin_permission),
):
    """
    Check for available updates without applying them (Issue #544).

    Triggers async Celery task to run pip-audit and apt check.

    Requires admin:access permission.

    Returns:
        task_id: Celery task ID for status polling
        status: 'queued' when task is submitted
    """
    try:
        logger.info("Update check requested")

        # Issue #705: Check worker availability before queuing
        is_available, error_msg = _check_celery_worker_available()
        if not is_available:
            logger.warning("Update check rejected: %s", error_msg)
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "worker_unavailable",
                    "message": error_msg,
                    "hint": "Start the Celery worker to enable system updates",
                },
            )

        # Queue the Celery task
        task = check_available_updates.delay()

        return {
            "task_id": task.id,
            "status": "queued",
            "message": "Update check task queued",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error queuing update check: %s", str(e))
        raise_server_error("UPDATES_0003", f"Error queuing update check: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_update_status",
    error_code_prefix="UPDATES",
)
@router.get("/updates/status")
async def get_update_status(
    _: None = Depends(check_admin_permission),
):
    """
    Get current system update status (Issue #544).

    Returns information about last update run.

    Returns:
        last_update: Timestamp of last update (if available)
        marker_exists: Whether marker file exists
    """
    try:
        marker_exists = UPDATES_MARKER_PATH.exists()
        last_update = None

        if marker_exists:
            stat = UPDATES_MARKER_PATH.stat()
            last_update = datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()

        return {
            "last_update": last_update,
            "marker_exists": marker_exists,
            "message": (
                f"Last update: {last_update}"
                if marker_exists
                else "No update history found"
            ),
        }

    except Exception as e:
        logger.error("Error checking update status: %s", str(e))
        raise_server_error("UPDATES_0004", f"Error checking update status: {str(e)}")
