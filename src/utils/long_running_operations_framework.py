"""
Comprehensive Long-Running Operations Framework for AutoBot
==========================================================

This framework provides intelligent timeout management for operations that need
to run for extended periods (potentially hours) with proper progress tracking,
checkpoint/resume capabilities, and resilience.

Key Features:
- Dynamic timeout profiles based on operation type and complexity
- Checkpoint/resume capabilities for operation resilience
- Real-time progress tracking with WebSocket broadcasting
- Background operation management with proper resource control
- Graceful failure handling with detailed diagnostics
- Integration with existing AutoBot timeout framework

Operation Types Supported:
- Code indexing and analysis (potentially hours for large codebases)
- Comprehensive test suites (extensive validation procedures)
- Knowledge base population and optimization
- Large-scale file operations and migrations
- Performance benchmarking and profiling
- Security scans and audits
"""

import asyncio
import json
import logging
import os
import pickle
import signal
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Union

import redis.asyncio as redis

# Import existing timeout framework
from src.constants.network_constants import NetworkConstants
from src.constants.path_constants import PATH

from .adaptive_timeouts import (
    AdaptiveTimeoutConfig,
    AdaptiveTimeout,
    TimeoutCategory,
)

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of long-running operations"""

    # Code Analysis Operations
    CODEBASE_INDEXING = "codebase_indexing"
    CODE_ANALYSIS = "code_analysis"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    SECURITY_SCAN = "security_scan"
    PERFORMANCE_PROFILING = "performance_profiling"

    # Testing Operations
    COMPREHENSIVE_TEST_SUITE = "comprehensive_test_suite"
    INTEGRATION_TESTING = "integration_testing"
    PERFORMANCE_TESTING = "performance_testing"
    LOAD_TESTING = "load_testing"

    # Knowledge Base Operations
    KB_POPULATION = "kb_population"
    KB_OPTIMIZATION = "kb_optimization"
    VECTOR_INDEXING = "vector_indexing"
    SEMANTIC_ANALYSIS = "semantic_analysis"

    # System Operations
    BACKUP_OPERATION = "backup_operation"
    MIGRATION_OPERATION = "migration_operation"
    CLEANUP_OPERATION = "cleanup_operation"
    MONITORING_COLLECTION = "monitoring_collection"


class OperationStatus(Enum):
    """Operation execution status"""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    CHECKPOINT_SAVED = "checkpoint_saved"
    RESUMING = "resuming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class OperationPriority(Enum):
    """Operation priority levels"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class OperationCheckpoint:
    """Checkpoint data for operation resume"""

    operation_id: str
    checkpoint_id: str
    timestamp: datetime
    progress_percentage: float
    processed_items: int
    total_items: int
    intermediate_results: Dict[str, Any]
    context_data: Dict[str, Any]
    next_step: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationProgress:
    """Real-time progress tracking"""

    operation_id: str
    current_step: str
    progress_percentage: float
    processed_items: int
    total_items: int
    estimated_completion: Optional[datetime]
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    status_message: str = ""
    detailed_status: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LongRunningOperation:
    """Definition of a long-running operation"""

    operation_id: str
    operation_type: OperationType
    name: str
    description: str
    priority: OperationPriority
    status: OperationStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: OperationProgress = None
    checkpoints: List[OperationCheckpoint] = field(default_factory=list)
    timeout_config: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error_info: Optional[str] = None

    def __post_init__(self):
        if self.progress is None:
            self.progress = OperationProgress(
                operation_id=self.operation_id,
                current_step="Initializing",
                progress_percentage=0.0,
                processed_items=0,
                total_items=0,
                estimated_completion=None,
            )


