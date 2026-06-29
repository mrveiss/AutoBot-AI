# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Application settings read/write endpoints.

Manages the mutable runtime configuration store, supporting live reload
of settings without restarting the backend process.
"""

import asyncio
import copy
import datetime
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import aiofiles
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_system import (
    ClearCacheResponse,
    ConfigSyncRequest,
    ConfigSyncResponse,
    HardwarePriorityRequest,
    HardwarePriorityResponse,
    RBACInitRequest,
    RBACStatusResponse,
    SettingsTaskQueuedResponse,
    SettingsTaskStatusResponse,
    SystemUpdateRequest,
    TelemetrySettingsRequest,
    TelemetrySettingsResponse,
    UpdateStatusResponse,
    WorkerStatusResponse,
)
from api.user_management.dependencies import get_db_session, get_optional_db_session
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from celery_app import celery_app
from services.config_revision_service import ConfigRevisionService
from services.config_service import ConfigService
from tasks.system_tasks import (
    check_available_updates,
    initialize_rbac,
    run_system_update,
)
from utils.catalog_http_exceptions import raise_server_error

router = APIRouter()

logger = get_logger(__name__)


# Issue #687: RBAC marker path constant
RBAC_MARKER_PATH = Path("/etc/autobot/rbac-initialized")


@router.get("/", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_settings",
    error_code_prefix="SETTINGS",
)
async def get_settings():
    """Get application settings - now uses full config from config.yaml"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting settings: %s", str(e))
        raise_server_error("API_0003", "Error getting settings")


@router.get("/settings", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_settings_explicit",
    error_code_prefix="SETTINGS",
)
async def get_settings_explicit():
    """Get application settings.

    Issue #3334: Deprecated duplicate — use GET /api/settings/ instead.
    This endpoint remains for backward compatibility but will be removed in a
    future release.
    """
    logger.warning("Deprecated endpoint called: GET /api/settings/settings. " "Use GET /api/settings/ instead. (#3334)")
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting settings: %s", str(e))
        raise_server_error("API_0003", "Error getting settings")


@router.post("/", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_settings",
    error_code_prefix="SETTINGS",
)
async def save_settings(
    settings_data: dict,
    session: AsyncSession = Depends(get_db_session),
):
    """Save application settings (#1747: records audit revision)."""
    try:
        if not settings_data:
            logger.warning("Received empty settings data, skipping save")
            return {"status": "skipped", "message": "No data to save"}

        before_config = ConfigService.get_full_config()
        result = ConfigService.save_full_config(settings_data)

        # Issue #1747: Record config revision
        await ConfigRevisionService(session).create_revision(
            entity_type="system",
            entity_id="settings",
            before_config=before_config,
            after_config=settings_data,
            source="api",
            created_by="admin",
        )
        return result
    except Exception as e:
        logger.error("Error saving settings: %s", str(e))
        raise_server_error("API_0003", "Error saving settings")


@router.post("/settings", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_settings_explicit",
    error_code_prefix="SETTINGS",
)
async def save_settings_explicit(
    settings_data: dict,
    session: AsyncSession = Depends(get_db_session),
):
    """Save application settings.

    Issue #3334: Deprecated duplicate — use POST /api/settings/ instead.
    This endpoint remains for backward compatibility but will be removed in a
    future release.
    """
    logger.warning(
        "Deprecated endpoint called: POST /api/settings/settings. " "Use POST /api/settings/ instead. (#3334)"
    )
    try:
        if not settings_data:
            logger.warning("Received empty settings data, skipping save")
            return {"status": "skipped", "message": "No data to save"}

        before_config = ConfigService.get_full_config()
        result = ConfigService.save_full_config(settings_data)

        await ConfigRevisionService(session).create_revision(
            entity_type="system",
            entity_id="settings",
            before_config=before_config,
            after_config=settings_data,
            source="api",
            created_by="admin",
        )
        return result
    except Exception as e:
        logger.error("Error saving settings: %s", str(e))
        raise_server_error("API_0003", "Error saving settings")


