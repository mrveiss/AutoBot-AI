# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Error Boundary Manager Module

Issue #381: Extracted from error_boundaries.py god class refactoring.
Contains the central error boundary management system.
"""

import asyncio
import json
import logging
import threading
import time
import traceback
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.constants.threshold_constants import RetryConfig

try:
    from src.utils.redis_client import get_redis_client
except ImportError:

    def get_redis_client():
        """Fallback function when redis client is unavailable."""
        return None


try:
    from src.utils.error_metrics import record_error_metric
except ImportError:

    async def record_error_metric(*args, **kwargs):
        """Fallback async function when error metrics module is unavailable."""
        pass


from .recovery_handlers import (
    ErrorRecoveryHandler,
    FallbackRecoveryHandler,
    RetryRecoveryHandler,
)
from .types import (
    CRITICAL_ERROR_TYPES,
    FALLBACK_ERROR_TYPES,
    HIGH_SEVERITY_ERROR_TYPES,
    MEDIUM_SEVERITY_ERROR_TYPES,
    RETRY_ERROR_TYPES,
    SYSTEM_RESTART_ERROR_TYPES,
    ErrorBoundaryException,
    ErrorCategory,
    ErrorContext,
    ErrorReport,
    ErrorSeverity,
    RecoveryStrategy,
)

logger = logging.getLogger(__name__)


class ErrorBoundaryManager:
    """Central error boundary management system"""

    def __init__(self, redis_client=None):
        """
        Initialize error boundary manager.

        Args:
            redis_client: Redis client instance (default: None, will auto-initialize)
        """
        self.redis_client = redis_client or get_redis_client()
        self.recovery_handlers: List[ErrorRecoveryHandler] = []
        self.error_reports: Dict[str, ErrorReport] = {}
        self._error_count = 0
        self._lock = threading.Lock()

        # Setup default recovery handlers
        self._setup_default_handlers()

        # Setup logging
        self._setup_error_logging()

    def _setup_default_handlers(self):
        """Setup default recovery handlers for common error scenarios."""
        # Retry handler for network and external service errors
        retry_handler = RetryRecoveryHandler(
            max_retries=RetryConfig.DEFAULT_RETRIES,
            backoff_factor=RetryConfig.BACKOFF_BASE,
            retry_exceptions=(ConnectionError, TimeoutError, OSError),
        )
        self.add_recovery_handler(retry_handler)

        # Fallback handler for common operations
        common_fallbacks = {
            "llm_interface.chat_completion": {
                "content": (
                    "I apologize, but I'm having trouble processing "
                    "your request. Please try again."
                ),
                "error": True,
            },
            "knowledge_base.search": [],
            "redis_client.get": None,
            "config_manager.get": {},
        }
        fallback_handler = FallbackRecoveryHandler(common_fallbacks)
        self.add_recovery_handler(fallback_handler)

    def _setup_error_logging(self):
        """Setup error logging configuration with file handler."""
        # Create error logs directory
        log_dir = Path("logs/errors")
        log_dir.mkdir(parents=True, exist_ok=True)

        # Configure error file handler
        error_handler = logging.FileHandler(log_dir / "error_boundary.log")
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        error_handler.setFormatter(error_formatter)
        logger.addHandler(error_handler)

    def add_recovery_handler(self, handler: ErrorRecoveryHandler):
        """
        Add a custom recovery handler.

        Args:
            handler: Error recovery handler instance to add
        """
        self.recovery_handlers.append(handler)

    def generate_error_id(self) -> str:
        """
        Generate unique error ID.

        Returns:
            Unique error identifier string
        """
        with self._lock:
            self._error_count += 1
            return f"ERR_{int(time.time())}_{self._error_count:06d}"

    def _get_category_keywords(self) -> Dict[ErrorCategory, tuple]:
        """
        Get keyword mappings for error categorization.

        Returns:
            Dictionary mapping error categories to keyword tuples
        """
        return {
            ErrorCategory.NETWORK: ("connection", "network", "timeout", "refused"),
            ErrorCategory.DATABASE: ("database", "sql", "sqlite", "redis"),
            ErrorCategory.LLM: ("llm", "openai", "ollama", "model"),
            ErrorCategory.AGENT: ("agent", "classification", "orchestration"),
            ErrorCategory.API: ("api", "endpoint", "request", "response"),
            ErrorCategory.VALIDATION: ("validation", "invalid", "format"),
            ErrorCategory.CONFIGURATION: ("config", "configuration", "setting"),
        }

    def categorize_error(self, error: Exception) -> ErrorCategory:
        """
        Automatically categorize errors based on type and content.

        Args:
            error: Exception to categorize

        Returns:
            Error category classification
        """
        error_str = str(error).lower()

        # Check keyword-based categories
        for category, keywords in self._get_category_keywords().items():
            if any(keyword in error_str for keyword in keywords):
                return category

        # Check permission/access for SYSTEM category
        if "permission" in error_str or "access" in error_str:
            return ErrorCategory.SYSTEM

        return ErrorCategory.SYSTEM

    def determine_severity(
        self, error: Exception, context: ErrorContext
    ) -> ErrorSeverity:
        """
        Determine error severity based on error type and context.

        Args:
            error: Exception to evaluate
            context: Error context

        Returns:
            Error severity level
        """
        if isinstance(error, CRITICAL_ERROR_TYPES):
            return ErrorSeverity.CRITICAL
        elif isinstance(error, HIGH_SEVERITY_ERROR_TYPES):
            return ErrorSeverity.HIGH
        elif isinstance(error, MEDIUM_SEVERITY_ERROR_TYPES):
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW

    async def handle_error(self, error: Exception, context: ErrorContext) -> Any:
        """
        Handle an error with appropriate recovery strategy.

        Args:
            error: Exception to handle
            context: Error context

        Returns:
            Recovery value if successful

        Raises:
            ErrorBoundaryException if recovery not possible
        """
        # Generate error report
        error_report = self.create_error_report(error, context)

        # Store error report
        self.store_error_report(error_report)

        # Record error metric
        try:
            await record_error_metric(
                error_code=None,
                category=error_report.category,
                component=context.component,
                function=context.function,
                message=error_report.message,
                trace_id=error_report.error_id,
            )
        except Exception as metrics_error:
            logger.debug("Failed to record error metric: %s", metrics_error)

        # Try recovery handlers
        for handler in self.recovery_handlers:
            if handler.can_handle(error, context):
                try:
                    return await handler.handle(error, context)
                except Exception as recovery_error:
                    logger.error("Recovery handler failed: %s", recovery_error)
                    continue

        # No recovery possible, re-raise with context
        logger.error("No recovery possible for error: %s", error_report.error_id)
        raise ErrorBoundaryException(
            f"Unrecoverable error in {context.component}."
            f"{context.function}: {str(error)}",
            severity=error_report.severity,
            category=error_report.category,
            context=context,
        ) from error

    def create_error_report(
        self, error: Exception, context: ErrorContext
    ) -> ErrorReport:
        """
        Create a structured error report.

        Args:
            error: Exception to report
            context: Error context

        Returns:
            Structured error report
        """
        error_id = self.generate_error_id()

        # Determine recovery strategy
        recovery_strategy = RecoveryStrategy.RETRY
        if isinstance(error, FALLBACK_ERROR_TYPES):
            recovery_strategy = RecoveryStrategy.FALLBACK
        elif isinstance(error, RETRY_ERROR_TYPES):
            recovery_strategy = RecoveryStrategy.RETRY
        elif isinstance(error, SYSTEM_RESTART_ERROR_TYPES):
            recovery_strategy = RecoveryStrategy.SYSTEM_RESTART

        error_report = ErrorReport(
            error_id=error_id,
            error_type=type(error).__name__,
            message=str(error),
            severity=self.determine_severity(error, context),
            category=self.categorize_error(error),
            context=context,
            stack_trace=traceback.format_exc(),
            recovery_strategy=recovery_strategy,
        )

        return error_report

    def store_error_report(self, error_report: ErrorReport):
        """
        Store error report for analysis.

        Args:
            error_report: Error report to store
        """
        try:
            # Store in memory
            self.error_reports[error_report.error_id] = error_report

            # Store in Redis with expiration
            redis_key = f"autobot:errors:{error_report.error_id}"
            error_data = {
                "error_id": error_report.error_id,
                "error_type": error_report.error_type,
                "message": error_report.message,
                "severity": error_report.severity.value,
                "category": error_report.category.value,
                "component": error_report.context.component,
                "function": error_report.context.function,
                "timestamp": error_report.timestamp,
                "stack_trace": error_report.stack_trace[:1000],
            }

            self.redis_client.setex(redis_key, 86400, json.dumps(error_data))

            # Log error
            logger.error("Error %s: %s", error_report.error_id, error_report.message)

        except Exception as e:
            logger.error("Failed to store error report: %s", e)

    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get error statistics for monitoring.

        Returns:
            Dictionary with error statistics and recent errors
        """
        try:
            # Get recent errors from Redis
            pattern = "autobot:errors:*"
            error_keys = self.redis_client.keys(pattern)

            # Issue #397: Fix N+1 query pattern - use pipeline for batch retrieval
            recent_errors = []
            if error_keys:
                pipe = self.redis_client.pipeline()
                for key in error_keys:
                    pipe.get(key)
                results = pipe.execute()

                for error_data in results:
                    if error_data:
                        recent_errors.append(json.loads(error_data))

            # Calculate statistics
            total_errors = len(recent_errors)
            if total_errors == 0:
                return {
                    "total_errors": 0,
                    "categories": {},
                    "severities": {},
                    "components": {},
                }

            # Group by category
            categories = {}
            severities = {}
            components = {}

            for error in recent_errors:
                category = error.get("category", "unknown")
                severity = error.get("severity", "unknown")
                component = error.get("component", "unknown")

                categories[category] = categories.get(category, 0) + 1
                severities[severity] = severities.get(severity, 0) + 1
                components[component] = components.get(component, 0) + 1

            return {
                "total_errors": total_errors,
                "categories": categories,
                "severities": severities,
                "components": components,
                "recent_errors": recent_errors[-10:],
            }

        except Exception as e:
            logger.error("Failed to get error statistics: %s", e)
            return {"error": str(e)}

    @contextmanager
    def error_boundary(self, component: str, function: str, **context_kwargs):
        """
        Context manager for error boundaries.

        Args:
            component: Component name
            function: Function name
            **context_kwargs: Additional context data

        Yields:
            ErrorContext object

        Raises:
            Exception after handling
        """
        context = ErrorContext(component=component, function=function, **context_kwargs)

        try:
            yield context
        except Exception as e:
            # Handle synchronous errors
            asyncio.run(self.handle_error(e, context))
            # Re-raise the handled exception
            raise

    @asynccontextmanager
    async def async_error_boundary(
        self, component: str, function: str, **context_kwargs
    ):
        """
        Async context manager for error boundaries.

        Args:
            component: Component name
            function: Function name
            **context_kwargs: Additional context data

        Yields:
            ErrorContext object

        Raises:
            Exception after handling
        """
        context = ErrorContext(component=component, function=function, **context_kwargs)

        try:
            yield context
        except Exception as e:
            # Handle asynchronous errors
            await self.handle_error(e, context)
            # Re-raise the handled exception
            raise


# Global error boundary manager instance (thread-safe)
_error_boundary_manager: Optional[ErrorBoundaryManager] = None
_error_boundary_manager_lock = threading.Lock()


def get_error_boundary_manager() -> ErrorBoundaryManager:
    """
    Get global error boundary manager instance (thread-safe).

    Returns:
        Singleton ErrorBoundaryManager instance
    """
    global _error_boundary_manager
    if _error_boundary_manager is None:
        with _error_boundary_manager_lock:
            # Double-check after acquiring lock
            if _error_boundary_manager is None:
                _error_boundary_manager = ErrorBoundaryManager()
    return _error_boundary_manager
