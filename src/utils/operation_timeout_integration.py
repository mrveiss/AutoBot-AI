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
from fastapi import APIRouter, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.constants.network_constants import ServiceURLs
from src.constants.threshold_constants import TimingConstants
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

# Performance optimization: O(1) lookup for operation status checks (Issue #326)
FAILED_OPERATION_STATUSES = {OperationStatus.FAILED, OperationStatus.TIMEOUT}
TERMINAL_OPERATION_STATUSES = {
    OperationStatus.COMPLETED,
    OperationStatus.FAILED,
    OperationStatus.CANCELLED,
}


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
        """Initialize operation integration manager with Redis URL."""
        self.redis_client = None
        self.redis_url = redis_url
        self.operation_manager = None
        self.websocket_connections: Dict[str, List[WebSocket]] = {}
        self.router = APIRouter(prefix="/operations", tags=["long-running-operations"])

        # Lock for thread-safe access to websocket_connections
        self._ws_lock = asyncio.Lock()

        self._setup_routes()

    async def initialize(self):
        """Initialize the integration manager"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            logger.info("Connected to Redis for operations management")
        except Exception as e:
            logger.warning("Failed to connect to Redis: %s, using in-memory storage", e)
            self.redis_client = None

        self.operation_manager = LongRunningOperationManager(self.redis_client)
        await self.operation_manager.start_background_processor()

        # Subscribe to progress updates for WebSocket broadcasting
        # Note: OperationProgressTracker uses subscribe_to_progress method
        # We use "*" as wildcard operation_id for global subscriptions
        async def progress_callback(operation):
            """Broadcast progress updates to connected WebSocket clients."""
            progress_data = {
                "operation_id": operation.operation_id,
                "progress": operation.progress.progress_percent,
                "current_step": operation.progress.current_step,
            }
            await self._broadcast_progress_update(progress_data)

        # Register callback for global progress updates
        await self.operation_manager.progress_tracker.subscribe_to_progress(
            "*", progress_callback
        )

    async def shutdown(self):
        """Shutdown the integration manager"""
        if self.operation_manager:
            await self.operation_manager.stop_background_processor()

        if self.redis_client:
            await self.redis_client.close()

    async def _handle_create_operation(
        self, request: CreateOperationRequest
    ) -> Dict[str, str]:
        """Handle create operation request."""
        try:
            operation_type = OperationType(request.operation_type.lower())
            priority = OperationPriority[request.priority.upper()]
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
            logger.error("Failed to create operation: %s", e)
            raise_server_error("API_0003", "Internal server error")

    def _calculate_operation_stats(self) -> tuple[int, int, int, int]:
        """Calculate operation statistics."""
        all_operations = self.get_all_operations()
        return (
            len(all_operations),
            len([op for op in all_operations if op.status == OperationStatus.RUNNING]),
            len(
                [op for op in all_operations if op.status == OperationStatus.COMPLETED]
            ),
            len(
                [op for op in all_operations if op.status in FAILED_OPERATION_STATUSES]
            ),
        )

    # Issue #321: Helper methods to reduce message chains (Law of Demeter)
    def get_all_operations(self) -> List[LongRunningOperation]:
        """Get all operations as a list, reducing operation_manager.operations.values() chain."""
        if self.operation_manager:
            return list(self.operation_manager.operations.values())
        return []

    async def list_operation_checkpoints(self, operation_id: str) -> List:
        """List checkpoints for operation, reducing checkpoint_manager.list_checkpoints chain."""
        if self.operation_manager and self.operation_manager.checkpoint_manager:
            return await self.operation_manager.checkpoint_manager.list_checkpoints(
                operation_id
            )
        return []

    async def update_operation_progress(
        self,
        operation: LongRunningOperation,
        current_step: str,
        processed_items: int,
        total_items: Optional[int] = None,
        performance_metrics: Optional[Dict[str, Any]] = None,
        status_message: str = "",
    ) -> None:
        """Update operation progress, reducing progress_tracker.update_progress chain."""
        if self.operation_manager:
            await self.operation_manager.progress_tracker.update_progress(
                operation,
                current_step,
                processed_items,
                total_items,
                performance_metrics,
                status_message,
            )

    async def _handle_websocket_connection(
        self, websocket: WebSocket, operation_id: str
    ):
        """Handle WebSocket connection for progress updates."""
        await websocket.accept()
        async with self._ws_lock:
            if operation_id not in self.websocket_connections:
                self.websocket_connections[operation_id] = []
            self.websocket_connections[operation_id].append(websocket)
        try:
            operation = self.operation_manager.get_operation(operation_id)
            if operation:
                response_data = self._convert_operation_to_response(operation).dict()
                await websocket.send_json(
                    {"type": "current_progress", "data": response_data}
                )
            while True:
                try:
                    await asyncio.wait_for(
                        websocket.receive_text(), timeout=TimingConstants.SHORT_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            logger.debug(
                "WebSocket client disconnected from operation %s", operation_id
            )
        finally:
            async with self._ws_lock:
                if (
                    operation_id in self.websocket_connections
                    and websocket in self.websocket_connections[operation_id]
                ):
                    self.websocket_connections[operation_id].remove(websocket)

    async def _handle_resume_operation(self, operation_id: str) -> Dict[str, str]:
        """Handle resume operation from latest checkpoint."""
        try:
            # Issue #321: Use helper method to reduce message chains
            checkpoints = await self.list_operation_checkpoints(operation_id)
            if not checkpoints:
                raise_not_found_error("API_0002", "No checkpoints found for operation")
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
            logger.error("Failed to resume operation: %s", e)
            raise_server_error("API_0003", str(e))

    async def _handle_update_progress(
        self, operation_id: str, request: ProgressUpdateRequest
    ) -> Dict[str, str]:
        """Handle update progress request."""
        operation = self.operation_manager.get_operation(operation_id)
        if not operation:
            raise_not_found_error("API_0002", "Operation not found")
        # Issue #321: Use helper method to reduce message chains
        await self.update_operation_progress(
            operation,
            request.current_step,
            request.processed_items,
            request.total_items,
            request.performance_metrics,
            request.status_message,
        )
        return {"status": "updated"}

    async def _handle_start_indexing(
        self, codebase_path: str, file_patterns: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """Handle start codebase indexing request."""
        try:
            operation_id = await execute_codebase_indexing(
                codebase_path, self.operation_manager, file_patterns
            )
            return {"operation_id": operation_id, "status": "started"}
        except Exception as e:
            logger.error("Failed to start codebase indexing: %s", e)
            raise_server_error("API_0003", str(e))

    async def _handle_start_testing(
        self, test_suite_path: str, test_patterns: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """Handle start comprehensive testing request."""
        try:
            operation_id = await execute_comprehensive_test_suite(
                test_suite_path, self.operation_manager, test_patterns
            )
            return {"operation_id": operation_id, "status": "started"}
        except Exception as e:
            logger.error("Failed to start comprehensive testing: %s", e)
            raise_server_error("API_0003", str(e))

    def _setup_routes(self):
        """Setup FastAPI routes for operation management. Issue #620."""
        self._setup_crud_routes()
        self._setup_lifecycle_routes()
        self._setup_specialized_routes()

    def _setup_crud_routes(self):
        """Setup CRUD routes for operation management. Issue #620."""

        @self.router.post("/create", response_model=Dict[str, str])
        async def create_operation(request: CreateOperationRequest):
            """Create a new long-running operation."""
            return await self._handle_create_operation(request)

        @self.router.get("/{operation_id}", response_model=OperationResponse)
        async def get_operation(operation_id: str):
            """Get operation details by ID."""
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
            """List operations with optional status and type filters."""
            status_filter = OperationStatus(status) if status else None
            type_filter = OperationType(operation_type) if operation_type else None
            operations = self.operation_manager.list_operations(
                status_filter, type_filter
            )[:limit]
            operation_responses = [
                self._convert_operation_to_response(op) for op in operations
            ]
            total, active, completed, failed = self._calculate_operation_stats()
            return OperationListResponse(
                operations=operation_responses,
                total_count=total,
                active_count=active,
                completed_count=completed,
                failed_count=failed,
            )

    def _setup_lifecycle_routes(self):
        """Setup operation lifecycle routes (cancel, resume, progress). Issue #620."""

        @self.router.post("/{operation_id}/cancel")
        async def cancel_operation(operation_id: str):
            """Cancel a running operation."""
            if not await self.operation_manager.cancel_operation(operation_id):
                raise_not_found_error("API_0002", "Operation not found")
            return {"status": "cancelled"}

        @self.router.post("/{operation_id}/resume")
        async def resume_operation_from_latest_checkpoint(operation_id: str):
            """Resume a paused operation from its latest checkpoint."""
            return await self._handle_resume_operation(operation_id)

        @self.router.post("/{operation_id}/progress")
        async def update_operation_progress(
            operation_id: str, request: ProgressUpdateRequest
        ):
            """Update progress for a running operation."""
            return await self._handle_update_progress(operation_id, request)

        @self.router.websocket("/{operation_id}/progress")
        async def websocket_progress_updates(websocket: WebSocket, operation_id: str):
            """WebSocket endpoint for real-time progress updates."""
            await self._handle_websocket_connection(websocket, operation_id)

    def _setup_specialized_routes(self):
        """Setup specialized operation routes (indexing, testing). Issue #620."""

        @self.router.post("/codebase/index")
        async def start_codebase_indexing(
            codebase_path: str,
            file_patterns: Optional[List[str]] = None,
            background_tasks: BackgroundTasks = None,
        ):
            """Start a codebase indexing operation."""
            return await self._handle_start_indexing(codebase_path, file_patterns)

        @self.router.post("/testing/comprehensive")
        async def start_comprehensive_testing(
            test_suite_path: str,
            test_patterns: Optional[List[str]] = None,
            background_tasks: BackgroundTasks = None,
        ):
            """Start a comprehensive testing operation."""
            return await self._handle_start_testing(test_suite_path, test_patterns)

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
            """Execute codebase indexing with progress updates."""
            from pathlib import Path

            from ..knowledge_base import KnowledgeBase

            codebase_path = context.get("codebase_path", "/home/kali/Desktop/AutoBot")
            file_patterns = context.get(
                "file_patterns", ["*.py", "*.js", "*.vue", "*.ts"]
            )

            path = Path(codebase_path)
            # Issue #358 - avoid blocking
            if not await asyncio.to_thread(path.exists):
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

    async def _collect_test_files(
        self, test_path: str, test_patterns: List[str]
    ) -> List:
        """Collect test files matching the given patterns."""
        from pathlib import Path

        test_files = []
        for pattern in test_patterns:
            # Issue #358 - avoid blocking
            pattern_files = await asyncio.to_thread(
                lambda p=pattern: list(Path(test_path).rglob(p))
            )
            test_files.extend(pattern_files)
        return test_files

    async def _run_single_test(self, test_file) -> Dict[str, Any]:
        """Run a single test file and return the result."""
        try:
            process = await asyncio.create_subprocess_exec(
                "python",
                "-m",
                "pytest",
                str(test_file),
                "-v",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            return {
                "file": str(test_file),
                "exit_code": process.returncode,
                "output": stdout.decode("utf-8"),
                "errors": stderr.decode("utf-8"),
            }
        except asyncio.TimeoutError:
            return {
                "file": str(test_file),
                "exit_code": -1,
                "error": "Test timed out",
            }

    def _calculate_test_success_rate(self, results: List[Dict[str, Any]]) -> float:
        """Calculate the success rate from test results."""
        if not results:
            return 0.0
        return len([r for r in results if r.get("exit_code") == 0]) / len(results) * 100

    def _test_suite_wrapper(self, context: Dict[str, Any]):
        """Wrapper for test suite operations"""

        async def operation_func(exec_context):
            """Execute test suite with progress tracking."""
            test_path = context.get("test_path", "/home/kali/Desktop/AutoBot/tests")
            test_patterns = context.get("test_patterns", ["test_*.py"])

            await exec_context.update_progress("Starting test suite", 0, 1)

            test_files = await self._collect_test_files(test_path, test_patterns)

            results = []
            for i, test_file in enumerate(test_files):
                await exec_context.update_progress(
                    f"Running {test_file.name}", i, len(test_files)
                )
                result = await self._run_single_test(test_file)
                results.append(result)

            return {
                "total_tests": len(test_files),
                "results": results,
                "success_rate": self._calculate_test_success_rate(results),
            }

        return operation_func

    def _code_analysis_wrapper(self, context: Dict[str, Any]):
        """Wrapper for code analysis operations"""

        async def operation_func(exec_context):
            """Execute code analysis with progress tracking."""
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
            """Execute knowledge base population with progress tracking."""
            # Implementation would integrate with KnowledgeBase
            await exec_context.update_progress("Starting KB population", 0, 1)

            # Simulate population
            await asyncio.sleep(1)

            return {"populated": "placeholder"}

        return operation_func

    def _convert_operation_to_response(
        self, operation: LongRunningOperation
    ) -> OperationResponse:
        """Convert internal operation to API response format (Issue #372 - uses model method)"""
        return OperationResponse(**operation.to_response_dict())

    async def _broadcast_progress_update(self, progress_data: Dict[str, Any]):
        """Broadcast progress update to WebSocket connections (thread-safe)"""
        operation_id = progress_data["operation_id"]

        # Get a copy of connections under lock
        async with self._ws_lock:
            if operation_id not in self.websocket_connections:
                return
            connections = list(self.websocket_connections[operation_id])

        # Send to connections outside lock (avoid holding lock during I/O)
        disconnected = []
        for websocket in connections:
            try:
                await websocket.send_json(
                    {"type": "progress_update", "data": progress_data}
                )
            except Exception:
                disconnected.append(websocket)

        # Remove disconnected websockets under lock
        if disconnected:
            async with self._ws_lock:
                for ws in disconnected:
                    if (
                        operation_id in self.websocket_connections
                        and ws in self.websocket_connections[operation_id]
                    ):
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
        """Inner decorator that wraps function for long-running operation tracking."""

        async def wrapper(*args, **kwargs):
            """Wrapper that creates and executes the operation."""
            operation_name = name or func.__name__

            # Create wrapper function for the operation framework
            async def operation_func(context):
                """Operation function that executes the decorated function."""
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
                """Example decorated function for codebase indexing."""
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
                # Check if operation reached terminal state (Issue #326)
                # Note: Using subset of TERMINAL_OPERATION_STATUSES
                # (excluding CANCELLED for this polling loop)
                if operation.status in {
                    OperationStatus.COMPLETED,
                    OperationStatus.FAILED,
                }:
                    break

                print(f"Progress: {operation.progress.progress_percentage:.1f}%")
                await asyncio.sleep(1)

            print("Operation completed!")

        finally:
            await operation_integration_manager.shutdown()

    # Run example
    asyncio.run(example_integration())
