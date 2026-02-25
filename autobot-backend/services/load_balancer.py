# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Worker Load Balancing Service

Provides comprehensive load balancing for distributing NPU tasks across multiple workers.

Features:
- Multiple load balancing strategies (Round-Robin, Least-Loaded, Weighted, Priority-Failover)
- Health monitoring with circuit breaker pattern
- Worker status tracking and management
- WebSocket event broadcasting for status changes
- Automatic failover and recovery
- Retry logic for failed tasks

Architecture:
- Worker Registry: Manages worker pool and state
- Load Balancing Strategies: Pluggable strategy pattern
- Health Monitor: Background task for worker health checks
- Circuit Breaker: Automatic failure detection and recovery
"""

import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

from constants.threshold_constants import RetryConfig, TimingConstants
from event_manager import event_manager
from npu_integration import NPUWorkerClient
from type_defs.common import Metadata

logger = logging.getLogger(__name__)


# ==============================================
# MODELS AND ENUMS
# ==============================================


class WorkerStatus(str, Enum):
    """Worker operational status"""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    ERROR = "error"


class CircuitBreakerState(str, Enum):
    """Circuit breaker states for fault tolerance"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class Worker:
    """
    NPU Worker representation with health tracking and circuit breaker.

    Attributes:
        worker_id: Unique identifier for the worker
        endpoint: Full URL endpoint for the worker (see ServiceURLs.NPU_WORKER_SERVICE)
        status: Current operational status
        max_concurrent_tasks: Maximum number of concurrent tasks this worker can handle
        priority: Worker priority for weighted distribution (higher = more preferred)
        enabled: Whether worker is enabled for task distribution
        current_load: Number of currently active tasks
        total_tasks_completed: Total successful tasks completed
        total_tasks_failed: Total failed tasks
        consecutive_failures: Number of consecutive failures (for circuit breaker)
        last_health_check: Timestamp of last health check
        last_success: Timestamp of last successful task
        circuit_breaker_state: Current circuit breaker state
        circuit_open_until: Timestamp when circuit breaker can attempt recovery
    """

    worker_id: str
    endpoint: str
    status: WorkerStatus = WorkerStatus.OFFLINE
    max_concurrent_tasks: int = 3
    priority: int = 1
    enabled: bool = True
    current_load: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    consecutive_failures: int = 0
    last_health_check: Optional[datetime] = None
    last_success: Optional[datetime] = None
    circuit_breaker_state: CircuitBreakerState = CircuitBreakerState.CLOSED
    circuit_open_until: Optional[datetime] = None

    def is_available(self) -> bool:
        """Check if worker is available for new tasks"""
        return (
            self.enabled
            and self.status == WorkerStatus.ONLINE
            and self.current_load < self.max_concurrent_tasks
            and self.circuit_breaker_state == CircuitBreakerState.CLOSED
        )

    def can_accept_task(self) -> bool:
        """Check if worker can accept a new task (includes HALF_OPEN state for testing)"""
        return (
            self.enabled
            and self.status in (WorkerStatus.ONLINE, WorkerStatus.BUSY)
            and self.current_load < self.max_concurrent_tasks
            and self.circuit_breaker_state
            in (CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN)
        )

    def record_success(self):
        """Record successful task completion"""
        self.current_load = max(0, self.current_load - 1)
        self.total_tasks_completed += 1
        self.consecutive_failures = 0
        self.last_success = datetime.now()
        # Close circuit breaker on success
        if self.circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            self.circuit_breaker_state = CircuitBreakerState.CLOSED
            self.circuit_open_until = None

    def record_failure(
        self, circuit_breaker_threshold: int = 3, circuit_breaker_timeout: int = 300
    ):
        """Record task failure and update circuit breaker"""
        self.current_load = max(0, self.current_load - 1)
        self.total_tasks_failed += 1
        self.consecutive_failures += 1

        # Open circuit breaker if threshold reached
        if self.consecutive_failures >= circuit_breaker_threshold:
            self.circuit_breaker_state = CircuitBreakerState.OPEN
            self.circuit_open_until = datetime.now() + timedelta(
                seconds=circuit_breaker_timeout
            )
            self.status = WorkerStatus.ERROR
            logger.warning(
                f"Circuit breaker OPEN for worker {self.worker_id} after "
                f"{self.consecutive_failures} failures. Will retry at {self.circuit_open_until}"
            )

    def check_circuit_breaker_recovery(self):
        """Check if circuit breaker can transition from OPEN to HALF_OPEN"""
        if self.circuit_breaker_state == CircuitBreakerState.OPEN:
            if self.circuit_open_until and datetime.now() >= self.circuit_open_until:
                self.circuit_breaker_state = CircuitBreakerState.HALF_OPEN
                logger.info(
                    f"Circuit breaker HALF_OPEN for worker {self.worker_id}, allowing test requests"
                )

    def handle_healthy_check(self) -> bool:
        """Handle successful health check result (Issue #372 - reduces feature envy).

        Returns:
            True if circuit breaker was closed (status changed significantly).
        """
        self.last_health_check = datetime.now()
        self.status = WorkerStatus.ONLINE
        self.consecutive_failures = 0

        # Close circuit breaker if in HALF_OPEN state
        if self.circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            self.circuit_breaker_state = CircuitBreakerState.CLOSED
            self.circuit_open_until = None
            return True
        return False

    def handle_unhealthy_check(
        self, circuit_breaker_threshold: int, circuit_breaker_timeout: int
    ):
        """Handle failed health check result (Issue #372 - reduces feature envy).

        Args:
            circuit_breaker_threshold: Number of failures before opening circuit
            circuit_breaker_timeout: Seconds before circuit can attempt recovery
        """
        self.last_health_check = datetime.now()
        self.consecutive_failures += 1

        if self.consecutive_failures >= circuit_breaker_threshold:
            self.status = WorkerStatus.ERROR
            self.circuit_breaker_state = CircuitBreakerState.OPEN
            self.circuit_open_until = datetime.now() + timedelta(
                seconds=circuit_breaker_timeout
            )
        else:
            self.status = WorkerStatus.OFFLINE

    def to_status_event_dict(self, reason: str) -> Metadata:
        """Convert to dictionary for status change event (Issue #372 - reduces feature envy).

        Args:
            reason: Reason for the status change event.

        Returns:
            Dictionary suitable for WebSocket event publishing.
        """
        return {
            "worker_id": self.worker_id,
            "status": self.status.value,
            "circuit_breaker_state": self.circuit_breaker_state.value,
            "current_load": self.current_load,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        }

    def to_dict(self) -> Metadata:
        """Serialize worker to dictionary"""
        return {
            "worker_id": self.worker_id,
            "endpoint": self.endpoint,
            "status": self.status.value,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "priority": self.priority,
            "enabled": self.enabled,
            "current_load": self.current_load,
            "total_tasks_completed": self.total_tasks_completed,
            "total_tasks_failed": self.total_tasks_failed,
            "consecutive_failures": self.consecutive_failures,
            "last_health_check": (
                self.last_health_check.isoformat() if self.last_health_check else None
            ),
            "last_success": (
                self.last_success.isoformat() if self.last_success else None
            ),
            "circuit_breaker_state": self.circuit_breaker_state.value,
            "circuit_open_until": (
                self.circuit_open_until.isoformat() if self.circuit_open_until else None
            ),
        }


