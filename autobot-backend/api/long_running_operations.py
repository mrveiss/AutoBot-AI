# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Long-Running Operations API for AutoBot Backend
==============================================

This module provides FastAPI endpoints for managing long-running operations
with proper timeout handling, progress tracking, and checkpoint/resume capabilities.

Integrated with the existing AutoBot backend architecture.

Boundary with ProcessAdapterService (#1751):
    This module manages in-process Python async tasks (codebase indexing,
    test suites, code analysis) with checkpoint/resume and WebSocket progress.

    For OS-level subprocess management (CLI tools, shell commands), see
    services/process_adapter_service.py and api/process_management.py.
"""

import asyncio
import logging
import sys
from typing import Dict, NoReturn

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)

from api.schemas_workflows import (
    CodebaseIndexingRequest,
    KnowledgeBaseRequest,
    LongRunningOperationCancelResponse,
    LongRunningOperationListResponse,
    LongRunningOperationMigrateResponse,
    LongRunningOperationResumeResponse,
    LongRunningOperationStatusResponse,
    SecurityScanRequest,
    TestSuiteRequest,
)
from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from api.ws_security import open_authenticated_ws
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import PROJECT_ALLOWED_ROOTS, validate_path
from constants.path_constants import PATH
from constants.threshold_constants import TimingConstants
from utils.long_running_operations.views import operation_view

# Add AutoBot paths
sys.path.append(str(PATH.PROJECT_ROOT))

# Import our long-running operations framework
from autobot_shared.missing_dep import optional_import

_lro = optional_import("utils.long_running_operations_framework", ["OperationStatus", "OperationType"])
_lro_int = optional_import(
    "utils.operation_timeout_integration",
    ["CreateOperationRequest", "OperationMigrator", "operation_integration_manager"],
)
OperationStatus = _lro["OperationStatus"]  # type: ignore[assignment]
OperationType = _lro["OperationType"]  # type: ignore[assignment]
CreateOperationRequest = _lro_int["CreateOperationRequest"]  # type: ignore[assignment]
OperationMigrator = _lro_int["OperationMigrator"]  # type: ignore[assignment]
operation_integration_manager = _lro_int["operation_integration_manager"]  # type: ignore[assignment]
_OPERATIONS_AVAILABLE = bool(OperationStatus)
if not _OPERATIONS_AVAILABLE:
    logging.warning("Long-running operations framework not available: %s", OperationStatus)

logger = get_logger(__name__)
router = APIRouter(tags=["long-running-operations"])
_ADMIN = [Depends(check_admin_permission)]  # #17010: starting work is an admin's

# Performance optimization: O(1) lookup for failed operation statuses (Issue #326)
if _OPERATIONS_AVAILABLE:
    FAILED_OPERATION_STATUSES = {OperationStatus.FAILED, OperationStatus.TIMEOUT}
else:
    FAILED_OPERATION_STATUSES = set()


async def get_operation_manager():
    """Dependency to get the operation integration manager"""
    if not _OPERATIONS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Long-running operations service not available")
    return operation_integration_manager


def _not_implemented(what: str) -> NoReturn:
    """501 for a start route with no working operation behind it; nothing is queued (#17017, #17023)."""
    raise HTTPException(status_code=501, detail=f"{what} is not implemented as a long-running operation yet (#17023)")


def _may_see(operation, user: dict) -> bool:
    """Creator or admin (#17017). An operation with no recorded creator is an admin's alone."""
    if is_admin_role(user.get("role")):
        return True
    creator = (getattr(operation, "metadata", None) or {}).get("created_by")
    return bool(creator) and creator == user.get("username")


async def _owned_operation(manager, operation_id: str, user: dict):
    """The operation, or 404 if it does not exist or is another user's: existence is not disclosed.

    ``get_operation`` is a coroutine; every caller here used to skip the ``await`` and
    got a coroutine object back, which is why status never worked (#17017).
    """
    operation = await manager.operation_manager.get_operation(operation_id)
    if operation is None or not _may_see(operation, user):
        raise HTTPException(status_code=404, detail="Operation not found")
    return operation


async def _may_see_id(operation_id: str, user: dict) -> bool:
    """The progress socket's ``allow`` check: the operation's creator or an admin."""
    manager = operation_integration_manager if _OPERATIONS_AVAILABLE else None
    operation = (
        await manager.operation_manager.get_operation(operation_id) if manager and manager.operation_manager else None
    )
    return is_admin_role(user.get("role")) or (operation is not None and _may_see(operation, user))


# Enhanced API endpoints with AutoBot-specific operations
@router.post("/codebase/index", response_model=Dict[str, str], dependencies=_ADMIN)
async def start_codebase_indexing(request: CodebaseIndexingRequest):
    """Not implemented: its operation called a method that exists nowhere (#17017). Wiring it to the
    codebase-analytics indexer, not a second copy of it, is #17023."""
    _not_implemented("Codebase indexing")


@router.post("/testing/comprehensive", response_model=Dict[str, str], dependencies=_ADMIN)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_comprehensive_testing",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def start_comprehensive_testing(
    request: TestSuiteRequest,
    background_tasks: BackgroundTasks,
    manager=Depends(get_operation_manager),
    current_user: dict = Depends(get_current_user),
):
    """
    Start comprehensive test suite operation

    This operation will:
    - Run all matching test files with proper isolation
    - Collect detailed test results and performance metrics
    - Support parallel execution with resource management
    - Provide real-time progress updates
    """
    try:
        context = {
            "test_path": request.test_path,
            "test_patterns": request.test_patterns,
            "test_types": request.test_types,
            "parallel_execution": request.parallel_execution,
            "timeout_per_test": request.timeout_per_test,
            "operation_type": "comprehensive_test_suite",
        }

        # Estimate test count (#15238: explicit project root, not the shared /tmp default)
        try:
            safe_test_path = validate_path(request.test_path, must_exist=True, allowed_roots=PROJECT_ALLOWED_ROOTS)
        except (ValueError, PermissionError):
            raise HTTPException(status_code=400, detail="Invalid or inaccessible test path")

        estimated_tests = 0
        try:
            for pattern in request.test_patterns:
                # Issue #358 - avoid blocking rglob() in async context
                pattern_files = await asyncio.to_thread(lambda p=pattern: list(safe_test_path.rglob(p)))
                estimated_tests += len(pattern_files)
        except Exception:
            estimated_tests = 50  # Default estimate

        create_request = CreateOperationRequest(
            operation_type="comprehensive_test_suite",
            name=f"Comprehensive test suite: {safe_test_path.name}",
            description=(f"Run all tests in {safe_test_path} with patterns" f"{request.test_patterns}"),
            priority=request.priority,
            estimated_items=estimated_tests,
            context=context,
            execute_immediately=False,
            created_by=current_user.get("username"),  # #17017: its creator sees and controls it
        )

        result = await manager._handle_create_operation(create_request)  # #17017: not routes[0] of an unmounted router

        logger.info(f"Started comprehensive testing operation: {result['operation_id']}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start comprehensive testing: %s", e)
        raise HTTPException(status_code=500, detail="Failed to start operation")


@router.post("/knowledge-base/populate", response_model=Dict[str, str], dependencies=_ADMIN)
async def start_knowledge_base_population(request: KnowledgeBaseRequest):
    """Not implemented: its operation was a placeholder that reported success (#17017). Wiring it to
    ``api/knowledge_population.py`` is #17023."""
    _not_implemented("Knowledge base population")


@router.post("/security/scan", response_model=Dict[str, str], dependencies=_ADMIN)
async def start_security_scan(request: SecurityScanRequest):
    """Not implemented: no operation handles a security scan (#17017); whether one is wanted is #17023."""
    _not_implemented("Security scan")


# Legacy operation migration endpoints
@router.post("/migrate/existing", response_model=LongRunningOperationMigrateResponse, dependencies=_ADMIN)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="migrate_existing_operation",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def migrate_existing_operation(
    operation_name: str,
    timeout_seconds: int,
    operation_type: str = "code_analysis",
    manager=Depends(get_operation_manager),
):
    """
    Migrate an existing timeout-sensitive operation to use long-running framework

    This endpoint helps transition existing operations that previously used
    simple timeouts to the new checkpoint/resume architecture.
    """
    try:
        # Convert operation type
        op_type = OperationType(operation_type.lower())

        # Create a placeholder operation function
        async def migrated_operation(context):
            """Placeholder for migrated operation"""
            await context.update_progress("Migration placeholder", 0, 1)
            await asyncio.sleep(TimingConstants.STANDARD_DELAY)  # Simulate work
            await context.update_progress("Completed", 1, 1)
            return {"status": "migrated", "original_timeout": timeout_seconds}

        operation_id = await OperationMigrator.migrate_existing_operation(
            operation_name=operation_name,
            operation_function=migrated_operation,
            timeout_seconds=timeout_seconds,
            operation_type=op_type,
        )

        return {"operation_id": operation_id, "status": "migrated"}

    except Exception as e:
        logger.error("Failed to migrate operation: %s", e)
        raise HTTPException(status_code=500, detail="Migration failed")


# Operation status and control endpoints (proxy to integration manager)
@router.get("/{operation_id}", response_model=LongRunningOperationStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_operation_status",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def get_operation_status(
    operation_id: str, manager=Depends(get_operation_manager), current_user: dict = Depends(get_current_user)
):
    """Get detailed operation status: its creator's or an admin's (#17017)"""
    try:
        return operation_view(await _owned_operation(manager, operation_id, current_user))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get operation status: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/", response_model=LongRunningOperationListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_operations",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def list_operations(
    status: str | None = None,
    operation_type: str | None = None,
    limit: int = 50,
    manager=Depends(get_operation_manager),
    current_user: dict = Depends(get_current_user),
):
    """List operations with filtering: a non-admin sees only their own, counts included (#17017)"""
    try:
        # Convert filters
        status_filter = OperationStatus(status) if status else None
        type_filter = OperationType(operation_type) if operation_type else None

        operations = await manager.operation_manager.list_operations(status_filter, type_filter)
        operations = [op for op in operations if _may_see(op, current_user)][:limit]

        # Convert to response format
        operation_responses = [operation_view(op) for op in operations]

        # Issue #321: Use helper method to reduce message chains
        all_operations = [op for op in manager.get_all_operations() if _may_see(op, current_user)]
        total_count = len(all_operations)
        active_count = len([op for op in all_operations if op.status == OperationStatus.RUNNING])
        completed_count = len([op for op in all_operations if op.status == OperationStatus.COMPLETED])
        failed_count = len([op for op in all_operations if op.status in FAILED_OPERATION_STATUSES])

        return {
            "operations": operation_responses,
            "total_count": total_count,
            "active_count": active_count,
            "completed_count": completed_count,
            "failed_count": failed_count,
        }

    except Exception as e:
        logger.error("Failed to list operations: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{operation_id}/cancel", response_model=LongRunningOperationCancelResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_operation",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def cancel_operation(
    operation_id: str, manager=Depends(get_operation_manager), current_user: dict = Depends(get_current_user)
):
    """Cancel a running operation: its creator or an admin (#17017)"""
    try:
        await _owned_operation(manager, operation_id, current_user)
        success = await manager.operation_manager.cancel_operation(operation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Operation not found or cannot be cancelled")

        return {"status": "cancelled", "operation_id": operation_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cancel operation: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{operation_id}/resume", response_model=LongRunningOperationResumeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resume_operation",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def resume_operation(
    operation_id: str, manager=Depends(get_operation_manager), current_user: dict = Depends(get_current_user)
):
    """Resume operation from latest checkpoint: its creator or an admin, who then owns the resumed one (#17017)"""
    try:
        creator = (await _owned_operation(manager, operation_id, current_user)).metadata.get("created_by")
        # Issue #321: Use helper method to reduce message chains
        checkpoints = await manager.list_operation_checkpoints(operation_id)
        if not checkpoints:
            raise HTTPException(status_code=404, detail="No checkpoints found for operation")

        # Use latest checkpoint
        latest_checkpoint = checkpoints[-1]
        new_operation_id = await manager.operation_manager.resume_operation(latest_checkpoint.checkpoint_id)
        resumed = await manager.operation_manager.get_operation(new_operation_id)
        if resumed is not None:
            resumed.metadata.setdefault("created_by", creator)

        return {
            "status": "resumed",
            "new_operation_id": new_operation_id,
            "resumed_from": latest_checkpoint.checkpoint_id,
            "original_operation_id": operation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to resume operation: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.websocket("/{operation_id}/progress")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="websocket_progress_updates",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def websocket_progress_updates(websocket: WebSocket, operation_id: str):
    """WebSocket endpoint for real-time progress updates"""
    # #17009: authenticated before anything is revealed; #17017: the operation's creator or an admin
    if not await open_authenticated_ws(websocket, allow=lambda user: _may_see_id(operation_id, user)):
        return
    if not _OPERATIONS_AVAILABLE:
        await websocket.close(code=1003, reason="Service not available")
        return

    # Add to connections
    if operation_id not in operation_integration_manager.websocket_connections:
        operation_integration_manager.websocket_connections[operation_id] = []
    operation_integration_manager.websocket_connections[operation_id].append(websocket)

    try:
        # Send current progress if operation exists
        operation = await operation_integration_manager.operation_manager.get_operation(operation_id)
        if operation:
            await websocket.send_json(
                {
                    "type": "current_progress",
                    "data": operation_view(operation),
                }
            )

        # Keep connection alive
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=TimingConstants.SHORT_TIMEOUT)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected for operation %s", operation_id)
    finally:
        # Remove from connections
        if (
            operation_id in operation_integration_manager.websocket_connections
            and websocket in operation_integration_manager.websocket_connections[operation_id]
        ):
            operation_integration_manager.websocket_connections[operation_id].remove(websocket)


@register_health_probe(KnownProbes.LONG_RUNNING)
async def probe_long_running(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333 / #6902: probe with rich data so the frontend can read
    ``probes[name=long_running].data.{active_operations,total_operations,...}``
    from /api/system/health and migrate off the legacy
    /api/long-running/health route before sunset.
    """
    if not _OPERATIONS_AVAILABLE:
        return ComponentHealth(
            name="long_running",
            status="down",
            detail="operations framework not available",
            data={
                "active_operations": 0,
                "total_operations": 0,
                "redis_connected": False,
                "background_processor_running": False,
            },
        )
    try:
        all_operations = operation_integration_manager.get_all_operations()
        active_operations = sum(1 for op in all_operations if op.status == OperationStatus.RUNNING)
        redis_connected = operation_integration_manager.redis_client is not None
        background_processor_running = operation_integration_manager.is_background_processor_running()
        return ComponentHealth(
            name="long_running",
            status="ok",
            data={
                "active_operations": active_operations,
                "total_operations": len(all_operations),
                "redis_connected": redis_connected,
                "background_processor_running": background_processor_running,
            },
        )
    except Exception as exc:
        return ComponentHealth(
            name="long_running",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


# Health check endpoint
# Initialize the operation integration manager when this module is imported
async def initialize_operations_service():
    """Initialize the operations service"""
    if operation_integration_manager is not None:
        try:
            await operation_integration_manager.initialize()
            logger.info("Long-running operations service initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize operations service: %s", e)


# Background task to initialize the service
def startup_operations_service():
    """Startup function to initialize operations service"""
    if operation_integration_manager is not None:
        asyncio.create_task(initialize_operations_service())