class LongRunningTimeoutConfig:
    """Specialized timeout configuration for long-running operations"""

    # Operation-specific timeout configurations
    OPERATION_TIMEOUTS = {
        OperationType.CODEBASE_INDEXING: {
            "base_timeout": 3600,  # 1 hour base
            "per_file_timeout": 10,  # 10 seconds per file
            "max_timeout": 14400,  # 4 hours maximum
            "checkpoint_interval": 300,  # 5 minutes
            "progress_report_interval": 30,  # 30 seconds
            "failure_threshold": 5,  # Max failures before abort
        },
        OperationType.CODE_ANALYSIS: {
            "base_timeout": 1800,  # 30 minutes base
            "per_file_timeout": 5,
            "max_timeout": 7200,  # 2 hours maximum
            "checkpoint_interval": 180,
            "progress_report_interval": 15,
            "failure_threshold": 3,
        },
        OperationType.COMPREHENSIVE_TEST_SUITE: {
            "base_timeout": 2400,  # 40 minutes base
            "per_test_timeout": 120,  # 2 minutes per test
            "max_timeout": 10800,  # 3 hours maximum
            "checkpoint_interval": 600,  # 10 minutes
            "progress_report_interval": 60,  # 1 minute
            "failure_threshold": 10,
        },
        OperationType.KB_POPULATION: {
            "base_timeout": 1800,  # 30 minutes base
            "per_document_timeout": 30,  # 30 seconds per document
            "max_timeout": 7200,  # 2 hours maximum
            "checkpoint_interval": 300,
            "progress_report_interval": 30,
            "failure_threshold": 5,
        },
        OperationType.SECURITY_SCAN: {
            "base_timeout": 2700,  # 45 minutes base
            "per_file_timeout": 15,
            "max_timeout": 10800,  # 3 hours maximum
            "checkpoint_interval": 300,
            "progress_report_interval": 60,
            "failure_threshold": 3,
        },
    }

    @classmethod
    def get_timeout_config(
        cls, operation_type: OperationType, estimated_items: int = 1
    ) -> Dict[str, Any]:
        """Calculate dynamic timeout configuration"""

        base_config = cls.OPERATION_TIMEOUTS.get(
            operation_type, cls.OPERATION_TIMEOUTS[OperationType.CODE_ANALYSIS]
        )

        # Calculate dynamic timeout based on estimated items
        base_timeout = base_config["base_timeout"]
        per_item_timeout = base_config.get(
            "per_file_timeout", base_config.get("per_test_timeout", 10)
        )
        max_timeout = base_config["max_timeout"]

        calculated_timeout = min(
            base_timeout + (estimated_items * per_item_timeout), max_timeout
        )

        return {
            **base_config,
            "calculated_timeout": calculated_timeout,
            "estimated_items": estimated_items,
        }


class OperationCheckpointManager:
    """Manages checkpoints for operation resume capability"""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.checkpoint_dir = PATH.get_data_path("checkpoints")
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    async def save_checkpoint(
        self,
        operation: LongRunningOperation,
        intermediate_results: Dict[str, Any],
        context_data: Dict[str, Any],
        next_step: str,
    ) -> str:
        """Save operation checkpoint"""

        checkpoint_id = f"checkpoint_{operation.operation_id}_{int(time.time())}"
        checkpoint = OperationCheckpoint(
            operation_id=operation.operation_id,
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now(),
            progress_percentage=operation.progress.progress_percentage,
            processed_items=operation.progress.processed_items,
            total_items=operation.progress.total_items,
            intermediate_results=intermediate_results,
            context_data=context_data,
            next_step=next_step,
            metadata={
                "operation_type": operation.operation_type.value,
                "operation_name": operation.name,
            },
        )

        # Save to Redis if available
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    f"checkpoint:{checkpoint_id}",
                    3600 * 24 * 7,  # 7 days TTL
                    pickle.dumps(checkpoint),
                )
                logger.info(f"Checkpoint {checkpoint_id} saved to Redis")
            except Exception as e:
                logger.warning(f"Failed to save checkpoint to Redis: {e}")

        # Save to filesystem as backup
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.pkl"
        try:
            with open(checkpoint_file, "wb") as f:
                pickle.dump(checkpoint, f)
            logger.info(f"Checkpoint {checkpoint_id} saved to filesystem")
        except Exception as e:
            logger.error(f"Failed to save checkpoint to filesystem: {e}")

        # Add to operation checkpoints list
        operation.checkpoints.append(checkpoint)
        operation.status = OperationStatus.CHECKPOINT_SAVED

        return checkpoint_id

    async def load_checkpoint(
        self, checkpoint_id: str
    ) -> Optional[OperationCheckpoint]:
        """Load operation checkpoint"""

        # Try Redis first
        if self.redis_client:
            try:
                data = await self.redis_client.get(f"checkpoint:{checkpoint_id}")
                if data:
                    checkpoint = pickle.loads(data)
                    logger.info(f"Checkpoint {checkpoint_id} loaded from Redis")
                    return checkpoint
            except Exception as e:
                logger.warning(f"Failed to load checkpoint from Redis: {e}")

        # Try filesystem
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_id}.pkl"
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file, "rb") as f:
                    checkpoint = pickle.load(f)
                logger.info(f"Checkpoint {checkpoint_id} loaded from filesystem")
                return checkpoint
            except Exception as e:
                logger.error(f"Failed to load checkpoint from filesystem: {e}")

        return None

    async def list_checkpoints(self, operation_id: str) -> List[OperationCheckpoint]:
        """List all checkpoints for an operation"""

        checkpoints = []

        # Search Redis
        if self.redis_client:
            try:
                keys = await self.redis_client.keys(
                    f"checkpoint:checkpoint_{operation_id}_*"
                )
                for key in keys:
                    data = await self.redis_client.get(key)
                    if data:
                        checkpoint = pickle.loads(data)
                        checkpoints.append(checkpoint)
            except Exception as e:
                logger.warning(f"Failed to list Redis checkpoints: {e}")

        # Search filesystem
        for checkpoint_file in self.checkpoint_dir.glob(
            f"checkpoint_{operation_id}_*.pkl"
        ):
            try:
                with open(checkpoint_file, "rb") as f:
                    checkpoint = pickle.load(f)
                    checkpoints.append(checkpoint)
            except Exception as e:
                logger.warning(f"Failed to load checkpoint {checkpoint_file}: {e}")

        # Sort by timestamp
        checkpoints.sort(key=lambda x: x.timestamp)
        return checkpoints