@router.get("/backend", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_backend_settings",
    error_code_prefix="SETTINGS",
)
async def get_backend_settings():
    """Get backend-specific settings"""
    try:
        return ConfigService.get_backend_settings()
    except Exception as e:
        logger.error("Error getting backend settings: %s", str(e))
        raise_server_error("API_0003", "Error getting backend settings")


@router.post("/backend", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_backend_settings",
    error_code_prefix="SETTINGS",
)
async def save_backend_settings(
    backend_settings: dict,
    session: AsyncSession = Depends(get_db_session),
):
    """Save backend-specific settings (#1747: audit trail)."""
    try:
        before_config = ConfigService.get_backend_settings()
        result = ConfigService.update_backend_settings(backend_settings)

        await ConfigRevisionService(session).create_revision(
            entity_type="system",
            entity_id="backend",
            before_config=before_config,
            after_config=backend_settings,
            source="api",
            created_by="admin",
        )
        return result
    except Exception as e:
        logger.error("Error saving backend settings: %s", str(e))
        raise_server_error("API_0003", "Error saving backend settings")


@router.get("/config", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_full_config",
    error_code_prefix="SETTINGS",
)
async def get_full_config():
    """Get complete application configuration"""
    try:
        return ConfigService.get_full_config()
    except Exception as e:
        logger.error("Error getting full config: %s", str(e))
        raise_server_error("API_0003", "Error getting full config")


@router.post("/config", response_model=dict)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="save_full_config",
    error_code_prefix="SETTINGS",
)
async def save_full_config(
    config_data: dict,
    session: AsyncSession = Depends(get_db_session),
):
    """Save complete application configuration (#1747: audit trail)."""
    try:
        before_config = ConfigService.get_full_config()
        result = ConfigService.save_full_config(config_data)

        await ConfigRevisionService(session).create_revision(
            entity_type="system",
            entity_id="config",
            before_config=before_config,
            after_config=config_data,
            source="api",
            created_by="admin",
        )
        return result
    except Exception as e:
        logger.error("Error saving full config: %s", str(e))
        raise_server_error("API_0003", "Error saving full config")


@router.post("/clear-cache", response_model=ClearCacheResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_cache",
    error_code_prefix="SETTINGS",
)
async def clear_cache():
    """Clear application cache - includes config cache"""
    try:
        logger.info("Settings clear-cache endpoint called - clearing config cache")

        # Clear the ConfigService cache to force reload of settings
        ConfigService.clear_cache()

        return {
            "status": "success",
            "message": ("Configuration cache cleared. Settings will be reloaded on next request."),
            "available_endpoints": {
                "clear_all_redis": "/api/cache/redis/clear/all",
                "clear_specific_redis": "/api/cache/redis/clear/{database_name}",
                "clear_cache_type": "/api/cache/clear/{cache_type}",
            },
        }
    except Exception as e:
        logger.error("Error in clear-cache endpoint: %s", str(e))
        raise_server_error("API_0003", "Error clearing cache")


# ==================== RBAC Management Endpoints (Issue #687) ====================


@router.post("/rbac/initialize", response_model=SettingsTaskQueuedResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="initialize_rbac_endpoint",
    error_code_prefix="SETTINGS",
)
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
        raise_server_error("RBAC_0001", "Error queuing RBAC initialization")


@router.get("/rbac/status/{task_id}", response_model=SettingsTaskStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_rbac_task_status",
    error_code_prefix="SETTINGS",
)
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
        raise_server_error("RBAC_0002", "Error getting task status")


@router.get("/rbac/status", response_model=RBACStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_rbac_status",
    error_code_prefix="SETTINGS",
)
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
            "message": ("RBAC system is initialized" if marker_exists else "RBAC system has not been initialized"),
        }

    except Exception as e:
        logger.error("Error checking RBAC status: %s", str(e))
        raise_server_error("RBAC_0003", "Error checking RBAC status")


# ==================== System Updates Endpoints (Issue #544) ====================

# Issue #544: System update marker path constant
UPDATES_MARKER_PATH = Path("/etc/autobot/last-update")


