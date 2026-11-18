#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Backend re-export shim for the circuit breaker (#18554).

The implementation moved to ``autobot_shared.circuit_breaker`` so every backend
(including the SLM) shares one breaker and one manager registry. Every public
name below is the SAME object as in the shared module, never a copy, so
``from circuit_breaker import X`` keeps working and keeps one registry.
"""

from autobot_shared.circuit_breaker import (  # noqa: F401
    CallRecord,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    CircuitBreakerStats,
    CircuitBreakerTimeout,
    CircuitState,
    circuit_breaker_async,
    circuit_breaker_sync,
    get_circuit_breaker_manager,
    protected_database_call,
    protected_llm_call,
    protected_network_call,
)

__all__ = [
    "CallRecord",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerManager",
    "CircuitBreakerOpenError",
    "CircuitBreakerState",
    "CircuitBreakerStats",
    "CircuitBreakerTimeout",
    "CircuitState",
    "circuit_breaker_async",
    "circuit_breaker_sync",
    "get_circuit_breaker_manager",
    "protected_database_call",
    "protected_llm_call",
    "protected_network_call",
]
