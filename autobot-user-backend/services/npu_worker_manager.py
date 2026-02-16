# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Worker Registry and Management Service

Manages NPU worker registration, health monitoring, and state tracking.
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import yaml
from event_manager import event_manager
from npu_integration import NPUWorkerClient

from backend.constants.threshold_constants import TimingConstants
from backend.models.npu_models import (
    LoadBalancingConfig,
    NPUWorkerConfig,
    NPUWorkerDetails,
    NPUWorkerMetrics,
    NPUWorkerStatus,
    WorkerStatus,
    WorkerTestResult,
)

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for worker events that include full data
_WORKER_FULL_DATA_EVENTS = frozenset({"worker.added", "worker.updated"})


class NPUWorkerManager:
    """
    Manages NPU worker registry with persistent storage and runtime state tracking.

    Features:
    - Worker registration and configuration management
    - Health monitoring with background checks
    - Runtime status tracking in Redis
    - Performance metrics collection
    - YAML-based persistent storage
    """

    # Issue #699: Constants for exponential backoff on unavailable workers
    _MIN_BACKOFF_MULTIPLIER = 1
    _MAX_BACKOFF_MULTIPLIER = 8  # Max 8x the health check interval (4 minutes at 30s)

    def __init__(self, config_file: Path = None, redis_client=None):
        """
        Initialize NPU Worker Manager.

        Args:
            config_file: Path to worker configuration YAML file
            redis_client: Redis client for state storage
        """
        self.config_file = config_file or Path("config/npu_workers.yaml")
        self.redis_client = redis_client
        self._workers: Dict[str, NPUWorkerConfig] = {}
        self._worker_clients: Dict[str, NPUWorkerClient] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        self._load_balancing_config = LoadBalancingConfig()

        # Issue #699: Track consecutive failures for exponential backoff
        self._worker_failure_counts: Dict[str, int] = {}
        self._worker_next_check: Dict[str, float] = {}

        # Initialize from config file
        self._load_workers_from_config()

    def _parse_single_worker(self, worker_data: dict) -> bool:
        """Parse and store a single worker configuration (Issue #315: extracted helper).

        Args:
            worker_data: Worker configuration dictionary

        Returns:
            True if successfully parsed, False otherwise
        """
        try:
            worker = NPUWorkerConfig(**worker_data)
            self._workers[worker.id] = worker
            logger.info("Loaded worker config: %s (%s)", worker.id, worker.name)
            return True
        except Exception as e:
            logger.error("Failed to load worker config: %s", e)
            return False

    def _load_workers_from_config(self):
        """Load worker configurations from YAML file"""
        try:
            if not self.config_file.exists():
                logger.warning("Worker config file not found: %s", self.config_file)
                self._save_workers_to_config()
                return

            with open(self.config_file, "r") as f:
                data = yaml.safe_load(f) or {}

            # Load workers using helper (Issue #315: reduced nesting)
            workers_data = data.get("workers", [])
            for worker_data in workers_data:
                self._parse_single_worker(worker_data)

            # Load load balancing config
            lb_config = data.get("load_balancing", {})
            if lb_config:
                self._load_balancing_config = LoadBalancingConfig(**lb_config)

            logger.info("Loaded %s worker configurations", len(self._workers))

        except Exception as e:
            logger.error("Failed to load worker configurations: %s", e)

    async def _save_workers_to_config(self):
        """Save worker configurations to YAML file"""
        try:
            # Ensure config directory exists
            # Issue #358 - avoid blocking
            await asyncio.to_thread(
                self.config_file.parent.mkdir, parents=True, exist_ok=True
            )

            # Prepare data - use mode='json' to serialize enums as strings
            # This prevents !!python/object tags that yaml.safe_load() cannot parse
            data = {
                "workers": [
                    worker.model_dump(mode="json") for worker in self._workers.values()
                ],
                "load_balancing": self._load_balancing_config.model_dump(mode="json"),
            }

            # Write to file asynchronously
            try:
                async with aiofiles.open(self.config_file, "w", encoding="utf-8") as f:
                    await f.write(yaml.dump(data, default_flow_style=False))
            except OSError as e:
                logger.error("Failed to write worker config file: %s", e)
                raise

            logger.info("Saved %s worker configurations", len(self._workers))

        except Exception as e:
            logger.error("Failed to save worker configurations: %s", e)
            raise

    async def start_health_monitoring(self):
        """Start background health monitoring task"""
        if self._running:
            logger.warning("Health monitoring already running")
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Started NPU worker health monitoring")

    async def stop_health_monitoring(self):
        """Stop background health monitoring task"""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                logger.debug("Health check task cancelled")

        # Close all worker clients
        for client in self._worker_clients.values():
            await client.close()
        self._worker_clients.clear()

        logger.info("Stopped NPU worker health monitoring")

    async def _check_single_worker_health(self, worker_id: str) -> None:
        """Check health of a single worker with error handling (Issue #315: extracted helper).

        Args:
            worker_id: ID of worker to check
        """
        try:
            await self._check_worker_health(worker_id)
        except Exception as e:
            # Issue #699: NPU workers are optional - log at DEBUG level to avoid spam
            logger.debug(
                "Health check failed for worker %s: %s (NPU workers are optional - "
                "configure at /settings/infrastructure)",
                worker_id,
                e,
            )

    def _get_backoff_multiplier(self, worker_id: str) -> int:
        """Get backoff multiplier for a worker based on consecutive failures (Issue #699).

        Returns:
            Multiplier for health check interval (1, 2, 4, 8)
        """
        failures = self._worker_failure_counts.get(worker_id, 0)
        # Exponential backoff: 2^failures, capped at MAX_BACKOFF_MULTIPLIER
        multiplier = min(2**failures, self._MAX_BACKOFF_MULTIPLIER)
        return max(multiplier, self._MIN_BACKOFF_MULTIPLIER)

    def _should_check_worker(self, worker_id: str) -> bool:
        """Check if enough time has passed to check this worker again (Issue #699).

        Returns:
            True if worker should be checked, False if still in backoff
        """
        next_check = self._worker_next_check.get(worker_id, 0)
        return time.time() >= next_check

    def _record_worker_failure(self, worker_id: str) -> None:
        """Record a health check failure and schedule next check with backoff (Issue #699)."""
        # Increment failure count
        self._worker_failure_counts[worker_id] = (
            self._worker_failure_counts.get(worker_id, 0) + 1
        )
        # Calculate next check time with backoff
        multiplier = self._get_backoff_multiplier(worker_id)
        interval = self._load_balancing_config.health_check_interval * multiplier
        self._worker_next_check[worker_id] = time.time() + interval

        if multiplier > 1:
            logger.debug(
                "Worker %s: %d consecutive failures, next check in %ds (backoff %dx)",
                worker_id,
                self._worker_failure_counts[worker_id],
                interval,
                multiplier,
            )

    def _record_worker_success(self, worker_id: str) -> None:
        """Reset failure count on successful health check (Issue #699)."""
        if worker_id in self._worker_failure_counts:
            del self._worker_failure_counts[worker_id]
        if worker_id in self._worker_next_check:
            del self._worker_next_check[worker_id]

    async def _health_check_loop(self):
        """Background task that periodically checks worker health"""
        logger.info("NPU worker health check loop started")

        while self._running:
            try:
                # Issue #699: Check all enabled workers with exponential backoff
                enabled_workers = [
                    wid for wid, cfg in self._workers.items() if cfg.enabled
                ]
                for worker_id in enabled_workers:
                    # Skip workers still in backoff period
                    if not self._should_check_worker(worker_id):
                        continue
                    await self._check_single_worker_health(worker_id)

                # Wait for next check interval
                await asyncio.sleep(self._load_balancing_config.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Issue #699: Log at DEBUG for health check loop errors (NPU is optional)
                logger.debug(
                    "Health check loop error: %s (NPU workers are optional)", e
                )
                # Error recovery delay before retry
                await asyncio.sleep(TimingConstants.LONG_DELAY)

    async def _check_worker_health(self, worker_id: str):
        """Check health of a specific worker (Issue #665: refactored with helper)."""
        worker_config = self._workers.get(worker_id)
        if not worker_config:
            return

        # Get previous status for comparison
        prev_status = await self._get_worker_status(worker_id)
        prev_status_value = prev_status.status if prev_status else WorkerStatus.UNKNOWN

        # Get or create worker client
        if worker_id not in self._worker_clients:
            self._worker_clients[worker_id] = NPUWorkerClient(worker_config.url)

        client = self._worker_clients[worker_id]

        try:
            # Perform health check with timeout
            health_data = await asyncio.wait_for(
                client.check_health(),
                timeout=self._load_balancing_config.timeout_seconds,
            )

            # Build status from health data
            status = self._build_healthy_status(worker_id, health_data)
            await self._store_and_emit_status(worker_id, status, prev_status_value)

            # Issue #699: Reset backoff on successful health check
            self._record_worker_success(worker_id)

        except asyncio.TimeoutError:
            # Issue #699: NPU workers are optional - log at DEBUG to avoid spam
            logger.debug(
                "Worker %s health check timed out (NPU workers are optional - "
                "configure at /settings/infrastructure)",
                worker_id,
            )
            status = NPUWorkerStatus(
                id=worker_id,
                status=WorkerStatus.OFFLINE,
                error_message="Health check timeout",
            )
            await self._store_and_emit_status(worker_id, status, prev_status_value)

            # Issue #699: Apply exponential backoff for consecutive failures
            self._record_worker_failure(worker_id)

        except Exception as e:
            # Issue #699: NPU workers are optional - log at DEBUG to avoid spam
            logger.debug(
                "Worker %s health check failed: %s (NPU workers are optional - "
                "configure at /settings/infrastructure)",
                worker_id,
                e,
            )
            status = NPUWorkerStatus(
                id=worker_id, status=WorkerStatus.ERROR, error_message=str(e)
            )
            await self._store_and_emit_status(worker_id, status, prev_status_value)

            # Issue #699: Apply exponential backoff for consecutive failures
            self._record_worker_failure(worker_id)

    def _build_healthy_status(
        self, worker_id: str, health_data: Dict[str, Any]
    ) -> NPUWorkerStatus:
        """Build worker status from health check data (Issue #665: extracted helper)."""
        return NPUWorkerStatus(
            id=worker_id,
            status=(
                WorkerStatus.ONLINE
                if health_data.get("status") == "healthy"
                else WorkerStatus.ERROR
            ),
            current_load=health_data.get("current_load", 0),
            total_tasks_completed=health_data.get("total_tasks", 0),
            uptime_seconds=health_data.get("uptime_seconds", 0.0),
            last_heartbeat=datetime.utcnow(),
            error_message=(
                health_data.get("error")
                if health_data.get("status") != "healthy"
                else None
            ),
        )

    async def _store_and_emit_status(
        self,
        worker_id: str,
        status: NPUWorkerStatus,
        prev_status_value: WorkerStatus,
    ) -> None:
        """Store status and emit change event if needed (Issue #665: extracted helper)."""
        await self._store_worker_status(worker_id, status)

        # Emit status change event if status actually changed
        if prev_status_value != status.status:
            worker_details = await self.get_worker(worker_id)
            if worker_details:
                await self._emit_worker_event("worker.status.changed", worker_details)

    async def _store_worker_status(self, worker_id: str, status: NPUWorkerStatus):
        """Store worker status in Redis"""
        if not self.redis_client:
            return

        try:
            key = f"npu:worker:{worker_id}:status"
            value = status.json()

            # Store with TTL (2x health check interval)
            ttl = self._load_balancing_config.health_check_interval * 2
            await self.redis_client.setex(key, ttl, value)

        except Exception as e:
            logger.error("Failed to store worker status in Redis: %s", e)

    async def _emit_worker_event(
        self, event_type: str, worker_details: NPUWorkerDetails
    ):
        """Emit worker event via event_manager (Issue #372 - refactored)"""
        try:
            event_data = {
                "event": event_type,
                "worker_id": worker_details.config.id,
                "data": {
                    "status": worker_details.status.status.value,
                    "current_load": worker_details.status.current_load,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            }

            # Add full worker data for certain events (Issue #372, #380)
            if event_type in _WORKER_FULL_DATA_EVENTS:
                event_data["worker"] = worker_details.to_event_dict()

            await event_manager.publish(f"npu.{event_type}", event_data)
            logger.debug(
                f"Emitted event {event_type} for worker {worker_details.config.id}"
            )

        except Exception as e:
            logger.error("Failed to emit worker event: %s", e, exc_info=True)

    async def _get_worker_status(self, worker_id: str) -> Optional[NPUWorkerStatus]:
        """Get worker status from Redis"""
        if not self.redis_client:
            return None

        try:
            key = f"npu:worker:{worker_id}:status"
            value = await self.redis_client.get(key)

            if value:
                return NPUWorkerStatus.parse_raw(value)

        except Exception as e:
            logger.error("Failed to get worker status from Redis: %s", e)

        return None

    async def list_workers(self) -> List[NPUWorkerDetails]:
        """List all registered workers with their status"""
        if not self._workers:
            return []

        # Get all worker IDs and configs
        worker_items = list(self._workers.items())
        worker_ids = [wid for wid, _ in worker_items]

        # Batch fetch all worker statuses in parallel - eliminates N+1 queries
        statuses = await asyncio.gather(
            *[self._get_worker_status(wid) for wid in worker_ids],
            return_exceptions=True,
        )

        # Build worker details list
        workers = []
        for (worker_id, config), status in zip(worker_items, statuses):
            if isinstance(status, Exception) or not status:
                status = NPUWorkerStatus(id=worker_id, status=WorkerStatus.UNKNOWN)
            workers.append(NPUWorkerDetails(config=config, status=status))

        return workers

    async def get_worker(self, worker_id: str) -> Optional[NPUWorkerDetails]:
        """Get specific worker details"""
        config = self._workers.get(worker_id)
        if not config:
            return None

        status = await self._get_worker_status(worker_id)
        if not status:
            status = NPUWorkerStatus(id=worker_id, status=WorkerStatus.UNKNOWN)

        # Get metrics if available
        metrics = await self._get_worker_metrics(worker_id)

        return NPUWorkerDetails(config=config, status=status, metrics=metrics)

    async def add_worker(self, worker_config: NPUWorkerConfig) -> NPUWorkerDetails:
        """Add new worker to registry"""
        if worker_config.id in self._workers:
            raise ValueError(f"Worker with ID '{worker_config.id}' already exists")

        # Validate worker by testing connection
        test_result = await self.test_worker_connection(worker_config)
        if not test_result.success:
            raise ValueError(
                f"Worker connection test failed: {test_result.error_message}"
            )

        # Add to registry
        self._workers[worker_config.id] = worker_config

        # Save to config file
        await self._save_workers_to_config()

        # Trigger immediate health check
        await self._check_worker_health(worker_config.id)

        # Get worker details and emit event
        worker_details = await self.get_worker(worker_config.id)
        await self._emit_worker_event("worker.added", worker_details)

        return worker_details

    async def update_worker(
        self, worker_id: str, worker_config: NPUWorkerConfig
    ) -> NPUWorkerDetails:
        """Update existing worker configuration"""
        if worker_id not in self._workers:
            raise ValueError(f"Worker with ID '{worker_id}' not found")

        # Ensure ID matches
        if worker_config.id != worker_id:
            raise ValueError("Worker ID cannot be changed")

        # Test new configuration
        test_result = await self.test_worker_connection(worker_config)
        if not test_result.success:
            raise ValueError(
                f"Worker connection test failed: {test_result.error_message}"
            )

        # Update configuration
        self._workers[worker_id] = worker_config

        # Close existing client if URL changed
        if worker_id in self._worker_clients:
            old_client = self._worker_clients.pop(worker_id)
            await old_client.close()

        # Save to config file
        await self._save_workers_to_config()

        # Trigger immediate health check
        await self._check_worker_health(worker_id)

        # Get worker details and emit event
        worker_details = await self.get_worker(worker_id)
        await self._emit_worker_event("worker.updated", worker_details)

        return worker_details

    async def update_worker_status_from_heartbeat(self, heartbeat) -> None:
        """Update worker status from heartbeat telemetry (Issue #68).

        Args:
            heartbeat: WorkerHeartbeat model with worker status data
        """
        worker_id = heartbeat.worker_id

        # Create status from heartbeat
        status = NPUWorkerStatus(
            id=worker_id,
            status=(
                WorkerStatus.ONLINE
                if heartbeat.status == "online"
                else WorkerStatus.ERROR
            ),
            current_load=heartbeat.current_load,
            total_tasks_completed=heartbeat.total_tasks_completed,
            total_tasks_failed=heartbeat.total_tasks_failed,
            uptime_seconds=heartbeat.uptime_seconds,
            last_heartbeat=datetime.utcnow(),
            error_message=None,
        )

        # Store in Redis
        await self._store_worker_status(worker_id, status)

        # Emit status changed event if worker exists
        if worker_id in self._workers:
            worker_details = await self.get_worker(worker_id)
            if worker_details:
                await self._emit_worker_event("worker.heartbeat", worker_details)

        logger.debug("Updated worker status from heartbeat: %s", worker_id)

    async def remove_worker(self, worker_id: str):
        """Remove worker from registry"""
        if worker_id not in self._workers:
            raise ValueError(f"Worker with ID '{worker_id}' not found")

        # Remove from registry
        del self._workers[worker_id]

        # Close and remove client
        if worker_id in self._worker_clients:
            client = self._worker_clients.pop(worker_id)
            await client.close()

        # Remove from Redis (Issue #379: concurrent deletes)
        if self.redis_client:
            try:
                await asyncio.gather(
                    self.redis_client.delete(f"npu:worker:{worker_id}:status"),
                    self.redis_client.delete(f"npu:worker:{worker_id}:metrics"),
                )
            except Exception as e:
                logger.error("Failed to remove worker data from Redis: %s", e)

        # Save to config file
        await self._save_workers_to_config()

        # Emit worker removed event
        await event_manager.publish(
            "npu.worker.removed",
            {
                "event": "worker.removed",
                "worker_id": worker_id,
                "data": {"timestamp": datetime.utcnow().isoformat() + "Z"},
            },
        )

    async def test_worker_connection(
        self, worker_config: NPUWorkerConfig
    ) -> WorkerTestResult:
        """Test connection to a worker"""
        client = NPUWorkerClient(worker_config.url)

        try:
            start_time = datetime.utcnow()

            # Perform health check with timeout
            health_data = await asyncio.wait_for(
                client.check_health(),
                timeout=self._load_balancing_config.timeout_seconds,
            )

            end_time = datetime.utcnow()
            response_time_ms = (end_time - start_time).total_seconds() * 1000

            return WorkerTestResult(
                worker_id=worker_config.id,
                success=health_data.get("status") == "healthy",
                response_time_ms=response_time_ms,
                status_code=200,
                health_data=health_data,
            )

        except asyncio.TimeoutError:
            return WorkerTestResult(
                worker_id=worker_config.id,
                success=False,
                error_message=f"Connection timeout after {self._load_balancing_config.timeout_seconds}s",
            )

        except Exception as e:
            return WorkerTestResult(
                worker_id=worker_config.id, success=False, error_message=str(e)
            )

        finally:
            await client.close()

    async def get_worker_metrics(self, worker_id: str) -> Optional[NPUWorkerMetrics]:
        """Get performance metrics for a worker"""
        return await self._get_worker_metrics(worker_id)

    async def _get_worker_metrics(self, worker_id: str) -> Optional[NPUWorkerMetrics]:
        """Get worker metrics from Redis"""
        if not self.redis_client:
            return None

        try:
            key = f"npu:worker:{worker_id}:metrics"
            value = await self.redis_client.get(key)

            if value:
                return NPUWorkerMetrics.parse_raw(value)

        except Exception as e:
            logger.error("Failed to get worker metrics from Redis: %s", e)

        return None

    def get_load_balancing_config(self) -> LoadBalancingConfig:
        """Get current load balancing configuration"""
        return self._load_balancing_config

    async def update_load_balancing_config(self, config: LoadBalancingConfig):
        """Update load balancing configuration"""
        self._load_balancing_config = config
        await self._save_workers_to_config()
        logger.info("Updated load balancing config: %s", config.strategy)


# Global worker manager instance (thread-safe)
import asyncio as _asyncio_lock

_worker_manager: Optional[NPUWorkerManager] = None
_worker_manager_lock = _asyncio_lock.Lock()


async def get_worker_manager(redis_client=None) -> NPUWorkerManager:
    """Get or create global worker manager instance (thread-safe)."""
    global _worker_manager

    if _worker_manager is None:
        async with _worker_manager_lock:
            # Double-check after acquiring lock
            if _worker_manager is None:
                _worker_manager = NPUWorkerManager(redis_client=redis_client)
                await _worker_manager.start_health_monitoring()

    return _worker_manager