@router.post("/updates/run", response_model=SettingsTaskQueuedResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_system_update_endpoint",
    error_code_prefix="SETTINGS",
)
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

        # Issue #705: Check worker availability before queuing
        is_available, error_msg = _check_celery_worker_available()
        if not is_available:
            logger.warning("System update rejected: %s", error_msg)
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "worker_unavailable",
                    "message": error_msg,
                    "hint": "Start the Celery worker to enable system updates",
                },
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error queuing system update: %s", str(e))
        raise_server_error("UPDATES_0001", "Error queuing system update")


@router.get("/updates/status/{task_id}", response_model=SettingsTaskStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_update_task_status",
    error_code_prefix="SETTINGS",
)
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
        raise_server_error("UPDATES_0002", "Error getting task status")


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
    except Exception:
        logger.warning("Celery worker check failed: %s", "Internal server error")
        return False, "Cannot verify worker status"


@router.get("/updates/worker-status", response_model=WorkerStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_celery_worker_status",
    error_code_prefix="SETTINGS",
)
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


@router.post("/updates/check", response_model=SettingsTaskQueuedResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_updates_endpoint",
    error_code_prefix="SETTINGS",
)
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
        raise_server_error("UPDATES_0003", "Error queuing update check")


@router.get("/updates/status", response_model=UpdateStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_update_status",
    error_code_prefix="SETTINGS",
)
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
            "message": (f"Last update: {last_update}" if marker_exists else "No update history found"),
        }

    except Exception as e:
        logger.error("Error checking update status: %s", str(e))
        raise_server_error("UPDATES_0004", "Error checking update status")


# ==================== Config Sync Endpoint (Issue #3398, #3881) ====================

# Allowlist of permitted top-level keys for /api/settings/sync.
# Any key not present here is rejected with HTTP 400 to prevent arbitrary
# key injection into the config store (Issue #3881).
_SYNC_ALLOWED_TOP_LEVEL_KEYS: frozenset = frozenset(
    {
        "backend",
        "celery",
        "chat",
        "data",
        "deployment",
        "hardware",
        "logging",
        "memory",
        "multimodal",
        "network",
        "npu",
        "optimization",
        "redis",
        "security",
        "system",
        "task_transport",
        "ui",
    }
)

# Maximum nesting depth accepted in the incoming settings payload (Issue #3881).
_SYNC_MAX_DEPTH: int = 8

# Maximum raw byte size of the incoming settings payload (Issue #3881).
_SYNC_MAX_PAYLOAD_BYTES: int = 256 * 1024  # 256 KiB


def _exceeds_depth(obj: Any, current_depth: int = 0) -> bool:
    """Return True when *obj* exceeds ``_SYNC_MAX_DEPTH`` nesting levels.

    Only recurses into dict values; non-dict values always return False.
    """
    if current_depth > _SYNC_MAX_DEPTH:
        return True
    if isinstance(obj, dict):
        return any(_exceeds_depth(v, current_depth + 1) for v in obj.values())
    return False


def _compute_flat_diff(before: dict, after: dict, prefix: str = "") -> dict:
    """Return a flat dict of keys whose values changed between *before* and *after*.

    Only leaf values are compared; nested dicts are recursed into.
    """
    diff: dict = {}
    all_keys = set(before) | set(after)
    for key in all_keys:
        full_key = f"{prefix}.{key}" if prefix else key
        bval = before.get(key)
        aval = after.get(key)
        if isinstance(bval, dict) and isinstance(aval, dict):
            diff.update(_compute_flat_diff(bval, aval, prefix=full_key))
        elif bval != aval:
            diff[full_key] = {"before": bval, "after": aval}
    return diff


