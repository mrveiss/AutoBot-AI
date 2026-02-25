# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Async Cancellation Token System - Replaces asyncio.wait_for() timeouts
Provides proper cancellation patterns without arbitrary time limits
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

from constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)


class CancellationReason(Enum):
    """Reasons for operation cancellation"""

    USER_REQUESTED = "user_requested"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    DEPENDENCY_FAILED = "dependency_failed"
    CIRCUIT_BREAKER = "circuit_breaker"
    GRACEFUL_SHUTDOWN = "graceful_shutdown"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"


@dataclass
class CancellationToken:
    """Cancellation token that can be checked for cancellation requests"""

    def __init__(self):
        """Initialize cancellation token with default state and empty callbacks."""
        self.is_cancelled = False
        self.cancellation_reason: Optional[CancellationReason] = None
        self.cancellation_message: str = ""
        self.cancellation_time: Optional[float] = None
        self._callbacks: list = []

    def cancel(self, reason: CancellationReason, message: str = ""):
        """Cancel the operation with specified reason"""
        if self.is_cancelled:
            return  # Already cancelled

        self.is_cancelled = True
        self.cancellation_reason = reason
        self.cancellation_message = message
        self.cancellation_time = time.time()

        logger.info("🚫 Operation cancelled: %s - %s", reason.value, message)

        # Execute cancellation callbacks
        for callback in self._callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error("Error in cancellation callback: %s", e)

    def add_cancellation_callback(
        self, callback: Callable[["CancellationToken"], None]
    ):
        """Add callback to execute when cancelled"""
        self._callbacks.append(callback)

    def raise_if_cancelled(self):
        """Raise CancelledError if operation is cancelled"""
        if self.is_cancelled:
            error = OperationCancelledException(
                f"Operation cancelled: {self.cancellation_reason.value} - {self.cancellation_message}"
            )
            error.reason = self.cancellation_reason
            error.message = self.cancellation_message
            raise error


class OperationCancelledException(Exception):
    """Exception raised when operation is cancelled via token"""

    def __init__(self, message: str):
        """Initialize exception with message and optional cancellation reason."""
        super().__init__(message)
        self.reason: Optional[CancellationReason] = None
        self.message: str = message


class ResourceMonitor:
    """Monitor resource availability to trigger cancellation"""

    def __init__(self):
        """Initialize resource monitor with default availability states."""
        self.redis_available = True
        self.llm_available = True
        self.kb_available = True
        self.last_check_time = 0
        self.check_interval = 1.0  # Check every second

    async def check_resources(self) -> Dict[str, bool]:
        """Check resource availability immediately"""
        current_time = time.time()

        # Only check if interval has passed
        if current_time - self.last_check_time < self.check_interval:
            return {
                "redis": self.redis_available,
                "llm": self.llm_available,
                "kb": self.kb_available,
            }

        self.last_check_time = current_time

        # Quick Redis check
        try:
            from utils.redis_immediate_test import redis_circuit_breaker

            self.redis_available = not redis_circuit_breaker.is_circuit_open
        except Exception:
            self.redis_available = False

        # Quick LLM check
        try:
            pass

            # Just check if interface can be created (no actual request)
            self.llm_available = (
                True  # Assume available unless circuit breaker says otherwise
            )
        except Exception:
            self.llm_available = False

        # Quick KB check
        try:
            # Check if KB is initialized (no heavy operations)
            self.kb_available = True  # Assume available unless specific issues
        except Exception:
            self.kb_available = False

        return {
            "redis": self.redis_available,
            "llm": self.llm_available,
            "kb": self.kb_available,
        }


# Global resource monitor
resource_monitor = ResourceMonitor()


class SmartCancellationHandler:
    """Smart cancellation handler that monitors conditions and cancels appropriately"""

    def __init__(self):
        """Initialize handler with empty token registry and monitor state."""
        self.active_tokens: Dict[str, CancellationToken] = {}
        self.monitor_task: Optional[asyncio.Task] = None
        self._shutdown = False

    def create_token(self, operation_id: str) -> CancellationToken:
        """Create a new cancellation token for an operation"""
        token = CancellationToken()
        self.active_tokens[operation_id] = token

        # Start monitoring if not already running
        if not self.monitor_task or self.monitor_task.done():
            self.monitor_task = asyncio.create_task(self._monitor_conditions())

        return token

    def remove_token(self, operation_id: str):
        """Remove completed operation token"""
        if operation_id in self.active_tokens:
            del self.active_tokens[operation_id]

    async def _monitor_conditions(self):
        """Monitor system conditions and cancel operations as needed"""
        while not self._shutdown and self.active_tokens:
            try:
                # Check resource availability
                resources = await resource_monitor.check_resources()

                # Cancel operations if critical resources unavailable
                for operation_id, token in list(self.active_tokens.items()):
                    if token.is_cancelled:
                        continue

                    # Cache operation_id.lower() to avoid repeated computation (Issue #323)
                    operation_id_lower = operation_id.lower()

                    # Cancel if Redis is unavailable and operation needs it
                    if not resources["redis"] and "redis" in operation_id_lower:
                        token.cancel(
                            CancellationReason.RESOURCE_UNAVAILABLE,
                            "Redis service unavailable",
                        )

                    # Cancel if LLM is unavailable and operation needs it
                    if not resources["llm"] and (
                        "llm" in operation_id_lower or "chat" in operation_id_lower
                    ):
                        token.cancel(
                            CancellationReason.RESOURCE_UNAVAILABLE,
                            "LLM service unavailable",
                        )

                    # Cancel if KB is unavailable and operation needs it
                    if not resources["kb"] and "knowledge" in operation_id_lower:
                        token.cancel(
                            CancellationReason.RESOURCE_UNAVAILABLE,
                            "Knowledge base unavailable",
                        )

                await asyncio.sleep(
                    TimingConstants.STANDARD_DELAY
                )  # Check every second

            except Exception as e:
                logger.error("Error in condition monitoring: %s", e)
                await asyncio.sleep(
                    TimingConstants.ERROR_RECOVERY_DELAY
                )  # Wait longer on error

    async def shutdown(self):
        """Graceful shutdown - cancel all operations"""
        self._shutdown = True

        for operation_id, token in self.active_tokens.items():
            if not token.is_cancelled:
                token.cancel(
                    CancellationReason.GRACEFUL_SHUTDOWN, "System shutting down"
                )

        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                logger.debug("Cancellation monitor task stopped")


