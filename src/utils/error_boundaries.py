#!/usr/bin/env python3
"""
Comprehensive Error Boundary System for AutoBot

Provides centralized error handling, recovery mechanisms, and error reporting
across all AutoBot components to prevent system crashes and provide meaningful
error messages to users.
"""

import asyncio
import functools
import json
import logging
import os
import sys
import threading
import time
import traceback
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from weakref import WeakValueDictionary

from src.constants.network_constants import NetworkConstants

# Add project root to path for imports
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

try:
    from src.utils.redis_client import get_redis_client
except ImportError:
    # Fallback if redis client not available
    def get_redis_client():
        return None


logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better organization and handling"""

    # System-level categories
    SYSTEM = "system"
    NETWORK = "network"
    DATABASE = "database"
    LLM = "llm"
    AGENT = "agent"
    API = "api"
    CONFIGURATION = "configuration"
    USER_INPUT = "user_input"

    # HTTP-aligned categories (for API endpoints)
    VALIDATION = "validation"              # 400 Bad Request
    AUTHENTICATION = "authentication"      # 401 Unauthorized
    AUTHORIZATION = "authorization"        # 403 Forbidden
    NOT_FOUND = "not_found"               # 404 Not Found
    CONFLICT = "conflict"                 # 409 Conflict
    RATE_LIMIT = "rate_limit"             # 429 Too Many Requests
    SERVER_ERROR = "server_error"         # 500 Internal Server Error
    SERVICE_UNAVAILABLE = "service_unavailable"  # 503 Service Unavailable
    EXTERNAL_SERVICE = "external_service"  # 502 Bad Gateway


class RecoveryStrategy(Enum):
    """Recovery strategies for different error types"""

    RETRY = "retry"
    FALLBACK = "fallback"
    GRACEFUL_DEGRADATION = "graceful_degradation"
    USER_INTERVENTION = "user_intervention"
    SYSTEM_RESTART = "system_restart"
    IGNORE = "ignore"


@dataclass
class ErrorContext:
    """Context information for error handling"""

    component: str
    function: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    additional_data: dict = field(default_factory=dict)


@dataclass
class ErrorReport:
    """Structured error report"""

    error_id: str
    error_type: str
    message: str
    severity: ErrorSeverity
    category: ErrorCategory
    context: ErrorContext
    stack_trace: str
    recovery_strategy: Optional[RecoveryStrategy] = None
    recovery_attempts: int = 0
    resolved: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class APIErrorResponse:
    """Standardized API error response for FastAPI endpoints"""

    category: ErrorCategory
    message: str
    code: str  # Error code like "KB_001", "AUTH_002"
    status_code: int
    details: Optional[Dict[str, Any]] = None
    retry_after: Optional[int] = None  # Seconds to wait before retry
    trace_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response"""
        response = {
            "error": {
                "category": self.category.value,
                "message": self.message,
                "code": self.code,
                "timestamp": self.timestamp,
            }
        }
        if self.details:
            response["error"]["details"] = self.details
        if self.retry_after:
            response["error"]["retry_after"] = self.retry_after
        if self.trace_id:
            response["error"]["trace_id"] = self.trace_id
        return response

    @staticmethod
    def get_status_code_for_category(category: ErrorCategory) -> int:
        """Map error category to HTTP status code"""
        status_map = {
            ErrorCategory.VALIDATION: 400,
            ErrorCategory.AUTHENTICATION: 401,
            ErrorCategory.AUTHORIZATION: 403,
            ErrorCategory.NOT_FOUND: 404,
            ErrorCategory.CONFLICT: 409,
            ErrorCategory.RATE_LIMIT: 429,
            ErrorCategory.SERVER_ERROR: 500,
            ErrorCategory.EXTERNAL_SERVICE: 502,
            ErrorCategory.SERVICE_UNAVAILABLE: 503,
            # Defaults for other categories
            ErrorCategory.SYSTEM: 500,
            ErrorCategory.NETWORK: 503,
            ErrorCategory.DATABASE: 500,
            ErrorCategory.LLM: 500,
            ErrorCategory.AGENT: 500,
            ErrorCategory.API: 500,
            ErrorCategory.CONFIGURATION: 500,
            ErrorCategory.USER_INPUT: 400,
        }
        return status_map.get(category, 500)


class ErrorBoundaryException(Exception):
    """Custom exception for error boundary system"""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        recovery_strategy: RecoveryStrategy = RecoveryStrategy.RETRY,
        context: Optional[ErrorContext] = None,
    ):
        super().__init__(message)
        self.severity = severity
        self.category = category
        self.recovery_strategy = recovery_strategy
        self.context = context


