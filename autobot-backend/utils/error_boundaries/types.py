# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Error Boundaries Types Module

Issue #381: Extracted from error_boundaries.py god class refactoring.
Contains enums and dataclasses for error boundary system.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict

# Module-level tuples for error type classification (from original module)
CRITICAL_ERROR_TYPES = (SystemExit, KeyboardInterrupt, MemoryError)
HIGH_SEVERITY_ERROR_TYPES = (ConnectionError, TimeoutError, OSError)
MEDIUM_SEVERITY_ERROR_TYPES = (ValueError, TypeError, AttributeError)
FALLBACK_ERROR_TYPES = (ValueError, TypeError)
RETRY_ERROR_TYPES = (ConnectionError, TimeoutError)
SYSTEM_RESTART_ERROR_TYPES = (MemoryError, SystemExit)


class ErrorSeverity(Enum):
    """Error severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def classify_error(error: Exception) -> ErrorSeverity:
    """Return the ErrorSeverity for an exception (GH#6628).

    Precedence: CRITICAL → RETRY (LOW) → HIGH → MEDIUM → else LOW.
    CRITICAL is checked first as a defensive invariant so a future exception that
    subclasses both a RETRY type and a CRITICAL type is never silently downgraded.
    RETRY must precede HIGH because ConnectionError and TimeoutError are subclasses
    of OSError (which is in HIGH_SEVERITY_ERROR_TYPES); checking HIGH first would
    prematurely cap transient network errors at the 1-retry HIGH budget (GH#8649).
    """
    if isinstance(error, CRITICAL_ERROR_TYPES):
        return ErrorSeverity.CRITICAL
    if isinstance(error, RETRY_ERROR_TYPES):
        return ErrorSeverity.LOW
    if isinstance(error, HIGH_SEVERITY_ERROR_TYPES):
        return ErrorSeverity.HIGH
    if isinstance(error, MEDIUM_SEVERITY_ERROR_TYPES):
        return ErrorSeverity.MEDIUM
    return ErrorSeverity.LOW


class ErrorCategory(Enum):
    """Error categories for better organization and handling"""

    # System-level categories
    SYSTEM = "system"
    INFRASTRUCTURE = "infrastructure"
    NETWORK = "network"
    DATABASE = "database"
    LLM = "llm"
    AGENT = "agent"
    API = "api"
    CONFIGURATION = "configuration"
    USER_INPUT = "user_input"

    # HTTP-aligned categories (for API endpoints)
    VALIDATION = "validation"  # 400 Bad Request
    AUTHENTICATION = "authentication"  # 401 Unauthorized
    AUTHORIZATION = "authorization"  # 403 Forbidden
    NOT_FOUND = "not_found"  # 404 Not Found
    CONFLICT = "conflict"  # 409 Conflict
    RATE_LIMIT = "rate_limit"  # 429 Too Many Requests
    SERVER_ERROR = "server_error"  # 500 Internal Server Error
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
    user_id: str | None = None
    request_id: str | None = None
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
    recovery_strategy: RecoveryStrategy | None = None
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
    details: Dict[str, Any] | None = None
    retry_after: int | None = None  # Seconds to wait before retry
    trace_id: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON response.

        Returns:
            Dictionary with error information formatted for API response
        """
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
        """
        Map error category to HTTP status code.

        Args:
            category: Error category enum value

        Returns:
            HTTP status code appropriate for the error category
        """
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
            ErrorCategory.INFRASTRUCTURE: 500,
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
        context: ErrorContext | None = None,
    ):
        """
        Initialize error boundary exception.

        Args:
            message: Error message
            severity: Error severity level (default: MEDIUM)
            category: Error category (default: SYSTEM)
            recovery_strategy: Recovery strategy to use (default: RETRY)
            context: Error context information
        """
        super().__init__(message)
        self.severity = severity
        self.category = category
        self.recovery_strategy = recovery_strategy
        self.context = context