async def _atomic_write_json(target: Path, data: dict) -> None:
    """Write *data* as JSON to *target* atomically via a temp-file rename.

    Creates parent directories as needed.  Cleans up the temp file if the
    write or rename fails so no partial file is left on disk.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp", prefix=target.stem + "_")
    os.close(tmp_fd)  # aiofiles will reopen by path
    try:
        async with aiofiles.open(tmp_path, "w", encoding="utf-8") as fh:
            await fh.write(json.dumps(data, indent=2, ensure_ascii=False))
        # Issue #3882: os.replace is a blocking syscall — offload to thread pool
        # so we do not stall the event loop under high concurrency.
        await asyncio.to_thread(os.replace, tmp_path, str(target))
    except Exception:
        try:
            # Issue #3882: os.unlink is also blocking — offload to thread pool.
            await asyncio.to_thread(os.unlink, tmp_path)
        except OSError:
            pass
        raise


def _count_unchanged_keys(incoming: dict, changed: dict) -> int:
    """Return how many leaf keys in *incoming* were not present in *changed*."""
    all_incoming_leaf_count = len(_compute_flat_diff({}, incoming))
    return max(0, all_incoming_leaf_count - len(changed))


@router.post("/sync", response_model=ConfigSyncResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="sync_config",
    error_code_prefix="SETTINGS",
)
async def sync_config(
    request: ConfigSyncRequest,
    session: AsyncSession = Depends(get_db_session),
    _: None = Depends(check_admin_permission),
):
    """Atomically merge *request.settings* into settings.json (Issue #3398).

    The write is atomic: the new JSON is written to a temp file then renamed
    over the target, preventing a half-written file from corrupting config.
    Requires operator/admin permission.  Returns a diff of what changed so the
    caller can display a confirmation to the user.
    """
    import copy

    from config.loader import deep_merge
    from constants.path_constants import PATH

    if not request.settings:
        return ConfigSyncResponse(status="skipped", changed={}, unchanged_keys=0)

    # Issue #3881: Enforce max payload size before any further processing.
    try:
        raw_size = len(json.dumps(request.settings).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="settings payload is not JSON-serialisable",
        ) from exc
    if raw_size > _SYNC_MAX_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(f"settings payload is too large ({raw_size} bytes); " f"limit is {_SYNC_MAX_PAYLOAD_BYTES} bytes"),
        )

    # Issue #3881: Reject unknown top-level keys to block arbitrary key injection.
    unknown_keys = set(request.settings) - _SYNC_ALLOWED_TOP_LEVEL_KEYS
    if unknown_keys:
        raise HTTPException(
            status_code=400,
            detail=f"unknown top-level config key(s): {sorted(unknown_keys)}",
        )

    # Issue #3881: Reject payloads that exceed the maximum permitted nesting depth.
    if _exceeds_depth(request.settings):
        raise HTTPException(
            status_code=400,
            detail=(f"settings payload exceeds maximum nesting depth of {_SYNC_MAX_DEPTH}"),
        )

    before_config: dict = ConfigService.get_full_config()
    merged_config = deep_merge(copy.deepcopy(before_config), request.settings)

    settings_file = PATH.PROJECT_ROOT / "config" / "settings.json"
    await _atomic_write_json(settings_file, merged_config)

    # Invalidate the ConfigService cache so the next read picks up the new file.
    ConfigService.clear_cache()

    changed = _compute_flat_diff(before_config, merged_config)
    unchanged_keys = _count_unchanged_keys(request.settings, changed)

    # Audit trail (same pattern as existing save_settings endpoint).
    await ConfigRevisionService(session).create_revision(
        entity_type="system",
        entity_id="settings",
        before_config=before_config,
        after_config=merged_config,
        source="api_sync",
        created_by="admin",
    )

    logger.info(
        "Config sync: %d key(s) changed, %d unchanged",
        len(changed),
        unchanged_keys,
    )

    return ConfigSyncResponse(
        status="ok",
        changed=changed,
        unchanged_keys=unchanged_keys,
    )


# ==================== Hardware Priority Endpoint (Issue #3288) ====================


@router.patch("/hardware-priority", response_model=HardwarePriorityResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_hardware_priority",
    error_code_prefix="SETTINGS",
)
async def update_hardware_priority(
    request: HardwarePriorityRequest,
    session: AsyncSession = Depends(get_db_session),
    _: None = Depends(check_admin_permission),
):
    """Set hardware processing priority order for NPU/GPU/CPU (Issue #3288).

    Persists the ordering to ``hardware.acceleration.priority_order`` in
    ``config.yaml`` and immediately applies it to the in-process
    ``HardwareAccelerationManager`` singleton so new agent dispatches respect
    the updated priority without a restart.

    Requires admin permission.
    """
    from hardware_acceleration import get_hardware_acceleration_manager

    before_config: dict = ConfigService.get_full_config()

    # Build the minimal patch — only the key we own
    patch: dict = {
        "hardware": {
            "acceleration": {
                "priority_order": request.priority_order,
            }
        }
    }

    # Deep-merge into a copy to produce the full updated config
    from config.loader import deep_merge

    merged_config = deep_merge(copy.deepcopy(before_config), patch)
    ConfigService.save_full_config(merged_config)
    ConfigService.clear_cache()

    # Apply in-memory so the running process respects the new ordering
    hw_manager = get_hardware_acceleration_manager()
    hw_manager.update_priorities(request.priority_order)

    # Read back the actually-applied order (filtered to available devices)
    applied_order = [t.value for t in hw_manager.current_config["priority_order"]]

    changed = _compute_flat_diff(before_config, merged_config)

    await ConfigRevisionService(session).create_revision(
        entity_type="system",
        entity_id="hardware_priority",
        before_config=before_config,
        after_config=merged_config,
        source="api",
        created_by="admin",
    )

    logger.info(
        "Hardware priority updated: %s (changed keys: %d)",
        request.priority_order,
        len(changed),
    )

    return HardwarePriorityResponse(
        status="ok",
        priority_order=applied_order,
        changed=changed,
    )


# ==================== Telemetry Settings Endpoints (Issue #9035) ====================


@router.get("/telemetry", response_model=TelemetrySettingsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_telemetry_settings",
    error_code_prefix="SETTINGS",
)
async def get_telemetry_settings(
    current_user: dict = Depends(get_current_user),
):
    """Get current telemetry settings (Issue #9035).

    Returns telemetry opt-in/opt-out status and whether the first-run
    prompt has been shown.

    Requires authentication.
    """
    from autobot_shared.ssot_config import config

    return TelemetrySettingsResponse(
        enabled=config.telemetry.enabled,
        anonymous_usage_stats=config.telemetry.anonymous_usage_stats,
        first_run_prompt_shown=config.telemetry.first_run_prompt_shown,
    )


@router.post("/telemetry", response_model=TelemetrySettingsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_telemetry_settings",
    error_code_prefix="SETTINGS",
)
async def update_telemetry_settings(
    request: TelemetrySettingsRequest,
    session: Optional[AsyncSession] = Depends(get_optional_db_session),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(check_admin_permission),
):
    """Update telemetry settings (Issue #9035).

    Allows users to opt in/out of telemetry collection. When telemetry
    is disabled, the AnalyticsMiddleware and VoiceRealtimeTelemetry
    services skip data collection.

    Requires admin permission.  The consent state is persisted to
    settings.json via ConfigService; a DB audit-trail revision is also
    recorded (Issue #10000).

    Args:
        request: New telemetry settings

    Returns:
        Updated telemetry settings
    """
    before_config: dict = ConfigService.get_full_config()

    # Build the minimal patch
    patch: dict = {
        "telemetry": {
            "enabled": request.enabled,
            "anonymous_usage_stats": request.anonymous_usage_stats,
            "first_run_prompt_shown": request.first_run_prompt_shown,
        }
    }

    # Deep-merge into a copy
    from config.loader import deep_merge

    merged_config = deep_merge(copy.deepcopy(before_config), patch)
    ConfigService.save_full_config(merged_config)
    ConfigService.clear_cache()

    changed = _compute_flat_diff(before_config, merged_config)

    # Record a DB audit-trail revision (Issue #10000). Defensive None-guard
    # retained in case an override yields no session.
    if session is not None:
        await ConfigRevisionService(session).create_revision(
            entity_type="system",
            entity_id="telemetry_settings",
            before_config=before_config,
            after_config=merged_config,
            source="api",
            created_by=current_user.get("id", "unknown"),
        )
    else:
        logger.debug("Telemetry audit trail skipped: Postgres unavailable in current deployment mode")

    logger.info(
        "Telemetry settings updated: enabled=%s, anonymous_usage_stats=%s (changed keys: %d)",
        request.enabled,
        request.anonymous_usage_stats,
        len(changed),
    )

    return TelemetrySettingsResponse(
        enabled=request.enabled,
        anonymous_usage_stats=request.anonymous_usage_stats,
        first_run_prompt_shown=request.first_run_prompt_shown,
    )
