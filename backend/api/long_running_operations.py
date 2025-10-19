"""
Long-Running Operations API for AutoBot Backend
==============================================

This module provides FastAPI endpoints for managing long-running operations
with proper timeout handling, progress tracking, and checkpoint/resume capabilities.

Integrated with the existing AutoBot backend architecture.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import (
    APIRouter,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    BackgroundTasks,
    Depends,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import sys
import os
from src.constants.network_constants import NetworkConstants

# Add AutoBot paths
sys.path.append("/home/kali/Desktop/AutoBot")

# Import our long-running operations framework
try:
    from src.utils.operation_timeout_integration import (
        operation_integration_manager,
        CreateOperationRequest,
        OperationResponse,
        OperationListResponse,
        ProgressUpdateRequest,
        OperationMigrator,
    )
    from src.utils.long_running_operations_framework import (
        OperationType,
        OperationStatus,
        OperationPriority,
    )
except ImportError as e:
    logging.warning(f"Long-running operations framework not available: {e}")
    # Provide fallback implementations
    operation_integration_manager = None

logger = logging.getLogger(__name__)
router = APIRouter(tags=["long-running-operations"])


# Additional models specific to AutoBot integration
class CodebaseIndexingRequest(BaseModel):
    """Request model for codebase indexing operations"""

    codebase_path: str = Field(
        default="/home/kali/Desktop/AutoBot", description="Path to codebase to index"
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
        default="/home/kali/Desktop/AutoBot/tests", description="Path to test directory"
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
        default=["/home/kali/Desktop/AutoBot"], description="Paths to populate from"
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
        default=["/home/kali/Desktop/AutoBot"], description="Paths to scan"
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
                estimated_files += len(list(Path(request.codebase_path).rglob(pattern)))
        except Exception:
            estimated_files = 1000  # Default estimate

        # Create operation using the integration manager
        create_request = CreateOperationRequest(
            operation_type="codebase_indexing",
            name=f"Index codebase: {Path(request.codebase_path).name}",
            description=f"Comprehensive indexing of {request.codebase_path} with patterns {request.file_patterns}",
            priority=request.priority,
            estimated_items=estimated_files,
            context=context,
            execute_immediately=False,
        )

        result = await manager.router.routes[0].endpoint(create_request)

        logger.info(f"Started codebase indexing operation: {result['operation_id']}")
        return result

    except Exception as e:
        logger.error(f"Failed to start codebase indexing: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start operation: {str(e)}"
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
                estimated_tests += len(list(Path(request.test_path).rglob(pattern)))
        except Exception:
            estimated_tests = 50  # Default estimate

        create_request = CreateOperationRequest(
            operation_type="comprehensive_test_suite",
            name=f"Comprehensive test suite: {Path(request.test_path).name}",
            description=f"Run all tests in {request.test_path} with patterns {request.test_patterns}",
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
        logger.error(f"Failed to start comprehensive testing: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start operation: {str(e)}"
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
        logger.error(f"Failed to start knowledge base population: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start operation: {str(e)}"
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

        logger.info(f"Started security scan operation: {result['operation_id']}")
        return result

    except Exception as e:
        logger.error(f"Failed to start security scan: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start operation: {str(e)}"
        )


# Legacy operation migration endpoints
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
        logger.error(f"Failed to migrate operation: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")


# Operation status and control endpoints (proxy to integration manager)
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
        logger.error(f"Failed to get operation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

        # Calculate statistics
        all_operations = list(manager.operation_manager.operations.values())
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
                if op.status in [OperationStatus.FAILED, OperationStatus.TIMEOUT]
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
        logger.error(f"Failed to list operations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error(f"Failed to cancel operation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{operation_id}/resume")
async def resume_operation(operation_id: str, manager=Depends(get_operation_manager)):
    """Resume operation from latest checkpoint"""
    try:
        checkpoints = (
            await manager.operation_manager.checkpoint_manager.list_checkpoints(
                operation_id
            )
        )
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
        logger.error(f"Failed to resume operation: {e}")
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
                    "data": operation_integration_manager._convert_operation_to_response(
                        operation
                    ).dict(),
                }
            )

        # Keep connection alive
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        pass
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
        # Check if manager is properly initialized
        active_operations = len(
            [
                op
                for op in operation_integration_manager.operation_manager.operations.values()
                if op.status == OperationStatus.RUNNING
            ]
        )

        return {
            "status": "healthy",
            "active_operations": active_operations,
            "total_operations": len(
                operation_integration_manager.operation_manager.operations
            ),
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
            logger.error(f"Failed to initialize operations service: {e}")


# Background task to initialize the service
def startup_operations_service():
    """Startup function to initialize operations service"""
    if operation_integration_manager is not None:
        asyncio.create_task(initialize_operations_service())
