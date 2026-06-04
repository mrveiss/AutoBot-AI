# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backward-compat shim — canonical implementation is ``circuit_breaker`` module.

Issue #6494: Consolidated dual circuit-breaker implementations.
Callers should migrate to: ``from circuit_breaker import ...``
"""

from circuit_breaker import (  # noqa: F401
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    CircuitBreakerStats,
    CircuitBreakerTimeout,
    get_circuit_breaker_manager,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerManager",
    "CircuitBreakerOpenError",
    "CircuitBreakerState",
    "CircuitBreakerStats",
    "CircuitBreakerTimeout",
    "get_circuit_breaker_manager",
]