class OperationProgressTracker:
    """Real-time progress tracking with WebSocket broadcasting"""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.progress_callbacks: Dict[str, List[Callable]] = {}
        self.websocket_connections: Dict[str, List] = {}

    def subscribe_to_progress(self, operation_id: str, callback: Callable):
        """Subscribe to progress updates"""
        if operation_id not in self.progress_callbacks:
            self.progress_callbacks[operation_id] = []
        self.progress_callbacks[operation_id].append(callback)

    async def update_progress(
        self,
        operation: LongRunningOperation,
        current_step: str,
        processed_items: int,
        total_items: Optional[int] = None,
        performance_metrics: Optional[Dict] = None,
        status_message: str = "",
    ):
        """Update operation progress"""

        if total_items is not None:
            operation.progress.total_items = total_items

        operation.progress.current_step = current_step
        operation.progress.processed_items = processed_items
        operation.progress.status_message = status_message

        # Calculate progress percentage
        if operation.progress.total_items > 0:
            operation.progress.progress_percentage = min(
                (processed_items / operation.progress.total_items) * 100, 100.0
            )

        # Estimate completion time
        if operation.started_at and operation.progress.progress_percentage > 0:
            elapsed = datetime.now() - operation.started_at
            total_estimated = elapsed / (operation.progress.progress_percentage / 100)
            remaining = total_estimated - elapsed
            operation.progress.estimated_completion = datetime.now() + remaining

        # Update performance metrics
        if performance_metrics:
            operation.progress.performance_metrics.update(performance_metrics)

        # Broadcast progress update
        await self._broadcast_progress_update(operation)

    async def _broadcast_progress_update(self, operation: LongRunningOperation):
        """Broadcast progress update to subscribers"""

        progress_data = {
            "operation_id": operation.operation_id,
            "operation_type": operation.operation_type.value,
            "status": operation.status.value,
            "progress": asdict(operation.progress),
            "timestamp": datetime.now().isoformat(),
        }

        # Call registered callbacks
        for callback in self.progress_callbacks.get(operation.operation_id, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(progress_data)
                else:
                    callback(progress_data)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

        # Store in Redis for real-time access
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    f"progress:{operation.operation_id}",
                    3600,  # 1 hour TTL
                    json.dumps(progress_data, default=str),
                )
            except Exception as e:
                logger.warning(f"Failed to store progress in Redis: {e}")


