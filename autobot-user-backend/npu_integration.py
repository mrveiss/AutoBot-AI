#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Worker Integration
Provides high-performance processing using NPU worker for heavy computational tasks

Issue #255: Updated to use ServiceHTTPClient for authenticated service-to-service
communication with HMAC-SHA256 signatures.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Union

import yaml

if TYPE_CHECKING:
    from backend.utils.service_client import ServiceHTTPClient

from autobot_shared.http_client import HTTPClientManager, get_http_client
from backend.constants.threshold_constants import LLMDefaults, TimingConstants

from .utils.service_registry import get_service_url

logger = logging.getLogger(__name__)

# Issue #255: Enable authenticated client for service-to-service communication
# Set to False to fall back to unauthenticated mode (for development/testing)
USE_AUTHENTICATED_CLIENT = True


class CircuitState(Enum):
    """Circuit breaker states for worker health management"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Worker failed, blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class WorkerState:
    """
    Track per-worker metrics and health status (Issue #168).

    Manages active task count, failure tracking, and circuit breaker state
    for load balancing and failover.
    """

    worker_id: str
    client: "NPUWorkerClient"
    active_tasks: int = 0
    total_requests: int = 0
    failures: int = 0
    last_health_check: float = 0
    healthy: bool = True
    circuit_state: CircuitState = CircuitState.CLOSED
    circuit_open_until: float = 0


def load_worker_config(config_path: str = "config/npu_workers.yaml") -> List[Dict]:
    """
    Parse and validate NPU worker configuration from YAML file (Issue #168).

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        List of validated worker configurations with constructed URLs
    """
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.debug("NPU worker config not found at %s, using defaults", config_path)
        return []
    except yaml.YAMLError as e:
        logger.error("Failed to parse NPU worker config: %s", e)
        return []

    if not config or "npu" not in config or "workers" not in config.get("npu", {}):
        logger.debug("No workers defined in NPU config")
        return []

    workers = []
    required_fields = {"id", "host", "port", "enabled"}

    for worker in config["npu"]["workers"]:
        # Validate required fields
        missing = required_fields - set(worker.keys())
        if missing:
            logger.warning(
                "Skipping worker with missing fields %s: %s", missing, worker
            )
            continue

        # Construct URL from host and port
        host = worker["host"]
        port = worker["port"]
        url = f"http://{host}:{port}"

        workers.append(
            {
                "id": worker["id"],
                "url": url,
                "enabled": worker.get("enabled", True),
                "priority": worker.get("priority", 5),
                "max_concurrent": worker.get("max_concurrent", 10),
                "weight": worker.get("weight", 50),
                "capabilities": worker.get("capabilities", ["llm"]),
            }
        )

    logger.info("Loaded %d NPU workers from config", len(workers))
    return workers


@dataclass
class NPUInferenceRequest:
    """Request payload for NPU inference (Issue #376 - use named constants)."""

    model_id: str
    input_text: str
    max_tokens: int = LLMDefaults.DEFAULT_MAX_TOKENS
    temperature: float = LLMDefaults.DEFAULT_TEMPERATURE
    top_p: float = LLMDefaults.DEFAULT_TOP_P


class NPUWorkerClient:
    """
    Client for communicating with NPU inference worker.

    Issue #255: Supports authenticated service-to-service communication using
    HMAC-SHA256 signatures via ServiceHTTPClient.
    """

    def __init__(
        self,
        npu_endpoint: str = None,
        use_auth: bool = None,
    ):
        """
        Initialize NPU client with endpoint and HTTP client.

        Args:
            npu_endpoint: NPU worker endpoint URL (default from service registry)
            use_auth: Use authenticated client (default from USE_AUTHENTICATED_CLIENT)
        """
        self.npu_endpoint = npu_endpoint or get_service_url("npu-worker")
        self._use_auth = use_auth if use_auth is not None else USE_AUTHENTICATED_CLIENT
        self._http_client: Optional[
            Union[HTTPClientManager, "ServiceHTTPClient"]
        ] = None
        self._auth_client_initialized = False
        self.available = False
        self._check_availability_task = None

    async def _get_http_client(self):
        """
        Get HTTP client, initializing authenticated client if needed.

        Issue #255: Uses ServiceHTTPClient for authenticated requests.
        """
        if self._http_client is not None:
            return self._http_client

        if self._use_auth and not self._auth_client_initialized:
            try:
                # Import here to avoid circular imports
                from backend.utils.service_client import create_service_client

                self._http_client = await create_service_client("main-backend")
                self._auth_client_initialized = True
                logger.info(
                    "NPU client using authenticated ServiceHTTPClient (Issue #255)"
                )
            except Exception as e:
                logger.warning(
                    "Failed to create authenticated client, falling back to "
                    "unauthenticated mode: %s",
                    e,
                )
                self._http_client = get_http_client()
        else:
            self._http_client = get_http_client()

        return self._http_client

    async def check_health(self) -> Dict[str, Any]:
        """Check NPU worker health and capabilities"""
        try:
            http_client = await self._get_http_client()
            async with await http_client.get(f"{self.npu_endpoint}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    self.available = True
                    return health_data
                else:
                    self.available = False
                    return {"status": "unhealthy", "error": f"HTTP {response.status}"}
        except Exception as e:
            self.available = False
            # Issue #699: NPU workers are optional - log at DEBUG level to avoid spam
            logger.debug(
                "NPU worker not available (optional service - configure at /settings/infrastructure): %s",
                e,
            )
            return {"status": "unavailable", "error": str(e)}

    async def get_available_models(self) -> Dict[str, Any]:
        """Get list of available models on NPU worker"""
        try:
            http_client = await self._get_http_client()
            async with await http_client.get(f"{self.npu_endpoint}/models") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"loaded_models": {}, "error": f"HTTP {response.status}"}
        except Exception as e:
            logger.error("Failed to get NPU models: %s", e)
            return {"loaded_models": {}, "error": str(e)}

    async def load_model(self, model_id: str, device: str = "CPU") -> Dict[str, Any]:
        """Load a model on the NPU worker"""
        try:
            http_client = await self._get_http_client()
            payload = {"model_id": model_id, "device": device}
            async with await http_client.post(
                f"{self.npu_endpoint}/models/load", json=payload
            ) as response:
                return await response.json()
        except Exception as e:
            logger.error("Failed to load model %s: %s", model_id, e)
            return {"success": False, "error": str(e)}

    async def run_inference(
        self,
        model_id: str,
        input_text: str,
        max_tokens: int = LLMDefaults.DEFAULT_MAX_TOKENS,
        temperature: float = LLMDefaults.DEFAULT_TEMPERATURE,
        top_p: float = LLMDefaults.DEFAULT_TOP_P,
    ) -> Dict[str, Any]:
        """Run inference on NPU worker"""
        try:
            http_client = await self._get_http_client()
            payload = {
                "model_id": model_id,
                "input_text": input_text,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            }

            async with await http_client.post(
                f"{self.npu_endpoint}/inference", json=payload
            ) as response:
                result = await response.json()
                if response.status == 200:
                    return result
                else:
                    return {
                        "error": result.get("detail", "Unknown error"),
                        "success": False,
                    }
        except Exception as e:
            logger.error("NPU inference failed: %s", e)
            return {"error": str(e), "success": False}

    async def offload_heavy_processing(
        self, task_type: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Offload heavy processing tasks to NPU worker

        Supported task types:
        - text_analysis: Analyze large text chunks
        - embedding_batch: Generate embeddings for multiple texts
        - knowledge_processing: Process knowledge base operations
        """
        try:
            # Check if NPU worker is available
            await self.check_health()
            if not self.available:
                return {
                    "success": False,
                    "error": "NPU worker not available",
                    "fallback": True,
                }

            # For now, use standard inference endpoint with task-specific prompts
            if task_type == "text_analysis":
                prompt = (
                    "Analyze the following text and extract key insights:\n\n"
                    f"{data.get('text', '')}"
                )
                return await self.run_inference(
                    model_id=data.get("model_id", "default"),
                    input_text=prompt,
                    max_tokens=data.get("max_tokens", LLMDefaults.ANALYSIS_MAX_TOKENS),
                )

            elif task_type == "knowledge_processing":
                prompt = (
                    "Process and summarize this knowledge data:\n\n"
                    f"{json.dumps(data.get('knowledge_data', {}))}"
                )
                return await self.run_inference(
                    model_id=data.get("model_id", "default"),
                    input_text=prompt,
                    max_tokens=data.get("max_tokens", LLMDefaults.KNOWLEDGE_MAX_TOKENS),
                )

            else:
                return {
                    "success": False,
                    "error": f"Unsupported task type: {task_type}",
                }

        except Exception as e:
            logger.error("Heavy processing offload failed: %s", e)
            return {"success": False, "error": str(e), "fallback": True}

    async def close(self):
        """No-op: HTTP client is managed by singleton HTTPClientManager"""
        # Using HTTPClient singleton - session management is centralized


class NPUWorkerPool:
    """
    Pool manager for multiple NPU workers with load balancing (Issue #168).

    Manages worker lifecycle, health monitoring, circuit breakers, and
    intelligent task routing using priority-first + least-connections algorithm.
    """

    def __init__(self, config_path: str = "config/npu_workers.yaml"):
        """
        Initialize worker pool from configuration.

        Args:
            config_path: Path to worker configuration YAML file
        """
        self.config_path = config_path
        self.workers: Dict[str, WorkerState] = {}
        self._worker_configs: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._health_monitor_task: Optional[asyncio.Task] = None
        self._running = False

        # Load initial configuration
        self._load_workers()

    def _load_workers(self) -> None:
        """Load workers from configuration file."""
        worker_configs = load_worker_config(self.config_path)

        for config in worker_configs:
            if not config.get("enabled", True):
                logger.debug("Skipping disabled worker: %s", config["id"])
                continue

            worker_id = config["id"]
            client = NPUWorkerClient(npu_endpoint=config["url"])

            self.workers[worker_id] = WorkerState(
                worker_id=worker_id,
                client=client,
            )
            self._worker_configs[worker_id] = config

            logger.info(
                "Initialized worker %s (priority=%d)",
                worker_id,
                config.get("priority", 5),
            )

        logger.info("NPUWorkerPool initialized with %d workers", len(self.workers))

    async def _select_worker(self, excluded_workers: Set[str]) -> Optional[WorkerState]:
        """
        Select best available worker using priority-first + least-connections.

        Args:
            excluded_workers: Set of worker IDs to exclude (for retry logic)

        Returns:
            WorkerState of selected worker, or None if no workers available
        """
        async with self._lock:
            # Filter available workers
            available = []
            for worker_id, state in self.workers.items():
                # Skip excluded workers
                if worker_id in excluded_workers:
                    continue
                # Skip workers with open circuit
                if state.circuit_state == CircuitState.OPEN:
                    continue
                available.append((worker_id, state))

            if not available:
                logger.debug("No available workers after filtering")
                return None

            # Group by priority (from config)
            priority_groups: Dict[int, List[tuple]] = {}
            for worker_id, state in available:
                priority = self._worker_configs.get(worker_id, {}).get("priority", 5)
                if priority not in priority_groups:
                    priority_groups[priority] = []
                priority_groups[priority].append((worker_id, state))

            # Select highest priority group
            max_priority = max(priority_groups.keys())
            top_group = priority_groups[max_priority]

            # Within group, select least loaded (by active_tasks)
            # Ties broken by worker_id (alphabetical)
            top_group.sort(key=lambda x: (x[1].active_tasks, x[0]))
            selected_id, selected_state = top_group[0]

            logger.debug(
                "Selected worker %s (priority=%d, active_tasks=%d)",
                selected_id,
                max_priority,
                selected_state.active_tasks,
            )

            return selected_state

    async def _check_worker_health(self, worker: WorkerState) -> bool:
        """
        Check health of a single worker and update its state.

        Args:
            worker: WorkerState to check

        Returns:
            True if worker is healthy, False otherwise
        """
        import time

        try:
            health_result = await worker.client.check_health()
            worker.last_health_check = time.time()

            if health_result.get("status") == "healthy":
                worker.healthy = True
                logger.debug("Worker %s is healthy", worker.worker_id)
                return True
            else:
                worker.healthy = False
                logger.debug(
                    "Worker %s is unhealthy: %s",
                    worker.worker_id,
                    health_result.get("error", "unknown"),
                )
                return False

        except Exception as e:
            worker.healthy = False
            worker.last_health_check = time.time()
            logger.debug("Health check failed for worker %s: %s", worker.worker_id, e)
            return False

    # Circuit breaker constants
    CIRCUIT_FAILURE_THRESHOLD = 5  # Open after 5 failures
    CIRCUIT_COOLDOWN_SECONDS = 60  # Stay open for 60 seconds

    def _record_failure(self, worker: WorkerState) -> None:
        """
        Record a task failure for a worker.

        Opens circuit if failure threshold is reached.
        """
        import time

        worker.failures += 1
        logger.debug("Worker %s failure count: %d", worker.worker_id, worker.failures)

        if worker.failures >= self.CIRCUIT_FAILURE_THRESHOLD:
            worker.circuit_state = CircuitState.OPEN
            worker.circuit_open_until = time.time() + self.CIRCUIT_COOLDOWN_SECONDS
            logger.error(
                "Circuit OPEN for worker %s after %d failures, cooldown until %s",
                worker.worker_id,
                worker.failures,
                worker.circuit_open_until,
            )

    def _record_success(self, worker: WorkerState) -> None:
        """
        Record a task success for a worker.

        Resets failure count and closes circuit from half-open state.
        """
        worker.failures = 0

        if worker.circuit_state == CircuitState.HALF_OPEN:
            worker.circuit_state = CircuitState.CLOSED
            logger.info(
                "Circuit CLOSED for worker %s after successful request",
                worker.worker_id,
            )

    def _is_circuit_available(self, worker: WorkerState) -> bool:
        """
        Check if circuit allows requests.

        Handles state transitions:
        - CLOSED: Always available
        - OPEN: Not available unless cooldown expired (then → HALF_OPEN)
        - HALF_OPEN: Available (test request)
        """
        import time

        if worker.circuit_state == CircuitState.CLOSED:
            return True

        if worker.circuit_state == CircuitState.HALF_OPEN:
            return True

        # Circuit is OPEN - check if cooldown expired
        if worker.circuit_state == CircuitState.OPEN:
            if time.time() >= worker.circuit_open_until:
                worker.circuit_state = CircuitState.HALF_OPEN
                logger.info(
                    "Circuit HALF_OPEN for worker %s, allowing test request",
                    worker.worker_id,
                )
                return True
            return False

        return False

    # Health monitor constants
    HEALTH_CHECK_INTERVAL = 30  # Seconds between health checks

    async def start_health_monitor(self) -> None:
        """
        Start background health monitoring task.

        Periodically checks health of all workers and updates their status.
        """
        if self._running:
            logger.warning("Health monitor already running")
            return

        self._running = True
        self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Health monitor started")

    async def stop_health_monitor(self) -> None:
        """
        Stop background health monitoring task.
        """
        self._running = False

        if self._health_monitor_task is not None:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
            self._health_monitor_task = None

        logger.info("Health monitor stopped")

    async def _health_monitor_loop(self) -> None:
        """
        Background task that periodically checks worker health.
        """
        logger.info("Health monitor loop started")

        while self._running:
            try:
                # Check health of all workers
                for worker_id, worker in self.workers.items():
                    try:
                        await self._check_worker_health(worker)
                    except Exception as e:
                        logger.debug("Health check failed for %s: %s", worker_id, e)

                # Wait for next check interval
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health monitor error: %s", e)
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)

        logger.info("Health monitor loop stopped")

    # Retry constants
    MAX_RETRY_ATTEMPTS = 3

    async def execute_task(
        self, task_type: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a task on the pool with automatic retry and failover.

        Args:
            task_type: Type of task (e.g., 'text_analysis', 'knowledge_processing')
            data: Task-specific data

        Returns:
            Task result dict with 'success' key
        """
        excluded_workers: Set[str] = set()
        last_error = None

        for attempt in range(self.MAX_RETRY_ATTEMPTS):
            # Select a worker
            worker = await self._select_worker(excluded_workers)

            if worker is None:
                logger.warning(
                    "No available workers for task (attempt %d/%d)",
                    attempt + 1,
                    self.MAX_RETRY_ATTEMPTS,
                )
                break

            try:
                # Increment active tasks
                worker.active_tasks += 1
                worker.total_requests += 1

                logger.debug(
                    "Executing task on worker %s (attempt %d/%d)",
                    worker.worker_id,
                    attempt + 1,
                    self.MAX_RETRY_ATTEMPTS,
                )

                # Execute the task
                result = await worker.client.offload_heavy_processing(task_type, data)

                # Decrement active tasks
                worker.active_tasks -= 1

                # Check if result indicates success
                if result.get("success") or not result.get("error"):
                    self._record_success(worker)
                    return result
                else:
                    # Task returned error result
                    self._record_failure(worker)
                    excluded_workers.add(worker.worker_id)
                    last_error = result.get("error", "Unknown error")
                    logger.info(
                        "Task failed on worker %s: %s",
                        worker.worker_id,
                        last_error,
                    )

            except Exception as e:
                # Decrement active tasks on exception
                worker.active_tasks -= 1
                self._record_failure(worker)
                excluded_workers.add(worker.worker_id)
                last_error = str(e)
                logger.info("Task exception on worker %s: %s", worker.worker_id, e)

        # All attempts failed
        logger.error(
            "Task failed after %d attempts: %s",
            self.MAX_RETRY_ATTEMPTS,
            last_error,
        )
        return {
            "success": False,
            "error": last_error or "All workers failed",
            "fallback": True,
        }

    async def get_pool_stats(self) -> Dict[str, Any]:
        """
        Get pool-level statistics and metrics (Issue #168).

        Returns:
            Dict containing pool metrics:
            - total_workers: Total number of configured workers
            - healthy_workers: Number of healthy workers
            - total_tasks_processed: Total tasks executed
            - active_tasks: Currently executing tasks
            - success_rate: Task success rate (0.0-1.0)
        """
        total_workers = len(self.workers)
        healthy_workers = sum(
            1
            for w in self.workers.values()
            if w.healthy and self._is_circuit_available(w)
        )
        total_tasks = sum(w.total_requests for w in self.workers.values())
        active_tasks = sum(w.active_tasks for w in self.workers.values())
        total_failures = sum(w.failures for w in self.workers.values())

        # Calculate success rate
        success_rate = 0.0
        if total_tasks > 0:
            success_rate = round(1.0 - (total_failures / total_tasks), 3)

        return {
            "total_workers": total_workers,
            "healthy_workers": healthy_workers,
            "total_tasks_processed": total_tasks,
            "active_tasks": active_tasks,
            "success_rate": success_rate,
        }

    async def reload_config(self) -> None:
        """
        Hot-reload worker configuration from YAML file (Issue #168).

        Reloads config/npu_workers.yaml and updates the worker pool:
        - New workers are added
        - Removed workers are removed (after active tasks drain)
        - Existing workers are updated
        """
        logger.info("Reloading pool configuration from %s", self.config_path)

        try:
            new_configs = load_worker_config(self.config_path)
        except Exception as e:
            logger.error("Failed to load worker config during reload: %s", e)
            raise

        new_worker_ids = {cfg["id"] for cfg in new_configs}
        current_worker_ids = set(self.workers.keys())

        # Remove workers no longer in config
        for worker_id in current_worker_ids - new_worker_ids:
            worker = self.workers.get(worker_id)
            if worker and worker.active_tasks == 0:
                del self.workers[worker_id]
                if worker_id in self._worker_configs:
                    del self._worker_configs[worker_id]
                logger.info("Removed worker %s from pool", worker_id)
            elif worker:
                logger.warning(
                    "Worker %s has %d active tasks, deferring removal",
                    worker_id,
                    worker.active_tasks,
                )

        # Add or update workers from new config
        for config in new_configs:
            worker_id = config["id"]
            if worker_id in self.workers:
                # Update existing worker config
                self._worker_configs[worker_id] = config
                logger.debug("Updated worker %s configuration", worker_id)
            else:
                # Add new worker
                if config.get("enabled", True):
                    client = NPUWorkerClient(npu_endpoint=config["url"])
                    self.workers[worker_id] = WorkerState(
                        worker_id=worker_id,
                        client=client,
                    )
                    self._worker_configs[worker_id] = config
                    logger.info("Added new worker %s to pool", worker_id)

        logger.info(
            "Pool configuration reloaded: %d workers active",
            len(self.workers),
        )


class NPUTaskQueue:
    """Queue for managing NPU processing tasks (Issue #376 - use named constants)."""

    def __init__(
        self,
        npu_client: NPUWorkerClient,
        max_concurrent: int = LLMDefaults.DEFAULT_CONCURRENT_WORKERS,
    ):
        """Initialize task queue with NPU client and worker pool."""
        self.npu_client = npu_client
        self.max_concurrent = max_concurrent
        self.queue = asyncio.Queue()
        self.workers = []
        self.running = False

    async def start_workers(self):
        """Start background worker tasks"""
        self.running = True
        for i in range(self.max_concurrent):
            worker = asyncio.create_task(self._worker(f"npu_worker_{i}"))
            self.workers.append(worker)
        logger.info("Started %s NPU workers", self.max_concurrent)

    async def stop_workers(self):
        """Stop background worker tasks"""
        self.running = False
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []
        logger.info("Stopped NPU workers")

    async def _worker(self, worker_id: str):
        """Background worker that processes NPU tasks"""
        logger.info("NPU worker %s started", worker_id)
        while self.running:
            try:
                # Wait for task with timeout to allow graceful shutdown
                task_data = await asyncio.wait_for(
                    self.queue.get(), timeout=TimingConstants.STANDARD_DELAY
                )

                logger.debug(
                    f"Worker {worker_id} processing task: {task_data['task_type']}"
                )

                # Process the task
                result = await self.npu_client.offload_heavy_processing(
                    task_data["task_type"], task_data["data"]
                )

                # Set result in the future
                if not task_data["future"].done():
                    task_data["future"].set_result(result)

                # Mark task as done
                self.queue.task_done()

            except asyncio.TimeoutError:
                continue  # No task available, continue loop
            except Exception as e:
                logger.error("NPU worker %s error: %s", worker_id, e)
                if "future" in locals() and not task_data["future"].done():
                    task_data["future"].set_exception(e)

    async def submit_task(self, task_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a task to the NPU queue"""
        if not self.running:
            await self.start_workers()

        future = asyncio.Future()
        task_data = {"task_type": task_type, "data": data, "future": future}

        await self.queue.put(task_data)

        try:
            # Wait for result with timeout (Issue #376 - use named constants)
            result = await asyncio.wait_for(
                future, timeout=TimingConstants.SHORT_TIMEOUT
            )
            return result
        except asyncio.TimeoutError:
            return {"success": False, "error": "NPU task timeout", "fallback": True}


# Global NPU client instance (thread-safe)
_npu_client = None
_npu_queue = None
_npu_pool = None
_npu_client_lock = asyncio.Lock()
_npu_queue_lock = asyncio.Lock()
_npu_pool_lock = asyncio.Lock()


async def get_npu_client() -> NPUWorkerClient:
    """Get or create global NPU client instance (thread-safe)"""
    global _npu_client
    if _npu_client is None:
        async with _npu_client_lock:
            # Double-check after acquiring lock
            if _npu_client is None:
                _npu_client = NPUWorkerClient()
                await _npu_client.check_health()
    return _npu_client


async def get_npu_queue() -> NPUTaskQueue:
    """Get or create global NPU task queue (thread-safe)"""
    global _npu_queue
    if _npu_queue is None:
        async with _npu_queue_lock:
            # Double-check after acquiring lock
            if _npu_queue is None:
                client = await get_npu_client()
                _npu_queue = NPUTaskQueue(client)
    return _npu_queue


async def get_npu_pool() -> NPUWorkerPool:
    """
    Get or create global NPU worker pool instance (thread-safe).

    Issue #168: The pool provides load-balanced access to multiple NPU workers
    with automatic failover, health monitoring, and circuit breaker protection.

    Returns:
        NPUWorkerPool singleton instance
    """
    global _npu_pool
    if _npu_pool is None:
        async with _npu_pool_lock:
            # Double-check after acquiring lock
            if _npu_pool is None:
                _npu_pool = NPUWorkerPool()
                await _npu_pool.start_health_monitor()
                logger.info("NPU worker pool initialized (Issue #168)")
    return _npu_pool


async def process_with_npu_fallback(
    task_type: str, data: Dict[str, Any], fallback_func: callable
) -> Dict[str, Any]:
    """
    Try to process with NPU worker, fall back to local processing if unavailable
    """
    try:
        queue = await get_npu_queue()
        result = await queue.submit_task(task_type, data)

        if result.get("fallback") or not result.get("success"):
            logger.info("NPU processing failed, using fallback for %s", task_type)
            return await fallback_func()

        return result
    except Exception as e:
        # Issue #699: NPU is optional, fallback is expected - log at DEBUG
        logger.debug(
            "NPU processing unavailable for %s, using fallback: %s", task_type, e
        )
        return await fallback_func()
