# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Long-Running Operation Manager

Issue #381: Extracted from long_running_operations_framework.py god class refactoring.
Main manager for long-running operations with background processing.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.constants.threshold_constants import TimingConstants

from .checkpoint_manager import OperationCheckpointManager
from .progress_tracker import OperationProgressTracker
from .types import (
    LongRunningOperation,
    OperationCheckpoint,
    OperationPriority,
    OperationStatus,
    OperationType,
)

logger = logging.getLogger(__name__)


@dataclass
class OperationExecutionContext:
    """Enhanced execution context provided to operation functions."""

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
    ) -> None:
        """Update operation progress."""
        total_items = total if total is not None else self.operation.progress.total_items
        await self.progress_tracker.update_progress(
            self.operation,
            current_step=step,
            progress_percent=(processed / total_items * 100) if total_items > 0 else 0,
            items_processed=processed,
            total_items=total_items,
            details={"message": message, "metrics": metrics or {}},
        )

    async def save_checkpoint(
        self,
        intermediate_results: Dict[str, Any],
        next_step: str,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save operation checkpoint."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        checkpoint_id = f"chk_{self.operation.operation_id}_{timestamp}"
        await self.checkpoint_manager.save_checkpoint(
            operation_id=self.operation.operation_id,
            checkpoint_id=checkpoint_id,
            progress_percent=self.operation.progress.progress_percent,
            state_data={
                "intermediate_results": intermediate_results,
                "next_step": next_step,
                **(context_data or {}),
            },
            metadata={
                "operation_type": self.operation.operation_type.value,
                "operation_name": self.operation.name,
            },
        )
        return checkpoint_id

    def should_resume(self) -> bool:
        """Check if this is a resumed operation."""
        return "resume_checkpoint" in self.operation.metadata

    def get_resume_data(self) -> Optional[OperationCheckpoint]:
        """Get resume checkpoint data."""
        return self.operation.metadata.get("resume_checkpoint")


class LongRunningOperationManager:
    """Main manager for long-running operations."""

    def __init__(self, redis_client=None):
        """Initialize operation manager with checkpoint and progress tracking."""
        self.redis_client = redis_client
        self.operations: Dict[str, LongRunningOperation] = {}
        self.checkpoint_manager = OperationCheckpointManager(redis_client)
        self.progress_tracker = OperationProgressTracker(redis_client)
        self.operation_tasks: Dict[str, asyncio.Task] = {}

        # Background task management
        self.background_queue: asyncio.Queue = asyncio.Queue()
        self.max_concurrent_operations = 3
        self.active_operations = 0

        # Lock for thread-safe access
        self._lock = asyncio.Lock()

        # Background processor
        self._background_processor_task = None

    async def start_background_processor(self) -> None:
        """Start the background operation processor."""
        if self._background_processor_task is None:
            self._background_processor_task = asyncio.create_task(
                self._background_processor()
            )

    async def stop_background_processor(self) -> None:
        """Stop the background operation processor."""
        if self._background_processor_task:
            self._background_processor_task.cancel()
            try:
                await self._background_processor_task
            except asyncio.CancelledError:
                logger.debug("Background processor cancelled")
            self._background_processor_task = None

    async def _background_processor(self) -> None:
        """Process background operations with concurrency control."""
        while True:
            try:
                # Wait for available slot
                while True:
                    async with self._lock:
                        if self.active_operations < self.max_concurrent_operations:
                            break
                    await asyncio.sleep(TimingConstants.STANDARD_DELAY)

                # Get next operation
                operation_id = await self.background_queue.get()

                async with self._lock:
                    operation = self.operations.get(operation_id)

                if operation and operation.status == OperationStatus.QUEUED:
                    async with self._lock:
                        self.active_operations += 1

                    task = asyncio.create_task(
                        self._execute_operation_with_monitoring(operation)
                    )

                    async with self._lock:
                        self.operation_tasks[operation_id] = task

                    # Cleanup callback
                    def make_done_callback(manager):
                        async def decrement():
                            async with manager._lock:
                                manager.active_operations -= 1

                        def callback(t):
                            asyncio.create_task(decrement())

                        return callback

                    task.add_done_callback(make_done_callback(self))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Background processor error: %s", e)
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)

    async def create_operation(
        self,
        operation_type: OperationType,
        name: str,
        description: str,
        operation_function: Callable,
        priority: OperationPriority = OperationPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
        execute_immediately: bool = False,
    ) -> str:
        """Create a new long-running operation."""
        operation_id = str(uuid.uuid4())

        operation = LongRunningOperation(
            operation_id=operation_id,
            operation_type=operation_type,
            name=name,
            description=description,
            priority=priority,
            status=OperationStatus.QUEUED,
            metadata=metadata or {},
            _operation_function=operation_function,
        )

        async with self._lock:
            self.operations[operation_id] = operation

        if execute_immediately:
            await self.execute_operation(operation_id)
        else:
            await self.background_queue.put(operation_id)

        logger.info("Created operation %s: %s", operation_id, name)
        return operation_id

    async def execute_operation(self, operation_id: str) -> Any:
        """Execute operation immediately (not in background)."""
        async with self._lock:
            operation = self.operations.get(operation_id)
        if not operation:
            raise ValueError(f"Operation {operation_id} not found")

        return await self._execute_operation_with_monitoring(operation)

    async def _execute_operation_with_monitoring(
        self, operation: LongRunningOperation
    ) -> Any:
        """Execute operation with monitoring and checkpoint support."""
        operation.start_execution()

        timeout_seconds = operation.get_timeout_seconds()
        checkpoint_interval = operation.get_checkpoint_interval()
        progress_interval = operation.get_progress_interval()

        logger.info(
            "Starting operation %s with %ds timeout",
            operation.operation_id,
            timeout_seconds,
        )

        try:
            # Set up periodic tasks
            checkpoint_task = asyncio.create_task(
                self._periodic_checkpoint(operation, checkpoint_interval)
            )
            progress_task = asyncio.create_task(
                self._periodic_progress_report(operation, progress_interval)
            )

            # Get operation function
            operation_function = operation.get_operation_function()

            # Create execution context
            context = OperationExecutionContext(
                operation=operation,
                progress_tracker=self.progress_tracker,
                checkpoint_manager=self.checkpoint_manager,
                logger=logger,
            )

            # Execute with timeout
            result = await asyncio.wait_for(
                self._execute_with_context(operation_function, context),
                timeout=timeout_seconds,
            )

            # Cleanup
            checkpoint_task.cancel()
            progress_task.cancel()

            operation.mark_completed(result)

            await self.progress_tracker.update_progress(
                operation,
                "Completed",
                100.0,
                operation.progress.total_items,
                operation.progress.total_items,
            )

            logger.info("Operation %s completed successfully", operation.operation_id)
            return result

        except asyncio.TimeoutError:
            operation.mark_timeout(timeout_seconds)
            logger.warning("Operation %s timed out", operation.operation_id)
            raise

        except Exception as e:
            operation.mark_failed(str(e))
            logger.error("Operation %s failed: %s", operation.operation_id, e)
            raise

        finally:
            async with self._lock:
                self.operation_tasks.pop(operation.operation_id, None)

    async def _execute_with_context(
        self, operation_function: Callable, context: OperationExecutionContext
    ) -> Any:
        """Execute operation function with context."""
        if asyncio.iscoroutinefunction(operation_function):
            return await operation_function(context)
        else:
            return await asyncio.to_thread(operation_function, context)

    async def _periodic_checkpoint(
        self, operation: LongRunningOperation, interval: float
    ) -> None:
        """Periodic checkpoint saving."""
        while True:
            try:
                await asyncio.sleep(interval)
                if operation.status == OperationStatus.RUNNING:
                    ts = int(datetime.now().timestamp())
                    checkpoint_id = f"periodic_{operation.operation_id}_{ts}"
                    await self.checkpoint_manager.save_checkpoint(
                        operation_id=operation.operation_id,
                        checkpoint_id=checkpoint_id,
                        progress_percent=operation.progress.progress_percent,
                        state_data={"step": operation.progress.current_step},
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Checkpoint save failed: %s", e)

    async def _periodic_progress_report(
        self, operation: LongRunningOperation, interval: float
    ) -> None:
        """Periodic progress reporting."""
        while True:
            try:
                await asyncio.sleep(interval)
                if operation.status == OperationStatus.RUNNING:
                    logger.info(
                        "Operation %s: %.1f%% (%d/%d) - %s",
                        operation.operation_id,
                        operation.progress.progress_percent,
                        operation.progress.items_processed,
                        operation.progress.total_items,
                        operation.progress.current_step,
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Progress report failed: %s", e)

    async def resume_operation(self, checkpoint_id: str) -> str:
        """Resume operation from checkpoint."""
        checkpoint = await self.checkpoint_manager.load_checkpoint(checkpoint_id)
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        async with self._lock:
            original_operation = self.operations.get(checkpoint.operation_id)
        if not original_operation:
            raise ValueError(f"Original operation {checkpoint.operation_id} not found")

        new_operation_id = str(uuid.uuid4())

        resumed_operation = LongRunningOperation(
            operation_id=new_operation_id,
            operation_type=original_operation.operation_type,
            name=f"Resumed: {original_operation.name}",
            description=f"Resumed from checkpoint {checkpoint_id}",
            priority=original_operation.priority,
            status=OperationStatus.RESUMING,
            metadata={
                **original_operation.metadata,
                "resume_checkpoint": checkpoint,
            },
            _operation_function=original_operation.get_operation_function(),
        )

        # Restore progress
        resumed_operation.progress.progress_percent = checkpoint.progress_percent

        async with self._lock:
            self.operations[new_operation_id] = resumed_operation

        logger.info(
            "Resuming operation from checkpoint %s as %s",
            checkpoint_id,
            new_operation_id,
        )

        await self.background_queue.put(new_operation_id)
        return new_operation_id

    async def get_operation(
        self, operation_id: str
    ) -> Optional[LongRunningOperation]:
        """Get operation by ID."""
        async with self._lock:
            return self.operations.get(operation_id)

    async def list_operations(
        self,
        status_filter: Optional[OperationStatus] = None,
        operation_type_filter: Optional[OperationType] = None,
    ) -> List[LongRunningOperation]:
        """List operations with optional filtering."""
        async with self._lock:
            operations = list(self.operations.values())

        if status_filter:
            operations = [op for op in operations if op.status == status_filter]

        if operation_type_filter:
            operations = [
                op for op in operations if op.operation_type == operation_type_filter
            ]

        operations.sort(key=lambda x: (x.priority.value, x.created_at), reverse=True)
        return operations

    async def cancel_operation(self, operation_id: str) -> bool:
        """Cancel a running operation."""
        async with self._lock:
            operation = self.operations.get(operation_id)
            if not operation:
                return False

            task = self.operation_tasks.get(operation_id)
            if task:
                task.cancel()
                del self.operation_tasks[operation_id]

        operation.mark_cancelled()
        logger.info("Cancelled operation %s", operation_id)
        return True