class ErrorRecoveryHandler(ABC):
    """Abstract base class for error recovery handlers"""

    @abstractmethod
    def can_handle(self, error: Exception, context: ErrorContext) -> bool:
        """Check if this handler can handle the given error"""
        pass

    @abstractmethod
    async def handle(self, error: Exception, context: ErrorContext) -> Any:
        """Handle the error and return a recovery value or re-raise"""
        pass


class RetryRecoveryHandler(ErrorRecoveryHandler):
    """Recovery handler that implements retry logic"""

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
        retry_exceptions: tuple = (Exception,),
    ):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.retry_exceptions = retry_exceptions
        self._retry_counts = WeakValueDictionary()

    def can_handle(self, error: Exception, context: ErrorContext) -> bool:
        return isinstance(error, self.retry_exceptions)

    async def handle(self, error: Exception, context: ErrorContext) -> Any:
        retry_key = f"{context.component}.{context.function}"
        current_retries = self._retry_counts.get(retry_key, 0)

        if current_retries >= self.max_retries:
            logger.error(f"Max retries ({self.max_retries}) exceeded for {retry_key}")
            raise error

        # Calculate backoff delay
        delay = self.backoff_factor**current_retries
        logger.warning(
            f"Retrying {retry_key} in {delay:.2f}s "
            f"(attempt {current_retries + 1}/{self.max_retries})"
        )

        await asyncio.sleep(delay)
        self._retry_counts[retry_key] = current_retries + 1

        # Re-raise to trigger retry
        raise error


class FallbackRecoveryHandler(ErrorRecoveryHandler):
    """Recovery handler that provides fallback values"""

    def __init__(self, fallback_values: Dict[str, Any]):
        self.fallback_values = fallback_values

    def can_handle(self, error: Exception, context: ErrorContext) -> bool:
        fallback_key = f"{context.component}.{context.function}"
        return fallback_key in self.fallback_values

    async def handle(self, error: Exception, context: ErrorContext) -> Any:
        fallback_key = f"{context.component}.{context.function}"
        fallback_value = self.fallback_values[fallback_key]

        logger.warning(f"Using fallback value for {fallback_key}: {fallback_value}")
        return fallback_value


class GracefulDegradationHandler(ErrorRecoveryHandler):
    """Handler for graceful service degradation"""

    def __init__(self, degraded_functions: Dict[str, Callable]):
        self.degraded_functions = degraded_functions

    def can_handle(self, error: Exception, context: ErrorContext) -> bool:
        degraded_key = f"{context.component}.{context.function}"
        return degraded_key in self.degraded_functions

    async def handle(self, error: Exception, context: ErrorContext) -> Any:
        degraded_key = f"{context.component}.{context.function}"
        degraded_func = self.degraded_functions[degraded_key]

        logger.warning(f"Graceful degradation for {degraded_key}")

        # Call degraded function with original arguments
        if asyncio.iscoroutinefunction(degraded_func):
            return await degraded_func(*context.args, **context.kwargs)
        else:
            return degraded_func(*context.args, **context.kwargs)


