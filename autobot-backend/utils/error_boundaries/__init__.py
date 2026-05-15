# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Error Boundaries Package

Issue #381: Extracted from error_boundaries.py god class refactoring.
Provides centralized error handling, recovery mechanisms, and error reporting.

- types.py: Enums, dataclasses, and exception types
- recovery_handlers.py: Abstract and concrete recovery handler implementations
- boundary_manager.py: Central error boundary management system
- decorators.py: Function-level error boundary decorators
"""

from .boundary_manager import ErrorBoundaryManager, get_error_boundary_manager
from .decorators import (
    error_boundary,
    get_error_statistics,
    with_async_error_boundary,
    with_error_boundary,
    with_error_handling,
)
from .recovery_handlers import (
    ErrorRecoveryHandler,
    FallbackRecoveryHandler,
    GracefulDegradationHandler,
    RetryRecoveryHandler,
)
from .types import (
    CRITICAL_ERROR_TYPES,
    FALLBACK_ERROR_TYPES,
    HIGH_SEVERITY_ERROR_TYPES,
    MEDIUM_SEVERITY_ERROR_TYPES,
    RETRY_ERROR_TYPES,
    SYSTEM_RESTART_ERROR_TYPES,
    APIErrorResponse,
    ErrorBoundaryException,
    ErrorCategory,
    ErrorContext,
    ErrorReport,
    ErrorSeverity,
    RecoveryStrategy,
)

# Backward compatibility aliases with underscore prefix (Issue #380)
_CRITICAL_ERROR_TYPES = CRITICAL_ERROR_TYPES
_HIGH_SEVERITY_ERROR_TYPES = HIGH_SEVERITY_ERROR_TYPES
_MEDIUM_SEVERITY_ERROR_TYPES = MEDIUM_SEVERITY_ERROR_TYPES
_FALLBACK_ERROR_TYPES = FALLBACK_ERROR_TYPES
_RETRY_ERROR_TYPES = RETRY_ERROR_TYPES
_SYSTEM_RESTART_ERROR_TYPES = SYSTEM_RESTART_ERROR_TYPES

__all__ = [
    # Types and enums
    "ErrorSeverity",
    "ErrorCategory",
    "RecoveryStrategy",
    "ErrorContext",
    "ErrorReport",
    "APIErrorResponse",
    "ErrorBoundaryException",
    # Error type tuples (both with and without underscore prefix)
    "CRITICAL_ERROR_TYPES",
    "HIGH_SEVERITY_ERROR_TYPES",
    "MEDIUM_SEVERITY_ERROR_TYPES",
    "FALLBACK_ERROR_TYPES",
    "RETRY_ERROR_TYPES",
    "SYSTEM_RESTART_ERROR_TYPES",
    "_CRITICAL_ERROR_TYPES",
    "_HIGH_SEVERITY_ERROR_TYPES",
    "_MEDIUM_SEVERITY_ERROR_TYPES",
    "_FALLBACK_ERROR_TYPES",
    "_RETRY_ERROR_TYPES",
    "_SYSTEM_RESTART_ERROR_TYPES",
    # Recovery handlers
    "ErrorRecoveryHandler",
    "RetryRecoveryHandler",
    "FallbackRecoveryHandler",
    "GracefulDegradationHandler",
    # Manager
    "ErrorBoundaryManager",
    "get_error_boundary_manager",
    # Decorators and utilities
    "error_boundary",
    "with_error_handling",
    "with_error_boundary",
    "with_async_error_boundary",
    "get_error_statistics",
]
