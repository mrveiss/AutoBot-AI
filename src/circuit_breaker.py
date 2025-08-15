#!/usr/bin/env python3
"""
Circuit Breaker pattern implementation for AutoBot
Prevents cascading failures by automatically stopping calls to failing services
"""

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, rejecting calls
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""

    failure_threshold: int = 5  # Number of failures to open circuit
    recovery_timeout: float = 60.0  # Seconds before trying half-open
    success_threshold: int = 3  # Successes needed to close circuit from half-open
    timeout: float = 30.0  # Call timeout in seconds

    # Exceptions that should trigger circuit breaker
    monitored_exceptions: tuple = (
        ConnectionError,
        TimeoutError,
        OSError,
        Exception,  # Broad for now, should be more specific per service
    )

    # Exceptions that should NOT trigger circuit breaker
    non_monitored_exceptions: tuple = (
        KeyboardInterrupt,
        SystemExit,
        ValueError,  # Business logic errors
        TypeError,
        AttributeError,
    )

    # Performance thresholds
    slow_call_threshold: float = 10.0  # Seconds - what constitutes a slow call
    slow_call_rate_threshold: float = 0.5  # 50% of calls being slow opens circuit
    min_calls_for_evaluation: int = 10  # Minimum calls before evaluating performance


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking calls"""

    def __init__(self, service_name: str, failure_count: int, last_failure_time: float):
        self.service_name = service_name
        self.failure_count = failure_count
        self.last_failure_time = last_failure_time
        super().__init__(
            f"Circuit breaker for {service_name} is OPEN "
            f"({failure_count} failures, last failure {time.time() - last_failure_time:.1f}s ago)"
        )


@dataclass
class CallRecord:
    """Record of a service call"""

    timestamp: float
    duration: float
    success: bool
    exception_type: Optional[str] = None


class CircuitBreaker:
    """Circuit breaker implementation with performance monitoring"""

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.state_change_time = time.time()

        # Call history for performance monitoring
        self.call_history: List[CallRecord] = []
        self.max_history_size = 100

        # Thread safety
        self._lock = Lock()

        # Statistics
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "blocked_calls": 0,
            "state_changes": 0,
            "average_response_time": 0.0,
            "slow_calls": 0,
        }

    def _should_monitor_exception(self, exception: Exception) -> bool:
        """Check if an exception should trigger circuit breaker logic"""
        if isinstance(exception, self.config.non_monitored_exceptions):
            return False
        return isinstance(exception, self.config.monitored_exceptions)

    def _add_call_record(
        self, duration: float, success: bool, exception_type: str = None
    ):
        """Add a call record to history"""
        with self._lock:
            record = CallRecord(
                timestamp=time.time(),
                duration=duration,
                success=success,
                exception_type=exception_type,
            )

            self.call_history.append(record)

            # Maintain history size limit
            if len(self.call_history) > self.max_history_size:
                self.call_history = self.call_history[-self.max_history_size :]

            # Update statistics
            self.stats["total_calls"] += 1
            if success:
                self.stats["successful_calls"] += 1
            else:
                self.stats["failed_calls"] += 1

            if duration > self.config.slow_call_threshold:
                self.stats["slow_calls"] += 1

    def _evaluate_performance(self) -> bool:
        """Evaluate if performance metrics indicate the service should be opened"""
        try:
            if len(self.call_history) < self.config.min_calls_for_evaluation:
                return False

            current_time = time.time()
            recent_calls = [
                record
                for record in self.call_history
                if current_time - record.timestamp < 60.0  # Last 60 seconds
            ]

            if len(recent_calls) < self.config.min_calls_for_evaluation:
                return False

            # Check slow call rate
            slow_calls = sum(
                1
                for call in recent_calls
                if call.duration > self.config.slow_call_threshold
            )
            slow_call_rate = slow_calls / len(recent_calls) if recent_calls else 0.0

            if slow_call_rate >= self.config.slow_call_rate_threshold:
                logger.warning(
                    f"Circuit breaker {self.name}: High slow call rate {slow_call_rate:.1%}"
                )
                return True

            return False
        except Exception:
            # If performance evaluation fails, don't open circuit based on performance
            return False

    def _can_execute(self) -> bool:
        """Check if a call can be executed based on current circuit state"""
        current_time = time.time()

        if self.state == CircuitState.CLOSED:
            return True

        elif self.state == CircuitState.OPEN:
            # Check if enough time has passed to try half-open
            if current_time - self.last_failure_time >= self.config.recovery_timeout:
                with self._lock:
                    if self.state == CircuitState.OPEN:  # Double-check with lock
                        logger.info(
                            f"Circuit breaker {self.name}: Transitioning to HALF_OPEN"
                        )
                        self.state = CircuitState.HALF_OPEN
                        self.state_change_time = current_time
                        self.stats["state_changes"] += 1
                        return True
            return False

        elif self.state == CircuitState.HALF_OPEN:
            # Allow limited calls to test service recovery
            return True

        return False

    def _record_success(self, duration: float):
        """Record a successful call"""
        with self._lock:
            self._add_call_record(duration, success=True)

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.debug(
                    f"Circuit breaker {self.name}: Success in HALF_OPEN ({self.success_count}/{self.config.success_threshold})"
                )

                if self.success_count >= self.config.success_threshold:
                    logger.info(f"Circuit breaker {self.name}: Transitioning to CLOSED")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.state_change_time = time.time()
                    self.stats["state_changes"] += 1

            # Reset failure count on successful call in CLOSED state
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)

    def _record_failure(self, duration: float, exception: Exception):
        """Record a failed call"""
        if not self._should_monitor_exception(exception):
            # Don't count this as a circuit breaker failure
            self._add_call_record(
                duration, success=False, exception_type=type(exception).__name__
            )
            return

        with self._lock:
            self._add_call_record(
                duration, success=False, exception_type=type(exception).__name__
            )
            self.failure_count += 1
            self.last_failure_time = time.time()

            logger.debug(
                f"Circuit breaker {self.name}: Failure recorded ({self.failure_count}/{self.config.failure_threshold})"
            )

            # Check if we should open the circuit
            should_open = (
                self.failure_count >= self.config.failure_threshold
                or self._evaluate_performance()
            )

            if should_open and self.state != CircuitState.OPEN:
                logger.warning(
                    f"Circuit breaker {self.name}: Opening circuit after {self.failure_count} failures"
                )
                self.state = CircuitState.OPEN
                self.success_count = 0
                self.state_change_time = time.time()
                self.stats["state_changes"] += 1

            elif self.state == CircuitState.HALF_OPEN:
                # Any failure in half-open state opens the circuit
                logger.warning(
                    f"Circuit breaker {self.name}: Opening circuit due to failure in HALF_OPEN"
                )
                self.state = CircuitState.OPEN
                self.success_count = 0
                self.state_change_time = time.time()
                self.stats["state_changes"] += 1

    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute an async function through the circuit breaker"""
        if not self._can_execute():
            self.stats["blocked_calls"] += 1
            raise CircuitBreakerOpenError(
                self.name, self.failure_count, self.last_failure_time
            )

        start_time = time.time()

        try:
            # Execute with timeout
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(
                    func(*args, **kwargs), timeout=self.config.timeout
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(func, *args, **kwargs),
                    timeout=self.config.timeout,
                )

            duration = time.time() - start_time
            self._record_success(duration)
            return result

        except asyncio.TimeoutError as e:
            duration = time.time() - start_time
            timeout_error = TimeoutError(
                f"Call to {self.name} timed out after {self.config.timeout}s"
            )
            self._record_failure(duration, timeout_error)
            raise timeout_error

        except Exception as e:
            duration = time.time() - start_time
            self._record_failure(duration, e)
            raise e

    def call_sync(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a synchronous function through the circuit breaker"""
        if not self._can_execute():
            self.stats["blocked_calls"] += 1
            raise CircuitBreakerOpenError(
                self.name, self.failure_count, self.last_failure_time
            )

        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            self._record_success(duration)
            return result

        except Exception as e:
            duration = time.time() - start_time
            self._record_failure(duration, e)
            raise e

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state"""
        current_time = time.time()

        # Calculate average response time
        if self.call_history:
            successful_calls = [r for r in self.call_history if r.success]
            if successful_calls:
                avg_response_time = statistics.mean(
                    r.duration for r in successful_calls
                )
            else:
                avg_response_time = 0.0
        else:
            avg_response_time = 0.0

        self.stats["average_response_time"] = avg_response_time

        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "time_since_last_failure": current_time - self.last_failure_time
            if self.last_failure_time
            else None,
            "time_in_current_state": current_time - self.state_change_time,
            "can_execute": self._can_execute(),
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout,
            },
            "stats": self.stats.copy(),
            "recent_performance": self._get_recent_performance(),
        }

    def _get_recent_performance(self) -> Dict[str, Any]:
        """Get recent performance metrics"""
        recent_calls = [
            record
            for record in self.call_history
            if time.time() - record.timestamp < 300.0  # Last 5 minutes
        ]

        if not recent_calls:
            return {"calls": 0}

        successful = sum(1 for call in recent_calls if call.success)
        slow_calls = sum(
            1
            for call in recent_calls
            if call.duration > self.config.slow_call_threshold
        )

        durations = [call.duration for call in recent_calls if call.success]
        avg_duration = statistics.mean(durations) if durations else 0.0

        # Calculate p95 duration safely
        p95_duration = avg_duration
        if len(durations) >= 20:
            try:
                quantiles = statistics.quantiles(durations, n=20)
                p95_duration = quantiles[18] if len(quantiles) > 18 else avg_duration
            except Exception:
                p95_duration = avg_duration

        return {
            "calls": len(recent_calls),
            "success_rate": successful / len(recent_calls),
            "slow_call_rate": slow_calls / len(recent_calls),
            "average_duration": avg_duration,
            "p95_duration": p95_duration,
        }

    def reset(self):
        """Reset circuit breaker to closed state"""
        with self._lock:
            logger.info(f"Circuit breaker {self.name}: Manual reset to CLOSED")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = 0.0
            self.state_change_time = time.time()
            self.call_history.clear()
            self.stats = {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "blocked_calls": 0,
                "state_changes": self.stats["state_changes"] + 1,
                "average_response_time": 0.0,
                "slow_calls": 0,
            }


