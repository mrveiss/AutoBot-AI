# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Adaptive Timeout Handlers for AutoBot
Intelligent timeout management with adaptive behavior and fallback strategies
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional


logger = logging.getLogger(__name__)


class TimeoutCategory(Enum):
    """Categories of timeout operations for different optimization strategies"""

    USER_INTERACTION = "user_interaction"  # User permission, input requests
    SYSTEM_INSTALLATION = "system_installation"  # Package installations, system changes
    COMMAND_EXECUTION = "command_execution"  # Shell commands, system operations
    NETWORK_OPERATION = "network_operation"  # HTTP requests, API calls
    AI_PROCESSING = "ai_processing"  # LLM requests, AI computations
    FILE_OPERATION = "file_operation"  # File I/O, disk operations
    DATABASE_OPERATION = "database_operation"  # Redis, SQLite, ChromaDB operations


class AdaptiveTimeoutConfig:
    """Adaptive timeout configuration with intelligent defaults for different operation types"""

    # ADAPTIVE TIMEOUTS (Dynamically adjusted based on operation type)
    TIMEOUTS = {
        TimeoutCategory.USER_INTERACTION: {
            "default": 30.0,  # Was 600s (10min) → 30s
            "retry": 15.0,  # Retry attempts
            "warning": 20.0,  # Warning threshold
            "max_attempts": 2,  # Maximum retry attempts
        },
        TimeoutCategory.SYSTEM_INSTALLATION: {
            "default": 120.0,  # Was 600s (10min) → 2min for most packages
            "large_package": 300.0,  # 5min for large packages (docker, etc)
            "warning": 60.0,  # Warning threshold
            "background": True,  # Allow background execution
        },
        TimeoutCategory.COMMAND_EXECUTION: {
            "default": 60.0,  # Was 300s (5min) → 1min
            "interactive": 30.0,  # Interactive commands
            "batch": 120.0,  # Batch operations
            "warning": 30.0,  # Warning threshold
        },
        TimeoutCategory.NETWORK_OPERATION: {
            "default": 15.0,  # Network requests
            "upload": 60.0,  # File uploads
            "download": 120.0,  # Large downloads
            "api": 10.0,  # API calls
        },
        TimeoutCategory.AI_PROCESSING: {
            "default": 30.0,  # LLM requests
            "complex": 60.0,  # Complex processing
            "streaming": 5.0,  # Per-chunk timeout
            "warning": 20.0,  # Warning threshold
        },
        TimeoutCategory.FILE_OPERATION: {
            "default": 10.0,  # File I/O
            "large_file": 60.0,  # Large file operations
            "network_fs": 30.0,  # Network filesystem
        },
        TimeoutCategory.DATABASE_OPERATION: {
            "default": 5.0,  # Database queries
            "bulk": 30.0,  # Bulk operations
            "migration": 60.0,  # Database migrations
        },
    }

    @classmethod
    def get_timeout(
        cls,
        category: TimeoutCategory,
        operation_type: str = "default",
        fallback: float = 30.0,
    ) -> float:
        """Get adaptive timeout for operation"""
        try:
            return cls.TIMEOUTS[category].get(operation_type, fallback)
        except KeyError:
            logger.warning(
                f"Unknown timeout category: {category}, using fallback: {fallback}s"
            )
            return fallback


