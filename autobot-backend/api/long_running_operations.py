# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
from typing import Dict

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
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_path
from constants.path_constants import PATH
from constants.threshold_constants import TimingConstants

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


# Enhanced API endpoints with AutoBot-specific operations
@router.post("/codebase/index", response_model=Dict[str, str])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_codebase_indexing",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def start_codebase_indexing(
    request: CodebaseIndexingRequest,
    background_tasks: BackgroundTasks,
    manager=Depends(get_operation_manager),
):
    """
    Start comprehensive codebase indexing operation

    This operation will:
    - Index all source code files matching the patterns
    - Extract semantic information and relationships
    - Build searchable knowledge base entries
    - Support checkpoint/resume for large codebases
    """
    try:
        # Prepare context with all options
        context = {
            "codebase_path": request.codebase_path,
            "file_patterns": request.file_patterns,
            "include_tests": request.include_tests,
            "include_docs": request.include_docs,
            "max_file_size": request.max_file_size,
            "operation_type": "codebase_indexing",
        }

        # Estimate items based on file patterns
        from pathlib import Path

        try:
            safe_codebase_path = Path(validate_path(request.codebase_path, must_exist=True))
        except (ValueError, PermissionError):
            raise HTTPException(status_code=400, detail="Invalid or inaccessible codebase path")

        estimated_files = 0
        try:
            for pattern in request.file_patterns:
                # Issue #358 - avoid blocking rglob() in async context
                pattern_files = await asyncio.to_thread(lambda p=pattern: list(safe_codebase_path.rglob(p)))
                estimated_files += len(pattern_files)
        except Exception:
            estimated_files = 1000  # Default estimate

        # Create operation using the integration manager
        create_request = CreateOperationRequest(
            operation_type="codebase_indexing",
            name=f"Index codebase: {safe_codebase_path.name}",
            description=(f"Comprehensive indexing of {safe_codebase_path} with" f"patterns {request.file_patterns}"),
            priority=request.priority,
            estimated_items=estimated_files,
            context=context,
            execute_immediately=False,
        )

        result = await manager.router.routes[0].endpoint(create_request)

        logger.info("Started codebase indexing operation: %s", result["operation_id"])
        return result

    except Exception as e:
        logger.error("Failed to start codebase indexing: %s", e)
        raise HTTPException(status_code=500, detail="Failed to start operation")


@router.post("/testing/comprehensive", response_model=Dict[str, str])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_comprehensive_testing",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def start_comprehensive_testing(
    request: TestSuiteRequest,
    background_tasks: BackgroundTasks,
    manager=Depends(get_operation_manager),
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

        # Estimate test count
        from pathlib import Path

        try:
            safe_test_path = Path(validate_path(request.test_path, must_exist=True))
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
        )

        result = await manager.router.routes[0].endpoint(create_request)

        logger.info(f"Started comprehensive testing operation: {result['operation_id']}")
        return result

    except Exception as e:
        logger.error("Failed to start comprehensive testing: %s", e)
        raise HTTPException(status_code=500, detail="Failed to start operation")


@router.post("/knowledge-base/populate", response_model=Dict[str, str])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_knowledge_base_population",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def start_knowledge_base_population(
    request: KnowledgeBaseRequest,
    background_tasks: BackgroundTasks,
    manager=Depends(get_operation_manager),
):
    """
    Start knowledge base population operation

    This operation will:
    - Process documents from specified source paths
    - Extract and chunk text content appropriately
    - Generate embeddings and build searchable index
    - Support incremental updates and force reindexing
    """
    try:
        context = {
            "source_paths": request.source_paths,
            "document_types": request.document_types,
            "chunk_size": request.chunk_size,
            "overlap": request.overlap,
            "force_reindex": request.force_reindex,
            "operation_type": "kb_population",
        }

        # Estimate documents
        estimated_docs = len(request.source_paths) * 100  # Rough estimate

        create_request = CreateOperationRequest(
            operation_type="kb_population",
            name="Knowledge base population",
            description=f"Populate knowledge base from {len(request.source_paths)} source paths",
            priority=request.priority,
            estimated_items=estimated_docs,
            context=context,
            execute_immediately=False,
        )

        result = await manager.router.routes[0].endpoint(create_request)

        logger.info(f"Started knowledge base population operation: {result['operation_id']}")
        return result

    except Exception as e:
        logger.error("Failed to start knowledge base population: %s", e)
        raise HTTPException(status_code=500, detail="Failed to start operation")