class CircuitBreakerManager:
    """Manages multiple circuit breakers for different services"""

    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._lock = Lock()

    def get_circuit_breaker(
        self, service_name: str, config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get or create a circuit breaker for a service"""
        if service_name not in self.circuit_breakers:
            with self._lock:
                if service_name not in self.circuit_breakers:
                    self.circuit_breakers[service_name] = CircuitBreaker(
                        service_name, config
                    )

        return self.circuit_breakers[service_name]

    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get states of all circuit breakers"""
        return {name: cb.get_state() for name, cb in self.circuit_breakers.items()}

    def reset_circuit_breaker(self, service_name: str):
        """Reset a specific circuit breaker"""
        if service_name in self.circuit_breakers:
            self.circuit_breakers[service_name].reset()

    def reset_all_circuit_breakers(self):
        """Reset all circuit breakers"""
        for cb in self.circuit_breakers.values():
            cb.reset()


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()


def circuit_breaker_async(
    service_name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    success_threshold: int = 3,
    timeout: float = 30.0,
    monitored_exceptions: tuple = None,
):
    """
    Decorator for async functions with circuit breaker protection

    Args:
        service_name: Name of the service for circuit breaker identification
        failure_threshold: Number of failures to open circuit
        recovery_timeout: Seconds before trying half-open
        success_threshold: Successes needed to close circuit from half-open
        timeout: Call timeout in seconds
        monitored_exceptions: Tuple of exceptions that should trigger circuit breaker
    """

    def decorator(func):
        config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            success_threshold=success_threshold,
            timeout=timeout,
        )

        if monitored_exceptions:
            config.monitored_exceptions = monitored_exceptions

        circuit_breaker = circuit_breaker_manager.get_circuit_breaker(
            service_name, config
        )

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await circuit_breaker.call_async(func, *args, **kwargs)

        wrapper.circuit_breaker = circuit_breaker  # Allow access to circuit breaker
        return wrapper

    return decorator