class LongRunningOperationManager:
    """Main manager for long-running operations"""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.operations: Dict[str, LongRunningOperation] = {}
        self.checkpoint_manager = OperationCheckpointManager(redis_client)
        self.progress_tracker = OperationProgressTracker(redis_client)
        self.timeout_config = LongRunningTimeoutConfig()
        self.operation_tasks: Dict[str, asyncio.Task] = {}

        # Background task management
        self.background_queue = asyncio.Queue()
        self.max_concurrent_operations = 3
        self.active_operations = 0

        # Start background processor
        self._background_processor_task = None

    async def start_background_processor(self):
        """Start the background operation processor"""
        if self._background_processor_task is None:
            self._background_processor_task = asyncio.create_task(
                self._background_processor()
            )

    async def stop_background_processor(self):
        """Stop the background operation processor"""
        if self._background_processor_task:
            self._background_processor_task.cancel()
            try:
                await self._background_processor_task
            except asyncio.CancelledError:
                pass
            self._background_processor_task = None

    async def _background_processor(self):
        """Process background operations with concurrency control"""
        while True:
            try:
                # Wait for available slot
                while self.active_operations >= self.max_concurrent_operations:
                    await asyncio.sleep(1)

                # Get next operation from queue
                operation_id = await self.background_queue.get()
                operation = self.operations.get(operation_id)

                if operation and operation.status == OperationStatus.QUEUED:
                    self.active_operations += 1
                    task = asyncio.create_task(
                        self._execute_operation_with_monitoring(operation)
                    )
                    self.operation_tasks[operation_id] = task

                    # Clean up when done
                    task.add_done_callback(
                        lambda t: setattr(
                            self, "active_operations", self.active_operations - 1
                        )
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Background processor error: {e}")
                await asyncio.sleep(5)

    async def create_operation(
        self,
        operation_type: OperationType,
        name: str,
        description: str,
        operation_function: Callable,
        priority: OperationPriority = OperationPriority.NORMAL,
        estimated_items: int = 1,
        context: Optional[Dict[str, Any]] = None,
        execute_immediately: bool = False,
    ) -> str:
        """Create a new long-running operation"""

        operation_id = str(uuid.uuid4())
        timeout_config = self.timeout_config.get_timeout_config(
            operation_type, estimated_items
        )

        operation = LongRunningOperation(
            operation_id=operation_id,
            operation_type=operation_type,
            name=name,
            description=description,
            priority=priority,
            status=OperationStatus.QUEUED,
            created_at=datetime.now(),
            timeout_config=timeout_config,
            context=context or {},
        )

        # Store operation function
        operation.context["operation_function"] = operation_function

        self.operations[operation_id] = operation

        if execute_immediately:
            await self.execute_operation(operation_id)
        else:
            await self.background_queue.put(operation_id)

        logger.info(f"Created operation {operation_id}: {name}")
        return operation_id

    async def execute_operation(self, operation_id: str) -> Any:
        """Execute operation immediately (not in background)"""

        operation = self.operations.get(operation_id)
        if not operation:
            raise ValueError(f"Operation {operation_id} not found")

        return await self._execute_operation_with_monitoring(operation)

    async def _execute_operation_with_monitoring(
        self, operation: LongRunningOperation
    ) -> Any:
        """Execute operation with full monitoring and checkpoint support"""

        operation.status = OperationStatus.RUNNING
        operation.started_at = datetime.now()

        timeout_seconds = operation.timeout_config["calculated_timeout"]
        checkpoint_interval = operation.timeout_config["checkpoint_interval"]
        progress_interval = operation.timeout_config["progress_report_interval"]

        logger.info(
            f"Starting operation {operation.operation_id} with {timeout_seconds}s timeout"
        )

        try:
            # Set up checkpoint and progress tasks
            checkpoint_task = asyncio.create_task(
                self._periodic_checkpoint(operation, checkpoint_interval)
            )
            progress_task = asyncio.create_task(
                self._periodic_progress_report(operation, progress_interval)
            )

            # Execute the actual operation
            operation_function = operation.context["operation_function"]

            # Create enhanced operation context
            enhanced_context = OperationExecutionContext(
                operation=operation,
                progress_tracker=self.progress_tracker,
                checkpoint_manager=self.checkpoint_manager,
                logger=logger,
            )

            # Execute with timeout
            result = await asyncio.wait_for(
                self._execute_with_context(operation_function, enhanced_context),
                timeout=timeout_seconds,
            )

            # Clean up monitoring tasks
            checkpoint_task.cancel()
            progress_task.cancel()

            # Mark as completed
            operation.status = OperationStatus.COMPLETED
            operation.completed_at = datetime.now()
            operation.result = result

            await self.progress_tracker.update_progress(
                operation,
                "Completed",
                operation.progress.total_items,
                operation.progress.total_items,
                status_message="Operation completed successfully",
            )

            logger.info(f"Operation {operation.operation_id} completed successfully")
            return result

        except asyncio.TimeoutError:
            operation.status = OperationStatus.TIMEOUT
            operation.error_info = (
                f"Operation timed out after {timeout_seconds} seconds"
            )

            # Save final checkpoint before timeout
            await self.checkpoint_manager.save_checkpoint(
                operation,
                {"timeout_occurred": True},
                operation.context,
                "timeout_recovery",
            )

            logger.warning(f"Operation {operation.operation_id} timed out")
            raise

        except Exception as e:
            operation.status = OperationStatus.FAILED
            operation.error_info = str(e)

            # Save checkpoint for potential recovery
            await self.checkpoint_manager.save_checkpoint(
                operation,
                {"error_occurred": True, "error_details": str(e)},
                operation.context,
                "error_recovery",
            )

            logger.error(f"Operation {operation.operation_id} failed: {e}")
            raise

        finally:
            # Clean up
            if operation.operation_id in self.operation_tasks:
                del self.operation_tasks[operation.operation_id]

    async def _execute_with_context(
        self, operation_function: Callable, context: "OperationExecutionContext"
    ) -> Any:
        """Execute operation function with enhanced context"""

        if asyncio.iscoroutinefunction(operation_function):
            return await operation_function(context)
        else:
            return await asyncio.to_thread(operation_function, context)

    async def _periodic_checkpoint(
        self, operation: LongRunningOperation, interval: int
    ):
        """Periodic checkpoint saving"""
        while True:
            try:
                await asyncio.sleep(interval)
                if operation.status == OperationStatus.RUNNING:
                    await self.checkpoint_manager.save_checkpoint(
                        operation,
                        operation.context.get("intermediate_results", {}),
                        operation.context,
                        operation.progress.current_step,
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Checkpoint save failed: {e}")

    async def _periodic_progress_report(
        self, operation: LongRunningOperation, interval: int
    ):
        """Periodic progress reporting"""
        while True:
            try:
                await asyncio.sleep(interval)
                if operation.status == OperationStatus.RUNNING:
                    logger.info(
                        f"Operation {operation.operation_id}: "
                        f"{operation.progress.progress_percentage:.1f}% "
                        f"({operation.progress.processed_items}/{operation.progress.total_items}) "
                        f"- {operation.progress.current_step}"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Progress report failed: {e}")

    async def resume_operation(self, checkpoint_id: str) -> str:
        """Resume operation from checkpoint"""

        checkpoint = await self.checkpoint_manager.load_checkpoint(checkpoint_id)
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        # Create new operation for resume
        new_operation_id = str(uuid.uuid4())

        # Find original operation or create new one
        original_operation = self.operations.get(checkpoint.operation_id)
        if not original_operation:
            raise ValueError(f"Original operation {checkpoint.operation_id} not found")

        # Create resumed operation
        resumed_operation = LongRunningOperation(
            operation_id=new_operation_id,
            operation_type=OperationType(checkpoint.metadata["operation_type"]),
            name=f"Resumed: {checkpoint.metadata['operation_name']}",
            description=f"Resumed from checkpoint {checkpoint_id}",
            priority=original_operation.priority,
            status=OperationStatus.RESUMING,
            created_at=datetime.now(),
            timeout_config=original_operation.timeout_config,
            context={
                **original_operation.context,
                **checkpoint.context_data,
                "resume_checkpoint": checkpoint,
                "resume_from": checkpoint.next_step,
            },
        )

        # Restore progress
        resumed_operation.progress.progress_percentage = checkpoint.progress_percentage
        resumed_operation.progress.processed_items = checkpoint.processed_items
        resumed_operation.progress.total_items = checkpoint.total_items

        self.operations[new_operation_id] = resumed_operation

        logger.info(
            f"Resuming operation from checkpoint {checkpoint_id} as {new_operation_id}"
        )

        # Execute resumed operation
        await self.background_queue.put(new_operation_id)
        return new_operation_id

    def get_operation(self, operation_id: str) -> Optional[LongRunningOperation]:
        """Get operation by ID"""
        return self.operations.get(operation_id)

    def list_operations(
        self,
        status_filter: Optional[OperationStatus] = None,
        operation_type_filter: Optional[OperationType] = None,
    ) -> List[LongRunningOperation]:
        """List operations with optional filtering"""

        operations = list(self.operations.values())

        if status_filter:
            operations = [op for op in operations if op.status == status_filter]

        if operation_type_filter:
            operations = [
                op for op in operations if op.operation_type == operation_type_filter
            ]

        # Sort by priority and creation time
        operations.sort(key=lambda x: (x.priority.value, x.created_at), reverse=True)
        return operations

    async def cancel_operation(self, operation_id: str) -> bool:
        """Cancel a running operation"""

        operation = self.operations.get(operation_id)
        if not operation:
            return False

        if operation_id in self.operation_tasks:
            task = self.operation_tasks[operation_id]
            task.cancel()
            del self.operation_tasks[operation_id]

        operation.status = OperationStatus.CANCELLED
        operation.completed_at = datetime.now()

        logger.info(f"Cancelled operation {operation_id}")
        return True


@dataclass
class OperationExecutionContext:
    """Enhanced execution context provided to operation functions"""

    operation: LongRunningOperation
    progress_tracker: OperationProgressTracker
    checkpoint_manager: OperationCheckpointManager
    logger: logging.Logger

    async def update_progress(
        self,
        step: str,
        processed: int,
        total: Optional[int] = None,
        metrics: Optional[Dict] = None,
        message: str = "",
    ):
        """Update operation progress"""
        await self.progress_tracker.update_progress(
            self.operation, step, processed, total, metrics, message
        )

    async def save_checkpoint(
        self,
        intermediate_results: Dict[str, Any],
        next_step: str,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save operation checkpoint"""
        return await self.checkpoint_manager.save_checkpoint(
            self.operation, intermediate_results, context_data or {}, next_step
        )

    def should_resume(self) -> bool:
        """Check if this is a resumed operation"""
        return "resume_checkpoint" in self.operation.context

    def get_resume_data(self) -> Optional[OperationCheckpoint]:
        """Get resume checkpoint data"""
        return self.operation.context.get("resume_checkpoint")


# Convenience functions for common operations
async def execute_codebase_indexing(
    codebase_path: str,
    manager: LongRunningOperationManager,
    file_patterns: Optional[List[str]] = None,
) -> str:
    """Execute codebase indexing operation"""

    async def indexing_operation(context: OperationExecutionContext):
        """Actual indexing implementation"""

        import fnmatch
        from pathlib import Path

        path = Path(codebase_path)
        patterns = file_patterns or ["*.py", "*.js", "*.vue", "*.ts", "*.jsx", "*.tsx"]

        # Count total files first
        all_files = []
        for pattern in patterns:
            all_files.extend(path.rglob(pattern))

        total_files = len(all_files)
        await context.update_progress("Scanning files", 0, total_files)

        results = []
        for i, file_path in enumerate(all_files):
            try:
                # Simulate file processing
                await asyncio.sleep(0.1)  # Simulate processing time

                # Process file (placeholder)
                file_info = {
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                    "indexed_at": datetime.now().isoformat(),
                }
                results.append(file_info)

                # Update progress
                await context.update_progress(
                    f"Processing {file_path.name}",
                    i + 1,
                    total_files,
                    {
                        "files_per_second": (i + 1)
                        / max(1, time.time() - context.operation.started_at.timestamp())
                    },
                    f"Indexed {i + 1} of {total_files} files",
                )

                # Save checkpoint every 100 files
                if (i + 1) % 100 == 0:
                    await context.save_checkpoint(
                        {"processed_files": results}, f"file_{i + 1}"
                    )

            except Exception as e:
                context.logger.warning(f"Failed to process {file_path}: {e}")

        return {
            "total_files_processed": len(results),
            "files": results,
            "completed_at": datetime.now().isoformat(),
        }

    return await manager.create_operation(
        OperationType.CODEBASE_INDEXING,
        f"Index codebase: {codebase_path}",
        f"Index all files in {codebase_path} matching patterns {file_patterns}",
        indexing_operation,
        OperationPriority.NORMAL,
        estimated_items=1000,  # Estimate
        execute_immediately=False,
    )


async def execute_comprehensive_test_suite(
    test_suite_path: str,
    manager: LongRunningOperationManager,
    test_patterns: Optional[List[str]] = None,
) -> str:
    """Execute comprehensive test suite operation"""

    async def test_suite_operation(context: OperationExecutionContext):
        """Actual test suite implementation"""

        import subprocess
        from pathlib import Path

        path = Path(test_suite_path)
        patterns = test_patterns or ["test_*.py", "*_test.py"]

        # Find all test files
        test_files = []
        for pattern in patterns:
            test_files.extend(path.rglob(pattern))

        total_tests = len(test_files)
        await context.update_progress("Initializing test suite", 0, total_tests)

        results = []
        passed = 0
        failed = 0

        for i, test_file in enumerate(test_files):
            try:
                await context.update_progress(
                    f"Running {test_file.name}",
                    i,
                    total_tests,
                    {"passed": passed, "failed": failed},
                    f"Test {i + 1} of {total_tests}: {test_file.name}",
                )

                # Run test (placeholder - would use actual test runner)
                await asyncio.sleep(0.5)  # Simulate test execution

                # Simulate test result
                import random

                test_passed = random.random() > 0.1  # 90% pass rate

                test_result = {
                    "file": str(test_file),
                    "status": "PASS" if test_passed else "FAIL",
                    "duration": 0.5,
                    "timestamp": datetime.now().isoformat(),
                }
                results.append(test_result)

                if test_passed:
                    passed += 1
                else:
                    failed += 1

                # Save checkpoint every 10 tests
                if (i + 1) % 10 == 0:
                    await context.save_checkpoint(
                        {"test_results": results, "passed": passed, "failed": failed},
                        f"test_{i + 1}",
                    )

            except Exception as e:
                context.logger.error(f"Failed to run test {test_file}: {e}")
                failed += 1

        return {
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
            "results": results,
            "success_rate": (passed / total_tests) * 100 if total_tests > 0 else 0,
        }

    return await manager.create_operation(
        OperationType.COMPREHENSIVE_TEST_SUITE,
        f"Comprehensive test suite: {test_suite_path}",
        f"Run all tests in {test_suite_path}",
        test_suite_operation,
        OperationPriority.HIGH,
        estimated_items=100,  # Estimate
        execute_immediately=False,
    )


# Example usage and testing
if __name__ == "__main__":

    async def example_usage():
        """Example usage of the long-running operations framework"""

        # Initialize manager
        manager = LongRunningOperationManager()
        await manager.start_background_processor()

        try:
            # Start codebase indexing
            indexing_op_id = await execute_codebase_indexing(
                str(PATH.PROJECT_ROOT / "src"), manager, ["*.py"]
            )

            # Start test suite
            test_op_id = await execute_comprehensive_test_suite(
                str(PATH.TESTS_DIR), manager, ["test_*.py"]
            )

            # Monitor operations
            while True:
                indexing_op = manager.get_operation(indexing_op_id)
                test_op = manager.get_operation(test_op_id)

                print(
                    f"Indexing: {indexing_op.status.value} - {indexing_op.progress.progress_percentage:.1f}%"
                )
                print(
                    f"Testing: {test_op.status.value} - {test_op.progress.progress_percentage:.1f}%"
                )

                if indexing_op.status in [
                    OperationStatus.COMPLETED,
                    OperationStatus.FAILED,
                ] and test_op.status in [
                    OperationStatus.COMPLETED,
                    OperationStatus.FAILED,
                ]:
                    break

                await asyncio.sleep(5)

            print("All operations completed!")

        finally:
            await manager.stop_background_processor()

    # Run example
    asyncio.run(example_usage())
