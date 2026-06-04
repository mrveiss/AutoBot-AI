# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Resilience services for graceful degradation and error isolation.

Issue #4342: Error isolation & graceful degradation for external services.
Enables system to continue with reduced functionality when dependencies fail.
"""

from .circuit_breaker_manager import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    CircuitBreakerStats,
    CircuitBreakerTimeout,
    get_circuit_breaker_manager,
)
from .error_budget import ErrorBudget, ErrorBudgetTracker
from .error_isolation import isolate_errors
from .fallback_manager import FallbackManager, get_fallback_manager

__all__ = [
    "isolate_errors",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerManager",
    "CircuitBreakerOpenError",
    "CircuitBreakerState",
    "CircuitBreakerStats",
    "CircuitBreakerTimeout",
    "get_circuit_breaker_manager",
    "ErrorBudget",
    "ErrorBudgetTracker",
    "FallbackManager",
    "get_fallback_manager",
]