def circuit_breaker_sync(
    service_name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    success_threshold: int = 3,
    timeout: float = 30.0,
    monitored_exceptions: tuple = None,
):
    """
    Decorator for sync functions with circuit breaker protection

    Args:
        service_name: Name of the service for circuit breaker identification
        failure_threshold: Number of failures to open circuit
        recovery_timeout: Seconds before trying half-open
        success_threshold: Successes needed to close circuit from half-open
        timeout: Call timeout in seconds
        monitored_exceptions: Tuple of exceptions that should trigger circuit breaker
    """

    def decorator(func):
        config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            success_threshold=success_threshold,
            timeout=timeout,
        )

        if monitored_exceptions:
            config.monitored_exceptions = monitored_exceptions

        circuit_breaker = circuit_breaker_manager.get_circuit_breaker(
            service_name, config
        )

        @wraps(func)
        def wrapper(*args, **kwargs):
            return circuit_breaker.call_sync(func, *args, **kwargs)

        wrapper.circuit_breaker = circuit_breaker  # Allow access to circuit breaker
        return wrapper

    return decorator


# Convenience functions for AutoBot services
async def protected_llm_call(func: Callable, *args, **kwargs) -> Any:
    """Make an LLM call protected by circuit breaker"""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=30.0,
        timeout=120.0,  # LLM calls can be slow
        monitored_exceptions=(ConnectionError, TimeoutError, OSError),
    )

    circuit_breaker = circuit_breaker_manager.get_circuit_breaker("llm_service", config)
    return await circuit_breaker.call_async(func, *args, **kwargs)


