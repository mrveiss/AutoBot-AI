# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Async Initializable Base Class - Standardized Initialization Pattern

This module provides a base class for components requiring async initialization
with proper idempotency, concurrency control, and error handling.

CONSOLIDATES PATTERNS FROM:
===========================
- src/autobot_memory_graph.py:137 (lock + idempotency + error handling)
- src/chat_workflow_manager.py:628 (lock + double-check + cleanup)
- backend/services/rag_service.py:59 (simple idempotency)
- backend/utils/async_redis_manager.py:137 (full pattern with metrics)
- 46+ other files with similar initialization patterns

BENEFITS:
=========
✅ Eliminates 150-300 lines of duplicate initialization code
✅ Standardizes error handling and logging
✅ Prevents race conditions with built-in locking
✅ Provides initialization metrics and timing
✅ Supports cleanup on failure
✅ Idempotency guaranteed
✅ Optional retry logic with exponential backoff

USAGE PATTERN:
==============
class MyService(AsyncInitializable):
    def __init__(self):
        super().__init__(component_name="my_service")
        # Your initialization here

    async def _initialize_impl(self) -> bool:
        '''
        Implement your actual initialization logic here.
        No need to handle locking, idempotency, or error logging.

        Returns:
            True if initialization successful, False otherwise
        '''
        # Your initialization steps
        self.resource = await create_resource()
        return True

    async def _cleanup_impl(self):
        '''
        Optional: Cleanup resources on initialization failure
        '''
        if hasattr(self, 'resource'):
            await self.resource.close()

# Usage
service = MyService()
success = await service.initialize()  # Inherits full initialization pattern

MIGRATION EXAMPLE:
==================
BEFORE (Manual Pattern - 20+ lines):
    class MyService:
        def __init__(self):
            self._initialized = False
            self._lock = asyncio.Lock()

        async def initialize(self) -> bool:
            if self._initialized:
                return True

            async with self._lock:
                if self._initialized:
                    return True

                try:
                    logger.info("Initializing MyService...")
                    # Step 1
                    self.resource = await create_resource()
                    # Step 2
                    await self.resource.setup()

                    self._initialized = True
                    logger.info("MyService initialized successfully")
                    return True

                except Exception as e:
                    logger.error(f"MyService initialization failed: {e}")
                    await self._cleanup()
                    return False

AFTER (Base Class Pattern - 8 lines):
    class MyService(AsyncInitializable):
        def __init__(self):
            super().__init__(component_name="my_service")

        async def _initialize_impl(self) -> bool:
            # Step 1
            self.resource = await create_resource()
            # Step 2
            await self.resource.setup()
            return True

        async def _cleanup_impl(self):
            if hasattr(self, 'resource'):
                await self.resource.close()

FEATURES:
=========
1. Automatic idempotency checking (prevents double initialization)
2. Async lock for concurrency control (prevents race conditions)
3. Double-check locking pattern (performance optimization)
4. Standardized error handling and logging
5. Automatic cleanup on failure (if implemented)
6. Initialization metrics (start time, duration, retry count)
7. Optional retry logic with exponential backoff
8. Component name tracking for debugging
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional

from src.utils.error_boundaries import error_boundary

logger = logging.getLogger(__name__)


@dataclass
class InitializationMetrics:
    """Metrics for initialization process"""

    component_name: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    retry_count: int = 0
    last_error: Optional[str] = None
    success: bool = False

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate initialization duration"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