class AdaptiveTimeout:
    """
    Intelligent timeout handler with adaptive behavior and fallback strategies
    """

    def __init__(self, category: TimeoutCategory):
        """Initialize adaptive timeout handler for given category."""
        self.category = category
        self.config = AdaptiveTimeoutConfig()
        self.start_time = None
        self.warning_sent = False

    async def execute_with_intelligent_timeout(
        self,
        operation: Callable,
        operation_type: str = "default",
        context: Optional[Dict[str, Any]] = None,
        fallback_result: Any = None,
        background_allowed: bool = False,
    ) -> Any:
        """
        Execute operation with intelligent timeout handling

        Features:
        - Adaptive timeout based on operation type
        - Warning notifications before timeout
        - Graceful fallback handling
        - Background execution for long operations
        - Performance logging
        """
        self.start_time = time.time()
        timeout_duration = self.config.get_timeout(self.category, operation_type)
        warning_threshold = self.config.get_timeout(
            self.category, "warning", timeout_duration * 0.7
        )

        context_str = f" ({context})" if context else ""
        logger.info(
            f"Starting {self.category.value} operation{context_str} with {timeout_duration}s timeout"
        )

        try:
            # Create warning task
            warning_task = asyncio.create_task(
                self._send_timeout_warning(warning_threshold, operation_type)
            )

            # Execute main operation
            if asyncio.iscoroutinefunction(operation):
                result = await asyncio.wait_for(operation(), timeout=timeout_duration)
            else:
                # Run sync operation in thread pool
                result = await asyncio.wait_for(
                    asyncio.to_thread(operation), timeout=timeout_duration
                )

            # Cancel warning task if operation completed
            warning_task.cancel()

            elapsed = time.time() - self.start_time
            logger.info(
                f"Operation completed in {elapsed:.2f}s (timeout was {timeout_duration}s)"
            )

            return result

        except asyncio.TimeoutError:
            elapsed = time.time() - self.start_time
            warning_task.cancel()

            logger.warning(
                f"TIMEOUT OPTIMIZATION: {self.category.value} operation timed out "
                f"after {elapsed:.2f}s (limit: {timeout_duration}s){context_str}"
            )

            # Handle timeout based on category
            return await self._handle_timeout_fallback(
                operation, operation_type, elapsed, background_allowed, fallback_result
            )

        except Exception as e:
            elapsed = time.time() - self.start_time
            logger.error("Operation failed after %.2fs: %s", elapsed, e)
            return fallback_result

    async def _send_timeout_warning(
        self, warning_threshold: float, operation_type: str
    ):
        """Send warning before timeout occurs"""
        try:
            await asyncio.sleep(warning_threshold)
            if not self.warning_sent:
                self.warning_sent = True
                elapsed = time.time() - self.start_time
                logger.warning(
                    f"Performance warning: {self.category.value} operation ({operation_type}) "
                    f"running for {elapsed:.2f}s, may timeout soon"
                )
        except asyncio.CancelledError:
            pass  # Operation completed before warning

    async def _handle_timeout_fallback(
        self,
        operation: Callable,
        operation_type: str,
        elapsed_time: float,
        background_allowed: bool,
        fallback_result: Any,
    ) -> Any:
        """Handle timeout with intelligent fallback strategies"""

        if self.category == TimeoutCategory.SYSTEM_INSTALLATION and background_allowed:
            # For installations, offer background execution
            logger.info("Offering background installation execution...")
            return await self._handle_background_installation(operation, operation_type)

        elif self.category == TimeoutCategory.USER_INTERACTION:
            # For user interactions, try retry with notification
            return await self._handle_user_interaction_timeout(operation, elapsed_time)

        elif self.category == TimeoutCategory.COMMAND_EXECUTION:
            # For commands, try shorter timeout or background
            return await self._handle_command_timeout(
                operation, operation_type, background_allowed
            )

        else:
            # Generic fallback
            logger.info("Using fallback result for %s timeout", self.category.value)
            return fallback_result

    async def _handle_background_installation(
        self, operation: Callable, operation_type: str
    ) -> Dict[str, Any]:
        """Handle installation timeout by offering background execution"""
        logger.info("Starting background installation process...")

        # Create background task (don't await)
        background_task = asyncio.create_task(self._background_installation(operation))

        return {
            "status": "background_started",
            "message": "Installation started in background due to timeout",
            "background_task_id": id(background_task),
            "estimated_time": "Installation may take several more minutes",
            "recommendation": "Check system status in 5-10 minutes",
        }

    async def _background_installation(self, operation: Callable):
        """Execute installation in background with extended timeout"""
        try:
            extended_timeout = 1200.0  # 20 minutes for background installations
            logger.info("Background installation with %ss timeout", extended_timeout)

            if asyncio.iscoroutinefunction(operation):
                result = await asyncio.wait_for(operation(), timeout=extended_timeout)
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(operation), timeout=extended_timeout
                )

            logger.info("Background installation completed successfully")
            return result

        except Exception as e:
            logger.error("Background installation failed: %s", e)
            return {"status": "failed", "error": str(e)}

    async def _handle_user_interaction_timeout(
        self, operation: Callable, elapsed_time: float
    ) -> Any:
        """Handle user interaction timeout with retry"""
        max_attempts = self.config.TIMEOUTS[self.category]["max_attempts"]
        retry_timeout = self.config.TIMEOUTS[self.category]["retry"]

        logger.info(
            f"User interaction timed out after {elapsed_time:.2f}s, offering retry..."
        )

        # For user interactions, we return a clear timeout status
        return {
            "status": "timeout",
            "elapsed_time": elapsed_time,
            "message": f"User interaction timed out after {elapsed_time:.2f}s",
            "retry_available": True,
            "retry_timeout": retry_timeout,
            "max_attempts": max_attempts,
        }

    async def _handle_command_timeout(
        self, operation: Callable, operation_type: str, background_allowed: bool
    ) -> Dict[str, Any]:
        """Handle command execution timeout"""
        if background_allowed and operation_type != "interactive":
            logger.info("Moving command to background execution...")
            background_task = asyncio.create_task(
                self.execute_with_intelligent_timeout(
                    operation, "batch", background_allowed=False
                )
            )
            return {
                "status": "moved_to_background",
                "message": "Command moved to background due to timeout",
                "background_task_id": id(background_task),
            }
        else:
            return {
                "status": "timeout",
                "message": "Command execution timed out",
                "recommendation": "Try breaking down the command into smaller steps",
            }


