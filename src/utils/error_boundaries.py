#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Comprehensive Error Boundary System for AutoBot

Issue #381: This file has been refactored into the error_boundaries/ package.
This thin facade maintains backward compatibility while delegating to focused modules.

See: src/utils/error_boundaries/
- types.py: Enums, dataclasses, and exception types
- recovery_handlers.py: Abstract and concrete recovery handler implementations
- boundary_manager.py: Central error boundary management system
- decorators.py: Function-level error boundary decorators

Provides centralized error handling, recovery mechanisms, and error reporting
across all AutoBot components to prevent system crashes and provide meaningful
error messages to users.
"""

import json

# Re-export all public API from the package for backward compatibility
from src.utils.error_boundaries import (
    # Types and enums
    ErrorSeverity,
    ErrorCategory,
    RecoveryStrategy,
    ErrorContext,
    ErrorReport,
    APIErrorResponse,
    ErrorBoundaryException,
    # Error type tuples
    CRITICAL_ERROR_TYPES,
    HIGH_SEVERITY_ERROR_TYPES,
    MEDIUM_SEVERITY_ERROR_TYPES,
    FALLBACK_ERROR_TYPES,
    RETRY_ERROR_TYPES,
    SYSTEM_RESTART_ERROR_TYPES,
    # Recovery handlers
    ErrorRecoveryHandler,
    RetryRecoveryHandler,
    FallbackRecoveryHandler,
    GracefulDegradationHandler,
    # Manager
    ErrorBoundaryManager,
    get_error_boundary_manager,
    # Decorators and utilities
    error_boundary,
    with_error_handling,
    with_error_boundary,
    with_async_error_boundary,
    get_error_statistics,
)

# Re-export with underscore prefix for backward compatibility (Issue #380)
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
        print("Error Statistics:")
        print(json.dumps(stats, indent=2))

    elif args.test:
        print("Testing Error Boundary System...")

        @error_boundary(component="test", function="divide")
        def test_divide(a, b):
            """Test division function."""
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

        print("Error boundary system test completed")

    else:
        print("Use --stats to show statistics or --test to test the system")