@router.post("/security/scan", response_model=Dict[str, str])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_security_scan",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def start_security_scan(
    request: SecurityScanRequest,
    background_tasks: BackgroundTasks,
    manager=Depends(get_operation_manager),
):
    """
    Start comprehensive security scan operation

    This operation will:
    - Scan code for security vulnerabilities
    - Check dependencies for known issues
    - Search for exposed secrets and credentials
    - Generate detailed security report
    """
    try:
        context = {
            "scan_paths": request.scan_paths,
            "scan_types": request.scan_types,
            "severity_threshold": request.severity_threshold,
            "include_dependencies": request.include_dependencies,
            "operation_type": "security_scan",
        }

        # Estimate files to scan
        estimated_files = len(request.scan_paths) * 200  # Rough estimate

        create_request = CreateOperationRequest(
            operation_type="security_scan",
            name="Security scan",
            description=f"Comprehensive security scan of {len(request.scan_paths)} paths",
            priority=request.priority,
            estimated_items=estimated_files,
            context=context,
            execute_immediately=False,
        )

        result = await manager.router.routes[0].endpoint(create_request)

        logger.info("Started security scan operation: %s", result["operation_id"])
        return result

    except Exception as e:
        logger.error("Failed to start security scan: %s", e)
        raise HTTPException(status_code=500, detail="Failed to start operation")


# Legacy operation migration endpoints
@router.post("/migrate/existing", response_model=LongRunningOperationMigrateResponse)
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
async def get_operation_status(operation_id: str, manager=Depends(get_operation_manager)):
    """Get detailed operation status"""
    try:
        operation = manager.operation_manager.get_operation(operation_id)
        if not operation:
            raise HTTPException(status_code=404, detail="Operation not found")

        return manager._convert_operation_to_response(operation)
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
):
    """List operations with filtering"""
    try:
        # Convert filters
        status_filter = OperationStatus(status) if status else None
        type_filter = OperationType(operation_type) if operation_type else None

        operations = manager.operation_manager.list_operations(status_filter, type_filter)
        operations = operations[:limit]

        # Convert to response format
        operation_responses = [manager._convert_operation_to_response(op) for op in operations]

        # Issue #321: Use helper method to reduce message chains
        all_operations = manager.get_all_operations()
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
async def cancel_operation(operation_id: str, manager=Depends(get_operation_manager)):
    """Cancel a running operation"""
    try:
        success = await manager.operation_manager.cancel_operation(operation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Operation not found or cannot be cancelled")

        return {"status": "cancelled", "operation_id": operation_id}

    except Exception as e:
        logger.error("Failed to cancel operation: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{operation_id}/resume", response_model=LongRunningOperationResumeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resume_operation",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
async def resume_operation(operation_id: str, manager=Depends(get_operation_manager)):
    """Resume operation from latest checkpoint"""
    try:
        # Issue #321: Use helper method to reduce message chains
        checkpoints = await manager.list_operation_checkpoints(operation_id)
        if not checkpoints:
            raise HTTPException(status_code=404, detail="No checkpoints found for operation")

        # Use latest checkpoint
        latest_checkpoint = checkpoints[-1]
        new_operation_id = await manager.operation_manager.resume_operation(latest_checkpoint.checkpoint_id)

        return {
            "status": "resumed",
            "new_operation_id": new_operation_id,
            "resumed_from": latest_checkpoint.checkpoint_id,
            "original_operation_id": operation_id,
        }

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
    if not _OPERATIONS_AVAILABLE:
        await websocket.close(code=1003, reason="Service not available")
        return

    await websocket.accept()

    # Add to connections
    if operation_id not in operation_integration_manager.websocket_connections:
        operation_integration_manager.websocket_connections[operation_id] = []
    operation_integration_manager.websocket_connections[operation_id].append(websocket)

    try:
        # Send current progress if operation exists
        operation = operation_integration_manager.operation_manager.get_operation(operation_id)
        if operation:
            await websocket.send_json(
                {
                    "type": "current_progress",
                    "data": (operation_integration_manager._convert_operation_to_response(operation).dict()),
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