# Convenience functions for common timeout patterns
async def execute_installation_with_timeout(
    operation: Callable,
    package_type: str = "default",
    context: Optional[Dict[str, Any]] = None,
) -> Any:
    """Execute package installation with adaptive timeout handling"""
    timeout_handler = AdaptiveTimeout(TimeoutCategory.SYSTEM_INSTALLATION)
    return await timeout_handler.execute_with_intelligent_timeout(
        operation=operation,
        operation_type=package_type,
        context=context,
        background_allowed=True,
        fallback_result={"status": "timeout", "background_available": True},
    )


async def execute_user_permission_with_timeout(
    operation: Callable, context: Optional[Dict[str, Any]] = None
) -> Any:
    """Execute user permission request with adaptive timeout"""
    timeout_handler = AdaptiveTimeout(TimeoutCategory.USER_INTERACTION)
    return await timeout_handler.execute_with_intelligent_timeout(
        operation=operation,
        operation_type="default",
        context=context,
        fallback_result={"status": "timeout", "permission_granted": False},
    )


async def execute_command_with_timeout(
    operation: Callable,
    command_type: str = "default",
    context: Optional[Dict[str, Any]] = None,
    background_allowed: bool = True,
) -> Any:
    """Execute command with adaptive timeout handling"""
    timeout_handler = AdaptiveTimeout(TimeoutCategory.COMMAND_EXECUTION)
    return await timeout_handler.execute_with_intelligent_timeout(
        operation=operation,
        operation_type=command_type,
        context=context,
        background_allowed=background_allowed,
        fallback_result={"status": "timeout", "command_failed": True},
    )


# Monitoring functions
def log_adaptive_timeout_metrics(
    original_timeout: float, new_timeout: float, operation_type: str
):
    """Log timeout adaptation metrics"""
    improvement_seconds = original_timeout - new_timeout
    improvement_percent = (improvement_seconds / original_timeout) * 100

    logger.info(
        f"TIMEOUT OPTIMIZATION: {operation_type} timeout reduced from "
        f"{original_timeout}s to {new_timeout}s "
        f"(saved {improvement_seconds}s, {improvement_percent:.1f}% improvement)"
    )


# Usage examples and testing
if __name__ == "__main__":

    async def test_timeout_optimization():
        """Test timeout optimization functionality"""

        # Test user interaction timeout (was 600s, now 30s)
        async def mock_user_permission():
            """Simulate slow user permission request for timeout testing."""
            await asyncio.sleep(35)  # Will timeout
            return True

        result = await execute_user_permission_with_timeout(
            mock_user_permission, context={"task": "test_permission"}
        )
        print(f"User permission result: {result}")

        # Test installation timeout (was 600s, now 120s with background)
        async def mock_installation():
            """Simulate slow package installation for background execution test."""
            await asyncio.sleep(150)  # Will timeout but go background
            return {"installed": True}

        result = await execute_installation_with_timeout(
            mock_installation,
            package_type="large_package",
            context={"package": "test-package"},
        )
        print(f"Installation result: {result}")

        # Log timeout metrics
        log_adaptive_timeout_metrics(600, 30, "user_permission")
        log_adaptive_timeout_metrics(600, 120, "installation")
        log_adaptive_timeout_metrics(300, 60, "command_execution")

    # Run test
    asyncio.run(test_timeout_optimization())