# Global cancellation handler
cancellation_handler = SmartCancellationHandler()


async def execute_with_cancellation(
    operation: Callable, operation_id: str, *args, **kwargs
) -> Any:
    """
    Execute operation with smart cancellation instead of timeouts.
    Operations complete naturally or are cancelled due to real conditions.
    """

    # Create cancellation token
    token = cancellation_handler.create_token(operation_id)

    try:
        # Execute operation with cancellation checking
        if asyncio.iscoroutinefunction(operation):
            result = await _execute_async_with_cancellation(
                operation, token, *args, **kwargs
            )
        else:
            result = await _execute_sync_with_cancellation(
                operation, token, *args, **kwargs
            )

        logger.info("✅ Operation completed successfully: %s", operation_id)
        return result

    except OperationCancelledException as e:
        logger.warning("⚠️ Operation cancelled: %s - %s", operation_id, e.message)
        raise

    except Exception as e:
        logger.error("❌ Operation failed: %s - %s", operation_id, str(e))
        raise

    finally:
        # Cleanup
        cancellation_handler.remove_token(operation_id)


async def _execute_async_with_cancellation(
    operation, token: CancellationToken, *args, **kwargs
):
    """Execute async operation with cancellation checks"""

    # Create task for the operation
    operation_task = asyncio.create_task(operation(*args, **kwargs))

    # Monitor for cancellation
    while not operation_task.done():
        # Check if cancelled
        if token.is_cancelled:
            operation_task.cancel()
            try:
                await operation_task
            except asyncio.CancelledError:
                logger.debug("Operation task cancelled via token")
            token.raise_if_cancelled()

        # Brief sleep to allow operation to progress
        try:
            await asyncio.wait_for(asyncio.shield(operation_task), timeout=0.1)
            break  # Operation completed
        except asyncio.TimeoutError:
            continue  # Keep monitoring

    return await operation_task


async def _execute_sync_with_cancellation(
    operation, token: CancellationToken, *args, **kwargs
):
    """Execute sync operation with cancellation checks"""

    # Run in thread pool with periodic cancellation checks
    loop = asyncio.get_event_loop()

    # Create a future that will be resolved in the thread
    future = loop.create_future()

    def run_with_checks():
        """Execute operation in thread and set future result on completion."""
        try:
            # Execute operation
            result = operation(*args, **kwargs)
            if not future.done():
                loop.call_soon_threadsafe(future.set_result, result)
        except Exception as e:
            if not future.done():
                loop.call_soon_threadsafe(future.set_exception, e)

    # Start operation in thread
    executor = loop.run_in_executor(None, run_with_checks)

    # Monitor for completion or cancellation
    while not future.done():
        if token.is_cancelled:
            executor.cancel()  # Cancel thread execution
            token.raise_if_cancelled()

        # Brief wait
        try:
            await asyncio.wait_for(asyncio.shield(future), timeout=0.1)
            break
        except asyncio.TimeoutError:
            continue

    return await future


# Convenience functions for common operations


async def execute_llm_request_with_cancellation(
    llm_function, operation_id: str, *args, **kwargs
):
    """Execute LLM request with smart cancellation"""
    return await execute_with_cancellation(
        llm_function, f"llm_{operation_id}", *args, **kwargs
    )


async def execute_kb_search_with_cancellation(
    kb_function, operation_id: str, *args, **kwargs
):
    """Execute knowledge base search with smart cancellation"""
    return await execute_with_cancellation(
        kb_function, f"knowledge_{operation_id}", *args, **kwargs
    )


async def execute_redis_operation_with_cancellation(
    redis_function, operation_id: str, *args, **kwargs
):
    """Execute Redis operation with smart cancellation"""
    return await execute_with_cancellation(
        redis_function, f"redis_{operation_id}", *args, **kwargs
    )


# Context manager for automatic token management
class CancellationContext:
    """Context manager for cancellation token lifecycle"""

    def __init__(self, operation_id: str):
        """Initialize context with operation identifier."""
        self.operation_id = operation_id
        self.token: Optional[CancellationToken] = None

    async def __aenter__(self) -> CancellationToken:
        """Enter context and create cancellation token for the operation."""
        self.token = cancellation_handler.create_token(self.operation_id)
        return self.token

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context and cleanup cancellation token."""
        if self.token:
            cancellation_handler.remove_token(self.operation_id)