# ==============================================
# LOAD BALANCING STRATEGIES
# ==============================================


class LoadBalancingStrategy(ABC):
    """Abstract base class for load balancing strategies"""

    @abstractmethod
    def select_worker(self, workers: List[Worker]) -> Optional[Worker]:
        """
        Select a worker from available workers.

        Args:
            workers: List of available workers

        Returns:
            Selected worker or None if no worker available
        """


class RoundRobinStrategy(LoadBalancingStrategy):
    """Round-robin load balancing strategy"""

    def __init__(self):
        """Initialize round-robin strategy with starting index."""
        self._last_index = -1

    def select_worker(self, workers: List[Worker]) -> Optional[Worker]:
        """Select next worker in round-robin fashion"""
        if not workers:
            return None

        # Filter available workers
        available = [w for w in workers if w.is_available()]
        if not available:
            return None

        # Select next in round-robin
        self._last_index = (self._last_index + 1) % len(available)
        return available[self._last_index]


class LeastLoadedStrategy(LoadBalancingStrategy):
    """Least-loaded load balancing strategy"""

    def select_worker(self, workers: List[Worker]) -> Optional[Worker]:
        """Select worker with lowest current load"""
        if not workers:
            return None

        # Filter available workers
        available = [w for w in workers if w.is_available()]
        if not available:
            return None

        # Select worker with minimum load
        return min(available, key=lambda w: w.current_load)