class AsyncInitializable(ABC):
    """
    Base class for components requiring async initialization.

    Provides standardized initialization pattern with:
    - Idempotency (can call initialize() multiple times safely)
    - Concurrency control (async lock prevents race conditions)
    - Error handling and logging
    - Cleanup on failure
    - Initialization metrics
    """

    def __init__(
        self,
        component_name: str,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
    ):
        """
        Initialize the AsyncInitializable base.

        Args:
            component_name: Name of component for logging/debugging
            max_retries: Maximum retry attempts (0 = no retries)
            retry_delay: Initial retry delay in seconds
            retry_backoff: Backoff multiplier for retries
        """
        self._component_name = component_name
        self._initialized = False
        self._initialization_lock = asyncio.Lock()
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._retry_backoff = retry_backoff

        # Metrics
        self._metrics = InitializationMetrics(component_name=component_name)

    @property
    def is_initialized(self) -> bool:
        """Check if component is initialized"""
        return self._initialized

    @property
    def component_name(self) -> str:
        """Get component name"""
        return self._component_name

    @property
    def initialization_metrics(self) -> InitializationMetrics:
        """Get initialization metrics"""
        return self._metrics

    @abstractmethod
    async def _initialize_impl(self) -> bool:
        """
        Implement actual initialization logic here.

        This method should contain your component's specific initialization
        steps. No need to handle locking, idempotency, or error logging -
        the base class handles that.

        Returns:
            bool: True if initialization successful, False otherwise

        Raises:
            Exception: Exceptions are caught and logged by base class
        """
        pass

    async def _cleanup_impl(self):
        """
        Optional: Cleanup resources on initialization failure.

        Override this method if your component needs to clean up
        partially initialized resources when initialization fails.
        """
        pass

    @error_boundary(component="async_initializable", function="initialize")
    async def initialize(self) -> bool:
        """
        Initialize the component with full pattern:
        - Idempotency check
        - Async locking
        - Double-check pattern
        - Error handling
        - Cleanup on failure
        - Metrics tracking

        Returns:
            bool: True if initialization successful, False otherwise
        """
        # Fast path: Already initialized
        if self._initialized:
            logger.debug(f"{self._component_name} already initialized")
            return True

        # Acquire lock for initialization
        async with self._initialization_lock:
            # Double-check: Another coroutine may have initialized while we waited
            if self._initialized:
                logger.debug(
                    f"{self._component_name} was initialized by another coroutine"
                )
                return True

            # Start metrics tracking
            self._metrics.start_time = time.time()
            logger.info(f"Initializing {self._component_name}...")

            # Attempt initialization with optional retry
            current_delay = self._retry_delay
            for attempt in range(self._max_retries + 1):
                try:
                    # Call implementation
                    success = await self._initialize_impl()

                    if success:
                        # Mark as initialized
                        self._initialized = True
                        self._metrics.end_time = time.time()
                        self._metrics.success = True

                        duration = self._metrics.duration_seconds
                        logger.info(
                            f"{self._component_name} initialized successfully "
                            f"(took {duration:.2f}s, {self._metrics.retry_count} retries)"
                        )
                        return True
                    else:
                        # Implementation returned False
                        logger.warning(
                            f"{self._component_name} initialization returned False "
                            f"(attempt {attempt + 1}/{self._max_retries + 1})"
                        )

                except Exception as e:
                    # Implementation raised exception
                    self._metrics.last_error = str(e)
                    self._metrics.retry_count = attempt

                    if attempt < self._max_retries:
                        # Retry with backoff
                        logger.warning(
                            f"{self._component_name} initialization failed "
                            f"(attempt {attempt + 1}/{self._max_retries + 1}): {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= self._retry_backoff
                    else:
                        # Final attempt failed
                        logger.error(
                            f"{self._component_name} initialization failed after "
                            f"{self._max_retries + 1} attempts: {e}"
                        )

                        # Attempt cleanup
                        try:
                            await self._cleanup_impl()
                            logger.info(f"{self._component_name} cleanup completed")
                        except Exception as cleanup_error:
                            logger.error(
                                f"{self._component_name} cleanup failed: {cleanup_error}"
                            )

            # All attempts failed
            self._metrics.end_time = time.time()
            self._metrics.success = False
            return False

    async def ensure_initialized(self):
        """
        Ensure component is initialized, raising exception if initialization fails.

        Raises:
            RuntimeError: If initialization fails
        """
        if not await self.initialize():
            raise RuntimeError(
                f"{self._component_name} initialization failed. "
                f"Last error: {self._metrics.last_error}"
            )


class SyncInitializable(ABC):
    """
    Synchronous version of AsyncInitializable for non-async components.

    Use this for components that don't require async operations during initialization.
    """

    def __init__(
        self,
        component_name: str,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
    ):
        """
        Initialize the SyncInitializable base.

        Args:
            component_name: Name of component for logging/debugging
            max_retries: Maximum retry attempts (0 = no retries)
            retry_delay: Initial retry delay in seconds
            retry_backoff: Backoff multiplier for retries
        """
        self._component_name = component_name
        self._initialized = False
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._retry_backoff = retry_backoff

        # Metrics
        self._metrics = InitializationMetrics(component_name=component_name)

        # Thread-safe lock for synchronous access
        import threading

        self._initialization_lock = threading.Lock()

    @property
    def is_initialized(self) -> bool:
        """Check if component is initialized"""
        return self._initialized

    @property
    def component_name(self) -> str:
        """Get component name"""
        return self._component_name

    @property
    def initialization_metrics(self) -> InitializationMetrics:
        """Get initialization metrics"""
        return self._metrics

    @abstractmethod
    def _initialize_impl(self) -> bool:
        """
        Implement actual initialization logic here.

        Returns:
            bool: True if initialization successful, False otherwise
        """
        pass

    def _cleanup_impl(self):
        """Optional: Cleanup resources on initialization failure"""
        pass

    def initialize(self) -> bool:
        """
        Initialize the component with full pattern (synchronous version).

        Returns:
            bool: True if initialization successful, False otherwise
        """
        # Fast path: Already initialized
        if self._initialized:
            logger.debug(f"{self._component_name} already initialized")
            return True

        # Acquire lock for initialization
        with self._initialization_lock:
            # Double-check
            if self._initialized:
                logger.debug(
                    f"{self._component_name} was initialized by another thread"
                )
                return True

            # Start metrics tracking
            self._metrics.start_time = time.time()
            logger.info(f"Initializing {self._component_name}...")

            # Attempt initialization with optional retry
            current_delay = self._retry_delay
            for attempt in range(self._max_retries + 1):
                try:
                    # Call implementation
                    success = self._initialize_impl()

                    if success:
                        # Mark as initialized
                        self._initialized = True
                        self._metrics.end_time = time.time()
                        self._metrics.success = True

                        duration = self._metrics.duration_seconds
                        logger.info(
                            f"{self._component_name} initialized successfully "
                            f"(took {duration:.2f}s, {self._metrics.retry_count} retries)"
                        )
                        return True
                    else:
                        logger.warning(
                            f"{self._component_name} initialization returned False "
                            f"(attempt {attempt + 1}/{self._max_retries + 1})"
                        )

                except Exception as e:
                    # Implementation raised exception
                    self._metrics.last_error = str(e)
                    self._metrics.retry_count = attempt

                    if attempt < self._max_retries:
                        # Retry with backoff
                        logger.warning(
                            f"{self._component_name} initialization failed "
                            f"(attempt {attempt + 1}/{self._max_retries + 1}): {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        import time as time_module

                        time_module.sleep(current_delay)
                        current_delay *= self._retry_backoff
                    else:
                        # Final attempt failed
                        logger.error(
                            f"{self._component_name} initialization failed after "
                            f"{self._max_retries + 1} attempts: {e}"
                        )

                        # Attempt cleanup
                        try:
                            self._cleanup_impl()
                            logger.info(f"{self._component_name} cleanup completed")
                        except Exception as cleanup_error:
                            logger.error(
                                f"{self._component_name} cleanup failed: {cleanup_error}"
                            )

            # All attempts failed
            self._metrics.end_time = time.time()
            self._metrics.success = False
            return False

    def ensure_initialized(self):
        """
        Ensure component is initialized, raising exception if initialization fails.

        Raises:
            RuntimeError: If initialization fails
        """
        if not self.initialize():
            raise RuntimeError(
                f"{self._component_name} initialization failed. "
                f"Last error: {self._metrics.last_error}"
            )