class ErrorBoundaryManager:
    """Central error boundary management system"""

    def __init__(self, redis_client=None):
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
        """Setup default recovery handlers"""
        # Retry handler for network and external service errors
        retry_handler = RetryRecoveryHandler(
            max_retries=3,
            backoff_factor=2.0,
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
        """Setup error logging configuration"""
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
        """Add a custom recovery handler"""
        self.recovery_handlers.append(handler)

    def generate_error_id(self) -> str:
        """Generate unique error ID"""
        with self._lock:
            self._error_count += 1
            return f"ERR_{int(time.time())}_{self._error_count:06d}"

    def categorize_error(self, error: Exception) -> ErrorCategory:
        """Automatically categorize errors based on type and content"""
        error_str = str(error).lower()

        if any(
            keyword in error_str
            for keyword in ["connection", "network", "timeout", "refused"]
        ):
            return ErrorCategory.NETWORK
        elif any(
            keyword in error_str for keyword in ["database", "sql", "sqlite", "redis"]
        ):
            return ErrorCategory.DATABASE
        elif any(
            keyword in error_str for keyword in ["llm", "openai", "ollama", "model"]
        ):
            return ErrorCategory.LLM
        elif any(
            keyword in error_str
            for keyword in ["agent", "classification", "orchestration"]
        ):
            return ErrorCategory.AGENT
        elif any(
            keyword in error_str
            for keyword in ["api", "endpoint", "request", "response"]
        ):
            return ErrorCategory.API
        elif any(
            keyword in error_str for keyword in ["validation", "invalid", "format"]
        ):
            return ErrorCategory.VALIDATION
        elif any(
            keyword in error_str for keyword in ["config", "configuration", "setting"]
        ):
            return ErrorCategory.CONFIGURATION
        elif "permission" in error_str or "access" in error_str:
            return ErrorCategory.SYSTEM
        else:
            return ErrorCategory.SYSTEM

    def determine_severity(
        self, error: Exception, context: ErrorContext
    ) -> ErrorSeverity:
        """Determine error severity based on error type and context"""
        if isinstance(error, (SystemExit, KeyboardInterrupt, MemoryError)):
            return ErrorSeverity.CRITICAL
        elif isinstance(error, (ConnectionError, TimeoutError, OSError)):
            return ErrorSeverity.HIGH
        elif isinstance(error, (ValueError, TypeError, AttributeError)):
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW

    async def handle_error(self, error: Exception, context: ErrorContext) -> Any:
        """Handle an error with appropriate recovery strategy"""
        # Generate error report
        error_report = self.create_error_report(error, context)

        # Store error report
        self.store_error_report(error_report)

        # Try recovery handlers
        for handler in self.recovery_handlers:
            if handler.can_handle(error, context):
                try:
                    return await handler.handle(error, context)
                except Exception as recovery_error:
                    logger.error(f"Recovery handler failed: {recovery_error}")
                    continue

        # No recovery possible, re-raise with context
        logger.error(f"No recovery possible for error: {error_report.error_id}")
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
        """Create a structured error report"""
        error_id = self.generate_error_id()

        # Determine recovery strategy
        recovery_strategy = RecoveryStrategy.RETRY
        if isinstance(error, (ValueError, TypeError)):
            recovery_strategy = RecoveryStrategy.FALLBACK
        elif isinstance(error, (ConnectionError, TimeoutError)):
            recovery_strategy = RecoveryStrategy.RETRY
        elif isinstance(error, (MemoryError, SystemExit)):
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
        """Store error report for analysis"""
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
                "stack_trace": error_report.stack_trace[:1000],  # Truncate for storage
            }

            self.redis_client.setex(
                redis_key, 86400, json.dumps(error_data)
            )  # 24h expiry

            # Log error
            logger.error(f"Error {error_report.error_id}: {error_report.message}")

        except Exception as e:
            logger.error(f"Failed to store error report: {e}")

    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics for monitoring"""
        try:
            # Get recent errors from Redis
            pattern = "autobot:errors:*"
            error_keys = self.redis_client.keys(pattern)

            recent_errors = []
            for key in error_keys:
                error_data = self.redis_client.get(key)
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
                "recent_errors": recent_errors[-10:],  # Last 10 errors
            }

        except Exception as e:
            logger.error(f"Failed to get error statistics: {e}")
            return {"error": str(e)}

    @contextmanager
    def error_boundary(self, component: str, function: str, **context_kwargs):
        """Context manager for error boundaries"""
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
        """Async context manager for error boundaries"""
        context = ErrorContext(component=component, function=function, **context_kwargs)

        try:
            yield context
        except Exception as e:
            # Handle asynchronous errors
            await self.handle_error(e, context)
            # Re-raise the handled exception
            raise


# Global error boundary manager instance
_error_boundary_manager = None


def get_error_boundary_manager() -> ErrorBoundaryManager:
    """Get global error boundary manager instance"""
    global _error_boundary_manager
    if _error_boundary_manager is None:
        _error_boundary_manager = ErrorBoundaryManager()
    return _error_boundary_manager


def error_boundary(
    component: str = None,
    function: str = None,
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.RETRY,
    max_retries: int = 3,
):
    """Decorator for function-level error boundaries"""

    def decorator(func):
        comp_name = component or func.__module__
        func_name = function or func.__name__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                manager = get_error_boundary_manager()
                context = ErrorContext(
                    component=comp_name, function=func_name, args=args, kwargs=kwargs
                )

                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        if attempt == max_retries:
                            # Last attempt, handle error
                            return await manager.handle_error(e, context)
                        elif recovery_strategy == RecoveryStrategy.RETRY:
                            # Wait before retry
                            await asyncio.sleep(2**attempt)
                            continue
                        else:
                            # Handle error immediately
                            return await manager.handle_error(e, context)

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                manager = get_error_boundary_manager()
                context = ErrorContext(
                    component=comp_name, function=func_name, args=args, kwargs=kwargs
                )

                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        if attempt == max_retries:
                            # Last attempt, handle error
                            return asyncio.run(manager.handle_error(e, context))
                        elif recovery_strategy == RecoveryStrategy.RETRY:
                            # Wait before retry
                            time.sleep(2**attempt)
                            continue
                        else:
                            # Handle error immediately
                            return asyncio.run(manager.handle_error(e, context))

            return sync_wrapper

    return decorator


def with_error_handling(
    category: ErrorCategory = ErrorCategory.SERVER_ERROR,
    operation: str = None,
    error_code_prefix: str = "API",
):
    """
    Simplified decorator for API endpoints with automatic HTTP error conversion.

    Usage:
        @with_error_handling(
            category=ErrorCategory.VALIDATION,
            operation="validate_user_input"
        )
        async def create_user(user_data: dict):
            # Implementation
            pass

    Args:
        category: Error category (determines HTTP status code)
        operation: Operation name for logging/tracing
        error_code_prefix: Prefix for error codes (e.g., "KB", "AUTH")
    """
    def decorator(func):
        func_operation = operation or func.__name__

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # Generate trace ID
                    trace_id = f"{func_operation}_{int(time.time()*1000)}"

                    # Generate error code
                    error_code = f"{error_code_prefix}_{abs(hash(str(e))) % 10000:04d}"

                    # Get status code from category
                    status_code = APIErrorResponse.get_status_code_for_category(category)

                    # Create API error response
                    error_response = APIErrorResponse(
                        category=category,
                        message=str(e),
                        code=error_code,
                        status_code=status_code,
                        details={"operation": func_operation},
                        trace_id=trace_id,
                    )

                    # Log the error
                    logger.error(
                        f"Error in {func_operation}: {e} "
                        f"(trace_id: {trace_id}, code: {error_code})"
                    )

                    # Raise FastAPI HTTPException
                    try:
                        from fastapi import HTTPException
                        raise HTTPException(
                            status_code=status_code,
                            detail=error_response.to_dict()
                        )
                    except ImportError:
                        # FastAPI not available, return error dict
                        return error_response.to_dict()

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Generate trace ID
                    trace_id = f"{func_operation}_{int(time.time()*1000)}"

                    # Generate error code
                    error_code = f"{error_code_prefix}_{abs(hash(str(e))) % 10000:04d}"

                    # Get status code from category
                    status_code = APIErrorResponse.get_status_code_for_category(category)

                    # Create API error response
                    error_response = APIErrorResponse(
                        category=category,
                        message=str(e),
                        code=error_code,
                        status_code=status_code,
                        details={"operation": func_operation},
                        trace_id=trace_id,
                    )

                    # Log the error
                    logger.error(
                        f"Error in {func_operation}: {e} "
                        f"(trace_id: {trace_id}, code: {error_code})"
                    )

                    # Raise FastAPI HTTPException
                    try:
                        from fastapi import HTTPException
                        raise HTTPException(
                            status_code=status_code,
                            detail=error_response.to_dict()
                        )
                    except ImportError:
                        # FastAPI not available, return error dict
                        return error_response.to_dict()

            return sync_wrapper

    return decorator


# Convenient error boundary functions
def with_error_boundary(component: str, function: str):
    """Context manager for error boundaries"""
    return get_error_boundary_manager().error_boundary(component, function)


async def with_async_error_boundary(component: str, function: str):
    """Async context manager for error boundaries"""
    return get_error_boundary_manager().async_error_boundary(component, function)


def get_error_statistics():
    """Get system error statistics"""
    return get_error_boundary_manager().get_error_statistics()


# CLI for error boundary management
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AutoBot Error Boundary Management")
    parser.add_argument("--stats", action="store_true", help="Show error statistics")
    parser.add_argument(
        "--test", action="store_true", help="Test error boundary system"
    )

    args = parser.parse_args()

    if args.stats:
        stats = get_error_statistics()
        print("📊 Error Statistics:")
        print(json.dumps(stats, indent=2))

    elif args.test:
        print("🧪 Testing Error Boundary System...")

        @error_boundary(component="test", function="divide")
        def test_divide(a, b):
            return a / b

        # Test normal operation
        result = test_divide(10, 2)
        print(f"Normal operation: 10 / 2 = {result}")

        # Test error handling
        try:
            result = test_divide(10, 0)
            print(f"Error handling: 10 / 0 = {result}")
        except Exception as e:
            print(f"Error caught: {e}")

        print("✅ Error boundary system test completed")

    else:
        print("Use --stats to show statistics or --test to test the system")
