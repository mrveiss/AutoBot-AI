# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Circuit Breaker Manager Module

Issue #4342: Manages circuit breaker instances for external services.
Detects timeouts, connection errors, rate limits.
Prevents cascading failures via fail-fast pattern.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""

    failure_threshold: int = 5  # Failures before open
    recovery_timeout: float = 60.0  # Seconds before trying again
    success_threshold: int = 2  # Successes needed to close from half_open
    timeout: float = 10.0  # Call timeout


@dataclass
class CircuitBreakerStats:
    """Statistics for a circuit breaker."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    blocked_calls: int = 0
    state_changes: int = 0
    last_state_change: float = field(default_factory=time.time)
    last_failure_time: Optional[float] = None
    last_failure_error: Optional[str] = None


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


class CircuitBreakerTimeout(Exception):
    """Raised when call exceeds circuit breaker timeout."""

    pass


class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    States:
        CLOSED: Service is healthy, calls proceed normally
        OPEN: Service is failing, calls are rejected immediately
        HALF_OPEN: Testing if service has recovered, limited calls allowed
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        """Initialize circuit breaker."""
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.stats = CircuitBreakerStats()
        self._lock = Lock()

    def _record_success(self):
        """Record successful call."""
        with self._lock:
            self.stats.total_calls += 1
            self.stats.successful_calls += 1

            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self._transition_to_closed()
            else:
                self.failure_count = 0
                self.success_count = 0

    def _record_failure(self, error: Exception):
        """Record failed call."""
        with self._lock:
            self.stats.total_calls += 1
            self.stats.failed_calls += 1
            self.stats.last_failure_time = time.time()
            self.stats.last_failure_error = type(error).__name__
            self.failure_count += 1

            if self.state == CircuitBreakerState.CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    self._transition_to_open()

            elif self.state == CircuitBreakerState.HALF_OPEN:
                self._transition_to_open()

    def _record_blocked(self):
        """Record blocked call (circuit open)."""
        with self._lock:
            self.stats.total_calls += 1
            self.stats.blocked_calls += 1

    def _transition_to_open(self):
        """Transition to OPEN state."""
        if self.state != CircuitBreakerState.OPEN:
            self.state = CircuitBreakerState.OPEN
            self.stats.state_changes += 1
            logger.warning(
                "Circuit breaker %s opened after %d failures",
                self.name,
                self.failure_count,
            )

    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state."""
        if self.state != CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.HALF_OPEN
            self.success_count = 0
            self.stats.state_changes += 1
            logger.info("Circuit breaker %s testing recovery (half-open)", self.name)

    def _transition_to_closed(self):
        """Transition to CLOSED state."""
        if self.state != CircuitBreakerState.CLOSED:
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.stats.state_changes += 1
            logger.info("Circuit breaker %s recovered (closed)", self.name)

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
            CircuitBreakerTimeout: If call exceeds timeout
        """
        with self._lock:
            # Check if we should try recovery
            if self.state == CircuitBreakerState.OPEN:
                if (
                    time.time() - self.stats.last_state_change
                    >= self.config.recovery_timeout
                ):
                    self._transition_to_half_open()
                else:
                    self._record_blocked()
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker {self.name} is open"
                    )

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure(e)
            raise

    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute async function with circuit breaker protection.

        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        with self._lock:
            # Check if we should try recovery
            if self.state == CircuitBreakerState.OPEN:
                if (
                    time.time() - self.stats.last_state_change
                    >= self.config.recovery_timeout
                ):
                    self._transition_to_half_open()
                else:
                    self._record_blocked()
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker {self.name} is open"
                    )

        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.timeout,
            )
            self._record_success()
            return result
        except asyncio.TimeoutError as e:
            self._record_failure(e)
            raise CircuitBreakerTimeout(
                f"Call to {self.name} exceeded {self.config.timeout}s"
            )
        except Exception as e:
            self._record_failure(e)
            raise


class CircuitBreakerManager:
    """Manages multiple circuit breakers for different services."""

    def __init__(self):
        """Initialize circuit breaker manager."""
        self.breakers: Dict[str, CircuitBreaker] = {}
        self._lock = Lock()

    def get_breaker(
        self,
        service_name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> CircuitBreaker:
        """
        Get or create circuit breaker for service.

        Args:
            service_name: Name of service
            config: Optional configuration

        Returns:
            CircuitBreaker instance
        """
        with self._lock:
            if service_name not in self.breakers:
                self.breakers[service_name] = CircuitBreaker(service_name, config)
            return self.breakers[service_name]

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers."""
        with self._lock:
            return {
                name: {
                    "state": breaker.state.value,
                    "total_calls": breaker.stats.total_calls,
                    "successful_calls": breaker.stats.successful_calls,
                    "failed_calls": breaker.stats.failed_calls,
                    "blocked_calls": breaker.stats.blocked_calls,
                    "state_changes": breaker.stats.state_changes,
                    "last_failure": breaker.stats.last_failure_error,
                }
                for name, breaker in self.breakers.items()
            }

    def reset_breaker(self, service_name: str):
        """Reset circuit breaker (move to CLOSED)."""
        with self._lock:
            if service_name in self.breakers:
                self.breakers[service_name]._transition_to_closed()
                logger.info("Circuit breaker %s manually reset", service_name)


_global_manager = None
_manager_lock = Lock()


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get global circuit breaker manager instance (singleton)."""
    global _global_manager
    if _global_manager is None:
        with _manager_lock:
            if _global_manager is None:
                _global_manager = CircuitBreakerManager()
    return _global_manager
