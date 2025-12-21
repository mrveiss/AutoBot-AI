# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Long-Running Operations API for AutoBot Backend
==============================================

This module provides FastAPI endpoints for managing long-running operations
with proper timeout handling, progress tracking, and checkpoint/resume capabilities.

Integrated with the existing AutoBot backend architecture.
"""

import asyncio
import logging
import sys
from typing import Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.constants.path_constants import PATH
from src.constants.threshold_constants import TimingConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Add AutoBot paths
sys.path.append(str(PATH.PROJECT_ROOT))

# Import our long-running operations framework
try:
    from src.utils.long_running_operations_framework import (
        OperationStatus,
        OperationType,
    )
    from src.utils.operation_timeout_integration import (
        CreateOperationRequest,
        OperationMigrator,
        operation_integration_manager,
    )
except ImportError as e:
    logging.warning(f"Long-running operations framework not available: {e}")
    # Provide fallback implementations
    operation_integration_manager = None

logger = logging.getLogger(__name__)
router = APIRouter(tags=["long-running-operations"])

# Performance optimization: O(1) lookup for failed operation statuses (Issue #326)
FAILED_OPERATION_STATUSES = {OperationStatus.FAILED, OperationStatus.TIMEOUT} if operation_integration_manager else set()


# Additional models specific to AutoBot integration
class CodebaseIndexingRequest(BaseModel):
    """Request model for codebase indexing operations"""

    codebase_path: str = Field(
        default=str(PATH.PROJECT_ROOT), description="Path to codebase to index"
    )
    file_patterns: List[str] = Field(
        default=["*.py", "*.js", "*.vue", "*.ts", "*.jsx", "*.tsx"],
        description="File patterns to include",
    )
    include_tests: bool = Field(default=True, description="Include test files")
    include_docs: bool = Field(default=True, description="Include documentation files")
    max_file_size: int = Field(
        default=1024 * 1024, description="Maximum file size in bytes"
    )
    priority: str = Field(default="normal", description="Operation priority")


class TestSuiteRequest(BaseModel):
    """Request model for comprehensive test suite operations"""

    test_path: str = Field(
        default=str(PATH.TESTS_DIR), description="Path to test directory"
    )
    test_patterns: List[str] = Field(
        default=["test_*.py", "*_test.py"], description="Test file patterns"
    )
    test_types: List[str] = Field(
        default=["unit", "integration", "performance"],
        description="Types of tests to run",
    )
    parallel_execution: bool = Field(default=True, description="Run tests in parallel")
    timeout_per_test: int = Field(
        default=300, description="Timeout per individual test in seconds"
    )
    priority: str = Field(default="high", description="Operation priority")


class KnowledgeBaseRequest(BaseModel):
    """Request model for knowledge base operations"""

    source_paths: List[str] = Field(
        default=[str(PATH.PROJECT_ROOT)], description="Paths to populate from"
    )
    document_types: List[str] = Field(
        default=["code", "docs", "config"], description="Document types to include"
    )
    chunk_size: int = Field(default=1000, description="Chunk size for text processing")
    overlap: int = Field(default=200, description="Overlap between chunks")
    force_reindex: bool = Field(
        default=False, description="Force reindexing of existing documents"
    )
    priority: str = Field(default="normal", description="Operation priority")


class SecurityScanRequest(BaseModel):
    """Request model for security scan operations"""

    scan_paths: List[str] = Field(
        default=[str(PATH.PROJECT_ROOT)], description="Paths to scan"
    )
    scan_types: List[str] = Field(
        default=["vulnerability", "dependency", "secrets"],
        description="Types of security scans",
    )
    severity_threshold: str = Field(
        default="medium", description="Minimum severity to report"
    )
    include_dependencies: bool = Field(default=True, description="Scan dependencies")
    priority: str = Field(default="high", description="Operation priority")


async def get_operation_manager():
    """Dependency to get the operation integration manager"""
    if operation_integration_manager is None:
        raise HTTPException(
            status_code=503, detail="Long-running operations service not available"
        )
    return operation_integration_manager


# Enhanced API endpoints with AutoBot-specific operations
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_codebase_indexing",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
@router.post("/codebase/index", response_model=Dict[str, str])
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

        estimated_files = 0
        try:
            for pattern in request.file_patterns:
                # Issue #358 - avoid blocking rglob() in async context
                pattern_files = await asyncio.to_thread(
                    lambda p=pattern: list(Path(request.codebase_path).rglob(p))
                )
                estimated_files += len(pattern_files)
        except Exception:
            estimated_files = 1000  # Default estimate

        # Create operation using the integration manager
        create_request = CreateOperationRequest(
            operation_type="codebase_indexing",
            name=f"Index codebase: {Path(request.codebase_path).name}",
            description=(
                f"Comprehensive indexing of {request.codebase_path} with"
                f"patterns {request.file_patterns}"
            ),
            priority=request.priority,
            estimated_items=estimated_files,
            context=context,
            execute_immediately=False,
        )

        result = await manager.router.routes[0].endpoint(create_request)

        logger.info("Started codebase indexing operation: %s", result['operation_id'])
        return result

    except Exception as e:
        logger.error("Failed to start codebase indexing: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to start operation: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_comprehensive_testing",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
@router.post("/testing/comprehensive", response_model=Dict[str, str])
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

        estimated_tests = 0
        try:
            for pattern in request.test_patterns:
                # Issue #358 - avoid blocking rglob() in async context
                pattern_files = await asyncio.to_thread(
                    lambda p=pattern: list(Path(request.test_path).rglob(p))
                )
                estimated_tests += len(pattern_files)
        except Exception:
            estimated_tests = 50  # Default estimate

        create_request = CreateOperationRequest(
            operation_type="comprehensive_test_suite",
            name=f"Comprehensive test suite: {Path(request.test_path).name}",
            description=(
                f"Run all tests in {request.test_path} with patterns"
                f"{request.test_patterns}"
            ),
            priority=request.priority,
            estimated_items=estimated_tests,
            context=context,
            execute_immediately=False,
        )

        result = await manager.router.routes[0].endpoint(create_request)

        logger.info(
            f"Started comprehensive testing operation: {result['operation_id']}"
        )
        return result

    except Exception as e:
        logger.error("Failed to start comprehensive testing: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to start operation: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_knowledge_base_population",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
@router.post("/knowledge-base/populate", response_model=Dict[str, str])
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

        logger.info(
            f"Started knowledge base population operation: {result['operation_id']}"
        )
        return result

    except Exception as e:
        logger.error("Failed to start knowledge base population: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to start operation: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_security_scan",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
@router.post("/security/scan", response_model=Dict[str, str])
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

        logger.info("Started security scan operation: %s", result['operation_id'])
        return result

    except Exception as e:
        logger.error("Failed to start security scan: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to start operation: {str(e)}"
        )


# Legacy operation migration endpoints
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="migrate_existing_operation",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
@router.post("/migrate/existing")
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
            await asyncio.sleep(1)  # Simulate work
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
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")


# Operation status and control endpoints (proxy to integration manager)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_operation_status",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
@router.get("/{operation_id}")
async def get_operation_status(
    operation_id: str, manager=Depends(get_operation_manager)
):
    """Get detailed operation status"""
    try:
        operation = manager.operation_manager.get_operation(operation_id)
        if not operation:
            raise HTTPException(status_code=404, detail="Operation not found")

        return manager._convert_operation_to_response(operation)
    except Exception as e:
        logger.error("Failed to get operation status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_operations",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
@router.get("/")
async def list_operations(
    status: Optional[str] = None,
    operation_type: Optional[str] = None,
    limit: int = 50,
    manager=Depends(get_operation_manager),
):
    """List operations with filtering"""
    try:
        # Convert filters
        status_filter = OperationStatus(status) if status else None
        type_filter = OperationType(operation_type) if operation_type else None

        operations = manager.operation_manager.list_operations(
            status_filter, type_filter
        )
        operations = operations[:limit]

        # Convert to response format
        operation_responses = [
            manager._convert_operation_to_response(op) for op in operations
        ]

        # Issue #321: Use helper method to reduce message chains
        all_operations = manager.get_all_operations()
        total_count = len(all_operations)
        active_count = len(
            [op for op in all_operations if op.status == OperationStatus.RUNNING]
        )
        completed_count = len(
            [op for op in all_operations if op.status == OperationStatus.COMPLETED]
        )
        failed_count = len(
            [
                op
                for op in all_operations
                if op.status in FAILED_OPERATION_STATUSES
            ]
        )

        return {
            "operations": operation_responses,
            "total_count": total_count,
            "active_count": active_count,
            "completed_count": completed_count,
            "failed_count": failed_count,
        }

    except Exception as e:
        logger.error("Failed to list operations: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cancel_operation",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
@router.post("/{operation_id}/cancel")
async def cancel_operation(operation_id: str, manager=Depends(get_operation_manager)):
    """Cancel a running operation"""
    try:
        success = await manager.operation_manager.cancel_operation(operation_id)
        if not success:
            raise HTTPException(
                status_code=404, detail="Operation not found or cannot be cancelled"
            )

        return {"status": "cancelled", "operation_id": operation_id}

    except Exception as e:
        logger.error("Failed to cancel operation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resume_operation",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
@router.post("/{operation_id}/resume")
async def resume_operation(operation_id: str, manager=Depends(get_operation_manager)):
    """Resume operation from latest checkpoint"""
    try:
        # Issue #321: Use helper method to reduce message chains
        checkpoints = await manager.list_operation_checkpoints(operation_id)
        if not checkpoints:
            raise HTTPException(
                status_code=404, detail="No checkpoints found for operation"
            )

        # Use latest checkpoint
        latest_checkpoint = checkpoints[-1]
        new_operation_id = await manager.operation_manager.resume_operation(
            latest_checkpoint.checkpoint_id
        )

        return {
            "status": "resumed",
            "new_operation_id": new_operation_id,
            "resumed_from": latest_checkpoint.checkpoint_id,
            "original_operation_id": operation_id,
        }

    except Exception as e:
        logger.error("Failed to resume operation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/{operation_id}/progress")
async def websocket_progress_updates(websocket: WebSocket, operation_id: str):
    """WebSocket endpoint for real-time progress updates"""
    if operation_integration_manager is None:
        await websocket.close(code=1003, reason="Service not available")
        return

    await websocket.accept()

    # Add to connections
    if operation_id not in operation_integration_manager.websocket_connections:
        operation_integration_manager.websocket_connections[operation_id] = []
    operation_integration_manager.websocket_connections[operation_id].append(websocket)

    try:
        # Send current progress if operation exists
        operation = operation_integration_manager.operation_manager.get_operation(
            operation_id
        )
        if operation:
            await websocket.send_json(
                {
                    "type": "current_progress",
                    "data": (
                        operation_integration_manager._convert_operation_to_response(
                            operation
                        ).dict()
                    ),
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
            and websocket
            in operation_integration_manager.websocket_connections[operation_id]
        ):
            operation_integration_manager.websocket_connections[operation_id].remove(
                websocket
            )


# Health check endpoint
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="operations_health",
    error_code_prefix="LONG_RUNNING_OPERATIONS",
)
@router.get("/health")
async def operations_health():
    """Health check for long-running operations service"""
    if operation_integration_manager is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "message": "Long-running operations service not initialized",
            },
        )

    try:
        # Issue #321: Use helper method to reduce message chains
        all_operations = operation_integration_manager.get_all_operations()
        active_operations = len(
            [op for op in all_operations if op.status == OperationStatus.RUNNING]
        )

        return {
            "status": "healthy",
            "active_operations": active_operations,
            "total_operations": len(all_operations),
            "redis_connected": operation_integration_manager.redis_client is not None,
            "background_processor_running": (
                operation_integration_manager.operation_manager._background_processor_task
                is not None
            ),
        }

    except Exception as e:
        return JSONResponse(
            status_code=500, content={"status": "error", "message": str(e)}
        )


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
