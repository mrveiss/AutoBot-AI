# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend shim over ``autobot_shared.error_boundaries`` (#18554).

The implementation lives in ``autobot_shared.error_boundaries``; this module
re-exports the SAME objects and registers the backend's cancel-scope and
error-metric implementations with it, so a backend process behaves identically
whichever path imported the boundaries. ``app_factory`` and ``celery_app`` also
call :func:`register_backend_hooks` explicitly at startup, because most prod
code imports the shared path and never touches this shim.
"""

from autobot_shared.error_boundaries.boundary_manager import ErrorBoundaryManager, get_error_boundary_manager
from autobot_shared.error_boundaries.decorators import (
    DEFAULT_ROUTE_DEADLINE_SECONDS,
    ROUTE_DEADLINE_GRACE,
    bounded,
    error_boundary,
    get_error_statistics,
    with_async_error_boundary,
    with_error_boundary,
    with_error_handling,
)
from autobot_shared.error_boundaries.hooks import (
    register_cancel_scope_provider,
    register_error_metric_sink,
)
from autobot_shared.error_boundaries.recovery_handlers import (
    ErrorRecoveryHandler,
    FallbackRecoveryHandler,
    GracefulDegradationHandler,
    RetryRecoveryHandler,
)
from autobot_shared.error_boundaries.types import (
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
    classify_error,
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
    "DEFAULT_ROUTE_DEADLINE_SECONDS",
    "ROUTE_DEADLINE_GRACE",
    "bounded",
    "with_error_handling",
    "with_error_boundary",
    "with_async_error_boundary",
    "get_error_statistics",
    # Classification helper (GH#6628)
    "classify_error",
    "register_backend_hooks",
    # Registration hooks (#18554)
    "register_cancel_scope_provider",
    "register_error_metric_sink",
]


async def _record_backend_error_metric(*args, **kwargs):
    """Forward to ``utils.error_metrics.record_error_metric``, resolved at call time.

    Lazy so importing this shim does not import the metrics module (which imports
    the shared boundaries) and so patching the backend function is honoured.
    """
    from utils.error_metrics import record_error_metric

    await record_error_metric(*args, **kwargs)


def register_backend_hooks() -> None:
    """Register the backend's cancel scopes and metric sink (idempotent)."""
    from utils import cancel_tokens

    register_cancel_scope_provider(cancel_tokens)
    register_error_metric_sink(_record_backend_error_metric)


register_backend_hooks()
