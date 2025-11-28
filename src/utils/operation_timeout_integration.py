# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration layer for Long-Running Operations Framework with AutoBot
==================================================================

This module provides seamless integration between the new long-running operations
framework and existing AutoBot components, including:

- FastAPI endpoints for operation management
- WebSocket support for real-time progress updates
- Redis integration for distributed operation tracking
- Migration utilities for existing timeout-sensitive operations
- Monitoring and alerting integration
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

import redis.asyncio as redis
from fastapi import (
    APIRouter,
    BackgroundTasks,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from src.constants.network_constants import ServiceURLs
from src.utils.catalog_http_exceptions import (
    raise_not_found_error,
    raise_server_error,
    raise_validation_error,
)

from .long_running_operations_framework import (
    LongRunningOperation,
    LongRunningOperationManager,
    OperationPriority,
    OperationStatus,
    OperationType,
    execute_codebase_indexing,
    execute_comprehensive_test_suite,
)

logger = logging.getLogger(__name__)


# Pydantic models for API
class CreateOperationRequest(BaseModel):
    operation_type: str
    name: str
    description: str
    priority: str = "normal"
    estimated_items: int = 1
    context: Dict[str, Any] = {}
    execute_immediately: bool = False


class OperationResponse(BaseModel):
    operation_id: str
    operation_type: str
    name: str
    description: str
    status: str
    priority: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress_percentage: float
    processed_items: int
    total_items: int
    current_step: str
    estimated_completion: Optional[str] = None
    error_info: Optional[str] = None


class OperationListResponse(BaseModel):
    operations: List[OperationResponse]
    total_count: int
    active_count: int
    completed_count: int
    failed_count: int


class ProgressUpdateRequest(BaseModel):
    operation_id: str
    current_step: str
    processed_items: int
    total_items: Optional[int] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    status_message: str = ""


class OperationIntegrationManager:
    """Integration manager for long-running operations with AutoBot"""

    def __init__(self, redis_url: str = f"{ServiceURLs.REDIS_VM}/9"):
        self.redis_client = None
        self.redis_url = redis_url
        self.operation_manager = None
        self.websocket_connections: Dict[str, List[WebSocket]] = {}
        self.router = APIRouter(prefix="/operations", tags=["long-running-operations"])
        self._setup_routes()

    async def initialize(self):
        """Initialize the integration manager"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            logger.info("Connected to Redis for operations management")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}, using in-memory storage")
            self.redis_client = None

        self.operation_manager = LongRunningOperationManager(self.redis_client)
        await self.operation_manager.start_background_processor()

        # Subscribe to progress updates for WebSocket broadcasting
        async def progress_callback(progress_data):
            await self._broadcast_progress_update(progress_data)

        # Register callback for all future operations
        self.operation_manager.progress_tracker.progress_callbacks["*"] = [
            progress_callback
        ]

    async def shutdown(self):
        """Shutdown the integration manager"""
        if self.operation_manager:
            await self.operation_manager.stop_background_processor()

        if self.redis_client:
            await self.redis_client.close()

    def _setup_routes(self):
        """Setup FastAPI routes for operation management"""

        @self.router.post("/create", response_model=Dict[str, str])
        async def create_operation(request: CreateOperationRequest):
            """Create a new long-running operation"""
            try:
                # Convert string enums to actual enums
                operation_type = OperationType(request.operation_type.lower())
                priority = OperationPriority[request.priority.upper()]

                # Determine operation function based on type
                operation_function = self._get_operation_function(
                    operation_type, request.context
                )

                operation_id = await self.operation_manager.create_operation(
                    operation_type=operation_type,
                    name=request.name,
                    description=request.description,
                    operation_function=operation_function,
                    priority=priority,
                    estimated_items=request.estimated_items,
                    context=request.context,
                    execute_immediately=request.execute_immediately,
                )

                return {"operation_id": operation_id, "status": "created"}

            except ValueError as e:
                raise_validation_error("API_0001", str(e))
            except Exception as e:
                logger.error(f"Failed to create operation: {e}")
                raise_server_error("API_0003", "Internal server error")

        @self.router.get("/{operation_id}", response_model=OperationResponse)
        async def get_operation(operation_id: str):
            """Get operation details"""
            operation = self.operation_manager.get_operation(operation_id)
            if not operation:
                raise_not_found_error("API_0002", "Operation not found")

            return self._convert_operation_to_response(operation)

        @self.router.get("/", response_model=OperationListResponse)
        async def list_operations(
            status: Optional[str] = None,
            operation_type: Optional[str] = None,
            limit: int = 50,
        ):
            """List operations with optional filtering"""
            status_filter = OperationStatus(status) if status else None
            type_filter = OperationType(operation_type) if operation_type else None

            operations = self.operation_manager.list_operations(
                status_filter, type_filter
            )

            # Limit results
            operations = operations[:limit]

            # Convert to response format
            operation_responses = [
                self._convert_operation_to_response(op) for op in operations
            ]

            # Calculate statistics
            all_operations = list(self.operation_manager.operations.values())
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

            return OperationListResponse(
                operations=operation_responses,
                total_count=total_count,
                active_count=active_count,
                completed_count=completed_count,
                failed_count=failed_count,
            )

        @self.router.post("/{operation_id}/cancel")
        async def cancel_operation(operation_id: str):
            """Cancel a running operation"""
            success = await self.operation_manager.cancel_operation(operation_id)
            if not success:
                raise_not_found_error("API_0002", "Operation not found")

            return {"status": "cancelled"}

        @self.router.post("/{operation_id}/resume")
        async def resume_operation_from_latest_checkpoint(operation_id: str):
            """Resume operation from its latest checkpoint"""
            try:
                checkpoints = (
                    await self.operation_manager.checkpoint_manager.list_checkpoints(
                        operation_id
                    )
                )
                if not checkpoints:
                    raise_not_found_error(
                        "API_0002", "No checkpoints found for operation"
                    )

                # Use latest checkpoint
                latest_checkpoint = checkpoints[-1]
                new_operation_id = await self.operation_manager.resume_operation(
                    latest_checkpoint.checkpoint_id
                )

                return {
                    "status": "resumed",
                    "new_operation_id": new_operation_id,
                    "resumed_from": latest_checkpoint.checkpoint_id,
                }

            except Exception as e:
                logger.error(f"Failed to resume operation: {e}")
                raise_server_error("API_0003", str(e))

        @self.router.post("/{operation_id}/progress")
        async def update_operation_progress(
            operation_id: str, request: ProgressUpdateRequest
        ):
            """Manually update operation progress (for external integrations)"""
            operation = self.operation_manager.get_operation(operation_id)
            if not operation:
                raise_not_found_error("API_0002", "Operation not found")

            await self.operation_manager.progress_tracker.update_progress(
                operation,
                request.current_step,
                request.processed_items,
                request.total_items,
                request.performance_metrics,
                request.status_message,
            )

            return {"status": "updated"}

        @self.router.websocket("/{operation_id}/progress")
        async def websocket_progress_updates(websocket: WebSocket, operation_id: str):
            """WebSocket endpoint for real-time progress updates"""
            await websocket.accept()

            # Add to connections
            if operation_id not in self.websocket_connections:
                self.websocket_connections[operation_id] = []
            self.websocket_connections[operation_id].append(websocket)

            try:
                # Send current progress if operation exists
                operation = self.operation_manager.get_operation(operation_id)
                if operation:
                    await websocket.send_json(
                        {
                            "type": "current_progress",
                            "data": (
                                self._convert_operation_to_response(operation).dict()
                            ),
                        }
                    )

                # Keep connection alive
                while True:
                    # Wait for client messages (ping/pong)
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
                    operation_id in self.websocket_connections
                    and websocket in self.websocket_connections[operation_id]
                ):
                    self.websocket_connections[operation_id].remove(websocket)

        # Specialized operation endpoints
        @self.router.post("/codebase/index")
        async def start_codebase_indexing(
            codebase_path: str,
            file_patterns: Optional[List[str]] = None,
            background_tasks: BackgroundTasks = None,
        ):
            """Start codebase indexing operation"""
            try:
                operation_id = await execute_codebase_indexing(
                    codebase_path, self.operation_manager, file_patterns
                )
                return {"operation_id": operation_id, "status": "started"}
            except Exception as e:
                logger.error(f"Failed to start codebase indexing: {e}")
                raise_server_error("API_0003", str(e))

        @self.router.post("/testing/comprehensive")
        async def start_comprehensive_testing(
            test_suite_path: str,
            test_patterns: Optional[List[str]] = None,
            background_tasks: BackgroundTasks = None,
        ):
            """Start comprehensive test suite operation"""
            try:
                operation_id = await execute_comprehensive_test_suite(
                    test_suite_path, self.operation_manager, test_patterns
                )
                return {"operation_id": operation_id, "status": "started"}
            except Exception as e:
                logger.error(f"Failed to start comprehensive testing: {e}")
                raise_server_error("API_0003", str(e))

    def _get_operation_function(
        self, operation_type: OperationType, context: Dict[str, Any]
    ):
        """Get the appropriate operation function based on type"""

        if operation_type == OperationType.CODEBASE_INDEXING:
            return self._codebase_indexing_wrapper(context)
        elif operation_type == OperationType.COMPREHENSIVE_TEST_SUITE:
            return self._test_suite_wrapper(context)
        elif operation_type == OperationType.CODE_ANALYSIS:
            return self._code_analysis_wrapper(context)
        elif operation_type == OperationType.KB_POPULATION:
            return self._kb_population_wrapper(context)
        else:
            raise ValueError(f"Unsupported operation type: {operation_type}")

    def _codebase_indexing_wrapper(self, context: Dict[str, Any]):
        """Wrapper for codebase indexing operations"""

        async def operation_func(exec_context):
            from pathlib import Path

            from ..knowledge_base import KnowledgeBase

            codebase_path = context.get("codebase_path", "/home/kali/Desktop/AutoBot")
            file_patterns = context.get(
                "file_patterns", ["*.py", "*.js", "*.vue", "*.ts"]
            )

            path = Path(codebase_path)
            if not path.exists():
                raise ValueError(f"Codebase path does not exist: {codebase_path}")

            # Implementation would integrate with actual KnowledgeBase indexing
            # This is a placeholder that shows the integration pattern
            await exec_context.update_progress("Initializing indexing", 0, 1)

            # Simulate actual indexing work
            kb = KnowledgeBase()
            result = await kb.populate_from_codebase(
                codebase_path,
                patterns=file_patterns,
                progress_callback=lambda step, processed, total: exec_context.update_progress(
                    step, processed, total
                ),
            )

            return result

        return operation_func

    def _test_suite_wrapper(self, context: Dict[str, Any]):
        """Wrapper for test suite operations"""

        async def operation_func(exec_context):
            test_path = context.get("test_path", "/home/kali/Desktop/AutoBot/tests")
            test_patterns = context.get("test_patterns", ["test_*.py"])

            # Implementation would integrate with actual test runners
            # This shows the integration pattern
            await exec_context.update_progress("Starting test suite", 0, 1)

            # Simulate test execution
            import subprocess
            from pathlib import Path

            test_files = []
            for pattern in test_patterns:
                test_files.extend(Path(test_path).rglob(pattern))

            results = []
            for i, test_file in enumerate(test_files):
                await exec_context.update_progress(
                    f"Running {test_file.name}", i, len(test_files)
                )

                # Run actual test
                try:
                    result = subprocess.run(
                        ["python", "-m", "pytest", str(test_file), "-v"],
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                    results.append(
                        {
                            "file": str(test_file),
                            "exit_code": result.returncode,
                            "output": result.stdout,
                            "errors": result.stderr,
                        }
                    )
                except subprocess.TimeoutExpired:
                    results.append(
                        {
                            "file": str(test_file),
                            "exit_code": -1,
                            "error": "Test timed out",
                        }
                    )

            return {
                "total_tests": len(test_files),
                "results": results,
                "success_rate": (
                    len([r for r in results if r.get("exit_code") == 0])
                    / len(results)
                    * 100
                ),
            }

        return operation_func

    def _code_analysis_wrapper(self, context: Dict[str, Any]):
        """Wrapper for code analysis operations"""

        async def operation_func(exec_context):
            # Implementation would integrate with existing code analysis tools
            # This is a placeholder showing the pattern
            await exec_context.update_progress("Starting code analysis", 0, 1)

            # Simulate analysis
            await asyncio.sleep(1)

            return {"analysis": "placeholder"}

        return operation_func

    def _kb_population_wrapper(self, context: Dict[str, Any]):
        """Wrapper for knowledge base population operations"""

        async def operation_func(exec_context):
            # Implementation would integrate with KnowledgeBase
            await exec_context.update_progress("Starting KB population", 0, 1)

            # Simulate population
            await asyncio.sleep(1)

            return {"populated": "placeholder"}

        return operation_func

    def _convert_operation_to_response(
        self, operation: LongRunningOperation
    ) -> OperationResponse:
        """Convert internal operation to API response format"""
        return OperationResponse(
            operation_id=operation.operation_id,
            operation_type=operation.operation_type.value,
            name=operation.name,
            description=operation.description,
            status=operation.status.value,
            priority=operation.priority.name.lower(),
            created_at=operation.created_at.isoformat(),
            started_at=(
                operation.started_at.isoformat() if operation.started_at else None
            ),
            completed_at=(
                operation.completed_at.isoformat() if operation.completed_at else None
            ),
            progress_percentage=operation.progress.progress_percentage,
            processed_items=operation.progress.processed_items,
            total_items=operation.progress.total_items,
            current_step=operation.progress.current_step,
            estimated_completion=(
                operation.progress.estimated_completion.isoformat()
                if operation.progress.estimated_completion
                else None
            ),
            error_info=operation.error_info,
        )

    async def _broadcast_progress_update(self, progress_data: Dict[str, Any]):
        """Broadcast progress update to WebSocket connections"""
        operation_id = progress_data["operation_id"]

        if operation_id in self.websocket_connections:
            disconnected = []
            for websocket in self.websocket_connections[operation_id]:
                try:
                    await websocket.send_json(
                        {"type": "progress_update", "data": progress_data}
                    )
                except Exception:
                    disconnected.append(websocket)

            # Remove disconnected websockets
            for ws in disconnected:
                self.websocket_connections[operation_id].remove(ws)


# Singleton instance for global access
operation_integration_manager = OperationIntegrationManager()


# Migration utilities for existing operations
class OperationMigrator:
    """Utility to migrate existing timeout-sensitive operations"""

    @staticmethod
    async def migrate_existing_operation(
        operation_name: str,
        operation_function: Callable,
        timeout_seconds: int,
        operation_type: OperationType = OperationType.CODE_ANALYSIS,
    ) -> str:
        """Migrate an existing operation to use the long-running framework"""

        # Calculate estimated items based on timeout
        estimated_items = max(1, timeout_seconds // 60)  # Rough estimate

        # Create operation
        operation_id = (
            await operation_integration_manager.operation_manager.create_operation(
                operation_type=operation_type,
                name=f"Migrated: {operation_name}",
                description=f"Migrated operation with {timeout_seconds}s timeout",
                operation_function=operation_function,
                priority=OperationPriority.NORMAL,
                estimated_items=estimated_items,
                execute_immediately=True,
            )
        )

        return operation_id

    @staticmethod
    def wrap_existing_function_with_progress(original_function: Callable):
        """Wrap existing function to provide progress updates"""

        async def wrapped_function(context):
            """Wrapped function with progress tracking"""

            # If original function expects progress callback
            if (
                hasattr(original_function, "__code__")
                and "progress_callback" in original_function.__code__.co_varnames
            ):
                progress_callback = (
                    lambda step, processed, total=None: asyncio.create_task(
                        context.update_progress(step, processed, total)
                    )
                )
                return await original_function(progress_callback=progress_callback)
            else:
                # Simple wrapper without progress
                await context.update_progress("Processing", 0, 1)
                result = await original_function()
                await context.update_progress("Completed", 1, 1)
                return result

        return wrapped_function


# Decorator for easy migration of existing functions
def long_running_operation(
    operation_type: OperationType,
    name: Optional[str] = None,
    estimated_items: int = 1,
    priority: OperationPriority = OperationPriority.NORMAL,
):
    """Decorator to convert regular functions into long-running operations"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            operation_name = name or func.__name__

            # Create wrapper function for the operation framework
            async def operation_func(context):
                # Extract original function arguments
                return await func(*args, **kwargs)

            # Create and execute operation
            operation_id = (
                await operation_integration_manager.operation_manager.create_operation(
                    operation_type=operation_type,
                    name=operation_name,
                    description=f"Long-running operation: {operation_name}",
                    operation_function=operation_func,
                    priority=priority,
                    estimated_items=estimated_items,
                    execute_immediately=True,
                )
            )

            return operation_id

        return wrapper

    return decorator


# Example usage
if __name__ == "__main__":

    async def example_integration():
        """Example of how to use the integration"""

        # Initialize
        await operation_integration_manager.initialize()

        try:
            # Example: Migrate existing codebase indexing
            @long_running_operation(
                OperationType.CODEBASE_INDEXING,
                name="Example Codebase Index",
                estimated_items=1000,
            )
            async def index_codebase():
                # Simulate existing function
                await asyncio.sleep(2)
                return {"indexed_files": 1000}

            # Run migrated operation
            operation_id = await index_codebase()
            print(f"Started operation: {operation_id}")

            # Monitor progress
            while True:
                operation = (
                    operation_integration_manager.operation_manager.get_operation(
                        operation_id
                    )
                )
                if operation.status in [
                    OperationStatus.COMPLETED,
                    OperationStatus.FAILED,
                ]:
                    break

                print(f"Progress: {operation.progress.progress_percentage:.1f}%")
                await asyncio.sleep(1)

            print("Operation completed!")

        finally:
            await operation_integration_manager.shutdown()

    # Run example
    asyncio.run(example_integration())