class WeightedStrategy(LoadBalancingStrategy):
    """Weighted load balancing based on worker priority"""

    def select_worker(self, workers: List[Worker]) -> Optional[Worker]:
        """Select worker based on priority weights"""
        if not workers:
            return None

        # Filter available workers
        available = [w for w in workers if w.is_available()]
        if not available:
            return None

        # Sort by priority (higher priority first), then by load (lower load first)
        sorted_workers = sorted(available, key=lambda w: (-w.priority, w.current_load))
        return sorted_workers[0]


class PriorityFailoverStrategy(LoadBalancingStrategy):
    """Priority-based failover strategy"""

    def select_worker(self, workers: List[Worker]) -> Optional[Worker]:
        """Select highest priority available worker (primary with failover)"""
        if not workers:
            return None

        # Filter available workers
        available = [w for w in workers if w.is_available()]
        if not available:
            return None

        # Sort by priority descending (highest priority first)
        sorted_workers = sorted(available, key=lambda w: -w.priority)
        return sorted_workers[0]


# ==============================================
# LOAD BALANCER SERVICE
# ==============================================


class NPULoadBalancer:
    """
    NPU Worker Load Balancer

    Manages multiple NPU workers with health monitoring, load balancing,
    and automatic failover capabilities.
    """

    def __init__(
        self,
        strategy: str = "round_robin",
        health_check_interval: int = 30,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_timeout: int = 300,
    ):
        """
        Initialize NPU Load Balancer.

        Args:
            strategy: Load balancing strategy ("round_robin", "least_loaded", "weighted", "priority_failover")
            health_check_interval: Seconds between health checks (default: 30)
            circuit_breaker_threshold: Consecutive failures before opening circuit (default: 3)
            circuit_breaker_timeout: Seconds to wait before attempting recovery (default: 300 = 5 minutes)
        """
        self._workers: Dict[str, Worker] = {}
        self._strategy = self._create_strategy(strategy)
        self._health_check_interval = health_check_interval
        self._circuit_breaker_threshold = circuit_breaker_threshold
        self._circuit_breaker_timeout = circuit_breaker_timeout
        self._health_monitor_task: Optional[asyncio.Task] = None
        self._running = False
        self._selection_lock = asyncio.Lock()
        self._workers_lock = (
            threading.Lock()
        )  # CRITICAL: Protect concurrent worker dictionary access

        logger.info(
            f"NPU Load Balancer initialized with {strategy} strategy, "
            f"health check every {health_check_interval}s"
        )

    def _create_strategy(self, strategy_name: str) -> LoadBalancingStrategy:
        """Create load balancing strategy instance"""
        strategies = {
            "round_robin": RoundRobinStrategy,
            "least_loaded": LeastLoadedStrategy,
            "weighted": WeightedStrategy,
            "priority_failover": PriorityFailoverStrategy,
        }

        strategy_class = strategies.get(strategy_name.lower())
        if not strategy_class:
            logger.warning("Unknown strategy '%s', using round_robin", strategy_name)
            strategy_class = RoundRobinStrategy

        return strategy_class()

    def add_worker(
        self,
        worker_id: str,
        endpoint: str,
        max_concurrent_tasks: int = 3,
        priority: int = 1,
        enabled: bool = True,
    ) -> Worker:
        """
        Add a new worker to the pool.

        Args:
            worker_id: Unique identifier for the worker
            endpoint: Full URL endpoint (see ServiceURLs.NPU_WORKER_SERVICE)
            max_concurrent_tasks: Maximum concurrent tasks for this worker
            priority: Worker priority (higher = more preferred)
            enabled: Whether worker is enabled

        Returns:
            Worker instance
        """
        worker = Worker(
            worker_id=worker_id,
            endpoint=endpoint,
            max_concurrent_tasks=max_concurrent_tasks,
            priority=priority,
            enabled=enabled,
        )
        # CRITICAL: Protect worker dictionary modifications with lock
        with self._workers_lock:
            self._workers[worker_id] = worker
        logger.info(
            f"Added worker {worker_id} at {endpoint} (priority={priority}, max_tasks={max_concurrent_tasks})"
        )
        return worker

    def remove_worker(self, worker_id: str) -> bool:
        """
        Remove a worker from the pool.

        Args:
            worker_id: Worker to remove

        Returns:
            True if removed, False if not found
        """
        # CRITICAL: Atomic check-and-delete with lock to prevent race conditions
        with self._workers_lock:
            if worker_id in self._workers:
                del self._workers[worker_id]
                logger.info("Removed worker %s", worker_id)
                return True
        return False

    def get_worker(self, worker_id: str) -> Optional[Worker]:
        """Get worker by ID"""
        with self._workers_lock:
            return self._workers.get(worker_id)

    def get_all_workers(self) -> List[Worker]:
        """Get all workers"""
        with self._workers_lock:
            return list(self._workers.values())

    async def select_worker(self) -> Optional[Worker]:
        """
        Select best worker for new task using configured strategy.

        Returns:
            Selected worker or None if no worker available
        """
        async with self._selection_lock:
            # CRITICAL: Snapshot workers under lock to prevent race conditions
            with self._workers_lock:
                workers = list(self._workers.values())

            if not workers:
                logger.warning("No workers registered")
                return None

            # Check circuit breaker recovery for all workers
            for worker in workers:
                worker.check_circuit_breaker_recovery()

            # Use strategy to select worker
            selected = self._strategy.select_worker(workers)

            if selected:
                selected.current_load += 1
                logger.debug(
                    f"Selected worker {selected.worker_id} (load={selected.current_load}/"
                    f"{selected.max_concurrent_tasks})"
                )
            else:
                logger.warning("No available workers for task")

            return selected

    async def submit_task(
        self,
        worker_id: str,
        task_type: str,
        task_data: Metadata,
        max_retries: int = RetryConfig.MIN_RETRIES,
    ) -> Metadata:
        """Submit task to specific worker with retry logic. Ref: #1088."""
        worker = self.get_worker(worker_id)
        if not worker:
            return {"success": False, "error": f"Worker {worker_id} not found"}

        if not worker.can_accept_task():
            return {
                "success": False,
                "error": f"Worker {worker_id} cannot accept tasks",
            }

        # Create NPU client for this worker
        client = NPUWorkerClient(npu_endpoint=worker.endpoint)

        try:
            # Execute task via NPU client
            result = await client.offload_heavy_processing(task_type, task_data)

            # Record result
            if result.get("success"):
                worker.record_success()
                await self._emit_worker_status_change(worker, "task_completed")
            else:
                worker.record_failure(
                    self._circuit_breaker_threshold, self._circuit_breaker_timeout
                )
                await self._emit_worker_status_change(worker, "task_failed")

                # Retry on different worker if configured
                if max_retries > 0 and result.get("fallback"):
                    logger.info(
                        f"Retrying task on different worker (retries left: {max_retries})"
                    ),
                    alternative = await self.select_worker()
                    if alternative and alternative.worker_id != worker_id:
                        return await self.submit_task(
                            alternative.worker_id, task_type, task_data, max_retries - 1
                        )

            return result

        except Exception as e:
            logger.error("Task execution error on worker %s: %s", worker_id, e)
            worker.record_failure(
                self._circuit_breaker_threshold, self._circuit_breaker_timeout
            )
            await self._emit_worker_status_change(worker, "task_error")
            return {"success": False, "error": str(e)}
        finally:
            await client.close()

    async def get_worker_status(self, worker_id: str) -> Optional[Metadata]:
        """
        Get status of specific worker.

        Args:
            worker_id: Worker ID

        Returns:
            Worker status dictionary or None if not found
        """
        worker = self.get_worker(worker_id)
        return worker.to_dict() if worker else None

    async def get_all_workers_status(self) -> List[Metadata]:
        """
        Get status of all workers.

        Returns:
            List of worker status dictionaries
        """
        # CRITICAL: Snapshot workers under lock to prevent race conditions
        with self._workers_lock:
            workers = list(self._workers.values())
        return [worker.to_dict() for worker in workers]

    async def start_health_monitoring(self):
        """Start background health monitoring task"""
        if self._running:
            logger.warning("Health monitoring already running")
            return

        self._running = True
        self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Started NPU worker health monitoring")

    async def stop_health_monitoring(self):
        """Stop background health monitoring task"""
        self._running = False
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                logger.debug("Health monitor task cancelled")
            self._health_monitor_task = None
        logger.info("Stopped NPU worker health monitoring")

    async def _health_monitor_loop(self):
        """Background task for periodic health checks"""
        logger.info("Health monitor loop started")

        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)

                # CRITICAL: Snapshot workers under lock to prevent race conditions
                with self._workers_lock:
                    workers = list(self._workers.values())

                if workers:
                    # Check all workers in parallel - eliminates N+1 sequential calls
                    await asyncio.gather(
                        *[self._check_worker_health(worker) for worker in workers],
                        return_exceptions=True,
                    )

            except asyncio.CancelledError:
                logger.info("Health monitor loop cancelled")
                break
            except Exception as e:
                logger.error("Error in health monitor loop: %s", e, exc_info=True)
                # Error recovery delay before continuing monitoring
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)

    async def _check_worker_health(self, worker: Worker):
        """
        Check health of a single worker (Issue #372 - uses model methods).

        Args:
            worker: Worker to check
        """
        if not worker.enabled:
            return

        client = NPUWorkerClient(npu_endpoint=worker.endpoint)
        try:
            health = await client.check_health()
            previous_status = worker.status

            # Update worker status based on health check using model methods
            if health.get("status") == "healthy":
                circuit_closed = worker.handle_healthy_check()
                if circuit_closed:
                    logger.info(
                        f"Circuit breaker CLOSED for worker {worker.worker_id} after successful health check"
                    )
            else:
                worker.handle_unhealthy_check(
                    self._circuit_breaker_threshold, self._circuit_breaker_timeout
                )

            # Emit status change event if status changed
            if previous_status != worker.status:
                await self._emit_worker_status_change(worker, "health_check")

        except Exception as e:
            logger.warning("Health check failed for worker %s: %s", worker.worker_id, e)
            previous_status = worker.status
            worker.handle_unhealthy_check(
                self._circuit_breaker_threshold, self._circuit_breaker_timeout
            )

            # Emit event if circuit breaker opened
            if (
                worker.circuit_breaker_state == CircuitBreakerState.OPEN
                and previous_status != worker.status
            ):
                await self._emit_worker_status_change(worker, "circuit_breaker_opened")

        finally:
            await client.close()

    async def _emit_worker_status_change(self, worker: Worker, reason: str):
        """
        Emit WebSocket event for worker status change (Issue #372 - uses model method).

        Args:
            worker: Worker that changed status
            reason: Reason for status change
        """
        try:
            await event_manager.publish(
                "npu_worker_status_change",
                worker.to_status_event_dict(reason),
            )
        except Exception as e:
            logger.error("Failed to emit worker status change event: %s", e)


# ==============================================
# GLOBAL INSTANCE
# ==============================================

# Global load balancer instance with thread-safe initialization (Issue #662)
_global_load_balancer: Optional[NPULoadBalancer] = None
_load_balancer_lock = threading.Lock()


def get_load_balancer(
    strategy: str = "round_robin",
    health_check_interval: int = 30,
    circuit_breaker_threshold: int = 3,
    circuit_breaker_timeout: int = 300,
) -> NPULoadBalancer:
    """
    Get or create global load balancer instance (thread-safe).

    Args:
        strategy: Load balancing strategy
        health_check_interval: Health check interval in seconds
        circuit_breaker_threshold: Failures before circuit opens
        circuit_breaker_timeout: Circuit breaker timeout in seconds

    Returns:
        Global NPULoadBalancer instance
    """
    global _global_load_balancer
    if _global_load_balancer is None:
        with _load_balancer_lock:
            # Double-check after acquiring lock
            if _global_load_balancer is None:
                _global_load_balancer = NPULoadBalancer(
                    strategy=strategy,
                    health_check_interval=health_check_interval,
                    circuit_breaker_threshold=circuit_breaker_threshold,
                    circuit_breaker_timeout=circuit_breaker_timeout,
                )
    return _global_load_balancer