async def protected_database_call(func: Callable, *args, **kwargs) -> Any:
    """Make a database call protected by circuit breaker"""
    config = CircuitBreakerConfig(
        failure_threshold=5,
        recovery_timeout=15.0,
        timeout=10.0,
        slow_call_threshold=2.0,  # Database calls should be fast
        monitored_exceptions=(ConnectionError, TimeoutError, OSError),
    )

    circuit_breaker = circuit_breaker_manager.get_circuit_breaker(
        "database_service", config
    )
    return await circuit_breaker.call_async(func, *args, **kwargs)


async def protected_network_call(func: Callable, *args, **kwargs) -> Any:
    """Make a network call protected by circuit breaker"""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=20.0,
        timeout=15.0,
        monitored_exceptions=(ConnectionError, TimeoutError, OSError),
    )

    circuit_breaker = circuit_breaker_manager.get_circuit_breaker(
        "network_service", config
    )
    return await circuit_breaker.call_async(func, *args, **kwargs)


if __name__ == "__main__":
    # Example usage and testing
    async def example_usage():
        """Example usage of circuit breaker"""

        # Example 1: Using decorator
        @circuit_breaker_async(
            "flaky_service", failure_threshold=3, recovery_timeout=5.0
        )
        async def flaky_service_call():
            import random

            if random.random() < 0.6:  # 60% chance of failure
                raise ConnectionError("Service unavailable")
            return "Service response"

        # Try calling the service multiple times
        for i in range(10):
            try:
                result = await flaky_service_call()
                print(f"Call {i+1}: Success - {result}")
            except (ConnectionError, CircuitBreakerOpenError) as e:
                print(f"Call {i+1}: Failed - {type(e).__name__}: {e}")

            await asyncio.sleep(1)

        # Check circuit breaker state
        cb_state = flaky_service_call.circuit_breaker.get_state()
        print(f"\\nCircuit breaker state: {cb_state['state']}")
        print(
            f"Success rate: {cb_state['recent_performance'].get('success_rate', 0):.1%}"
        )

    # Run example
    asyncio.run(example_usage())
