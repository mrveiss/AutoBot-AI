# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
NPU Worker Registry and Management Service

Manages NPU worker registration, health monitoring, and state tracking.
"""

import asyncio
import json
import math
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import yaml

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, utc_timestamp
from constants.threshold_constants import TimingConstants
from events.bus import PersistStrategy, publish_event
from models.npu_models import (
    LoadBalancingConfig,
    NPUWorkerConfig,
    NPUWorkerDetails,
    NPUWorkerMetrics,
    NPUWorkerStatus,
    WorkerStatus,
    WorkerTestResult,
)
from npu_integration import NPUWorkerClient
from utils.async_initializable import AsyncInitializable

logger = get_logger(__name__)

# Issue #380: Module-level frozenset for worker events that include full data
_WORKER_FULL_DATA_EVENTS = frozenset({"worker.added", "worker.updated"})

# GH#6739: Pulse-probe canary config path
_PULSE_CANARIES_CONFIG = Path("config/npu_pulse_canaries.yaml")

# GH#6739: Prometheus metrics (lazy-initialised to avoid import-time side-effects)
try:
    from prometheus_client import Counter, Histogram

    _pulse_total = Counter(
        "autobot_npu_pulse_total",
        "Total NPU pulse-probe attempts",
        ["worker_id", "model_id"],
    )
    _pulse_failure_total = Counter(
        "autobot_npu_pulse_failure_total",
        "Total NPU pulse-probe failures",
        ["worker_id", "model_id", "failure_class"],
    )
    _pulse_latency = Histogram(
        "autobot_npu_pulse_latency_seconds",
        "NPU pulse-probe round-trip latency",
        ["worker_id", "model_id"],
        buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0),
    )
    _PULSE_METRICS_AVAILABLE = True
except Exception:
    _PULSE_METRICS_AVAILABLE = False


class NPUWorkerManager(AsyncInitializable):
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

    def __init__(self, config_file: Path = None, redis_client=None) -> None:
        """
        Initialize NPU Worker Manager.

        Args:
            config_file: Path to worker configuration YAML file
            redis_client: Redis client for state storage
        """
        super().__init__(component_name="npu_worker_manager")
        self.config_file = config_file or Path("config/npu_workers.yaml")
        self.redis_client = redis_client
        self._workers: Dict[str, NPUWorkerConfig] = {}
        self._worker_clients: Dict[str, NPUWorkerClient] = {}
        self._health_check_task: asyncio.Task | None = None
        self._running = False
        self._load_balancing_config = LoadBalancingConfig()
        self._failover_monitor_task: asyncio.Task | None = None

        # Issue #699: Track consecutive failures for exponential backoff
        self._worker_failure_counts: Dict[str, int] = {}
        self._worker_next_check: Dict[str, float] = {}

        # GH#6739: Pulse-probe state
        self._pulse_task: asyncio.Task | None = None
        self._pulse_failure_counts: Dict[str, int] = {}
        self._pulse_canaries: Dict[str, Any] = {}
        self._pulse_defaults: Dict[str, Any] = {}

    async def _initialize_impl(self) -> bool:
        """Load worker configurations from YAML (deferred from __init__ to avoid blocking I/O)."""
        await asyncio.to_thread(self._load_workers_from_config)
        return True

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

    def _load_workers_from_config(self) -> None:
        """Load worker configurations from YAML file"""
        try:
            if not self.config_file.exists():
                logger.warning("Worker config file not found: %s", self.config_file)
                self._save_workers_to_config()
                return

            with open(self.config_file, "r", encoding="utf-8") as f:
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

    async def _save_workers_to_config(self) -> None:
        """Save worker configurations to YAML file"""
        try:
            # Ensure config directory exists
            # Issue #358 - avoid blocking
            await asyncio.to_thread(self.config_file.parent.mkdir, parents=True, exist_ok=True)

            # Prepare data - use mode='json' to serialize enums as strings
            # This prevents !!python/object tags that yaml.safe_load() cannot parse
            data = {
                "workers": [worker.model_dump(mode="json") for worker in self._workers.values()],
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

    async def start_health_monitoring(self) -> None:
        """Start background health monitoring and failover monitor tasks."""
        if self._running:
            logger.warning("Health monitoring already running")
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self._failover_monitor_task = asyncio.create_task(self.failover_monitor())
        self._pulse_task = asyncio.create_task(self._pulse_probe_loop())
        logger.info("Started NPU worker health monitoring, failover monitor, and pulse-probe loop")

    async def stop_health_monitoring(self) -> None:
        """Stop background health monitoring and failover monitor tasks."""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                logger.debug("Health check task cancelled")

        if self._failover_monitor_task:
            self._failover_monitor_task.cancel()
            try:
                await self._failover_monitor_task
            except asyncio.CancelledError:
                logger.debug("Failover monitor task cancelled")

        if self._pulse_task:
            self._pulse_task.cancel()
            try:
                await self._pulse_task
            except asyncio.CancelledError:
                logger.debug("Pulse-probe task cancelled")

        # Close all worker clients
        for client in self._worker_clients.values():
            await client.close()
        self._worker_clients.clear()

        logger.info("Stopped NPU worker health monitoring and failover monitor")

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
        self._worker_failure_counts[worker_id] = self._worker_failure_counts.get(worker_id, 0) + 1
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

    # ------------------------------------------------------------------ #
    #  GH#6739 — Pulse-probe: correctness / inference-quality check       #
    # ------------------------------------------------------------------ #

    def _load_pulse_canaries(self) -> None:
        """Load pulse canary config from YAML (called lazily on first probe)."""
        try:
            if not _PULSE_CANARIES_CONFIG.exists():
                logger.warning("Pulse canary config not found: %s", _PULSE_CANARIES_CONFIG)
                return
            with open(_PULSE_CANARIES_CONFIG, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._pulse_defaults = data.get("defaults", {})
            self._pulse_canaries = data.get("model_families", {})
            logger.debug("Loaded pulse canary config with %d model families", len(self._pulse_canaries))
        except Exception as e:
            logger.error("Failed to load pulse canary config: %s", e)

    def _canary_for_model(self, model_id: str) -> Dict[str, Any]:
        """Return the canary definition that matches model_id (longest prefix wins)."""
        if not self._pulse_canaries:
            self._load_pulse_canaries()
        best: Dict[str, Any] = {}
        best_len = -1
        for _family, cfg in self._pulse_canaries.items():
            for prefix in cfg.get("match_prefixes", []):
                if model_id.startswith(prefix) and len(prefix) > best_len:
                    best = cfg
                    best_len = len(prefix)
        if not best:
            best = self._pulse_canaries.get("default", {})
        return best

    async def _store_pulse_latency(self, worker_id: str, model_id: str, latency_s: float) -> None:
        """Append latest pulse latency to a Redis list for p95 tracking."""
        if not self.redis_client:
            return
        window = int(self._pulse_defaults.get("latency_window", 20))
        key = f"npu:worker:{worker_id}:pulse_latency:{model_id}"
        try:
            pipe = self.redis_client.pipeline()
            pipe.rpush(key, latency_s)
            pipe.ltrim(key, -window, -1)
            pipe.expire(key, 86400)
            await pipe.execute()
        except Exception as e:
            logger.debug("Failed to store pulse latency for %s: %s", worker_id, e)

    async def _get_pulse_p95_latency(self, worker_id: str, model_id: str) -> Optional[float]:
        """Return p95 latency (seconds) from the Redis window, or None if unavailable."""
        if not self.redis_client:
            return None
        key = f"npu:worker:{worker_id}:pulse_latency:{model_id}"
        try:
            raw = await self.redis_client.lrange(key, 0, -1)
            if not raw:
                return None
            samples = sorted(float(v) for v in raw)
            idx = math.ceil(0.95 * len(samples)) - 1
            return samples[max(idx, 0)]
        except Exception:
            return None

    async def _get_pool_median_latency(self, model_id: str) -> Optional[float]:
        """Return median p95 latency across all workers for throttle detection."""
        p95s = []
        for worker_id in list(self._workers):
            v = await self._get_pulse_p95_latency(worker_id, model_id)
            if v is not None:
                p95s.append(v)
        if not p95s:
            return None
        p95s.sort()
        mid = len(p95s) // 2
        return p95s[mid] if len(p95s) % 2 else (p95s[mid - 1] + p95s[mid]) / 2

    def _check_heartbeat_reachability(self, worker_id: str, status: NPUWorkerStatus | None) -> Optional[str]:
        """Return 'heartbeat_stale' if last_heartbeat exceeds the silence threshold.

        MVA-1399: The pulse-probe correctness check now includes heartbeat
        reachability — a worker whose last_heartbeat has gone silent beyond
        heartbeat_max_silence_seconds is classified as unreachable regardless
        of whether its inference endpoint still responds.

        Returns None when the worker is reachable (or when the check is
        disabled / no baseline has been established yet).
        """
        max_silence = float(self._pulse_defaults.get("heartbeat_max_silence_seconds", 600))
        if max_silence <= 0:
            return None

        if status is None or status.last_heartbeat is None:
            # No heartbeat baseline yet — skip; cannot distinguish a fresh
            # worker from a silent one until at least one heartbeat arrives.
            return None

        last_hb = status.last_heartbeat
        now = now_utc()
        # Normalise to tz-aware for safe subtraction (last_heartbeat is
        # written by now_utc() so it should always be tz-aware; guard anyway).
        if last_hb.tzinfo is None:
            from datetime import timezone as _tz

            last_hb = last_hb.replace(tzinfo=_tz.utc)

        silence_s = (now - last_hb).total_seconds()
        if silence_s > max_silence:
            logger.warning(
                "Pulse-probe: heartbeat silent for %.1fs (threshold %.0fs) on worker %s",
                silence_s,
                max_silence,
                worker_id,
            )
            return "heartbeat_stale"
        return None

    async def _pulse_check_worker(self, worker_id: str) -> None:
        """Send a canary inference request to verify worker correctness (GH#6739).

        On failure increments pulse_failure counter; after K failures marks
        worker DEGRADED; after M failures marks worker OFFLINE and lets the
        existing exponential-backoff health-check path retry.
        """
        if not self._pulse_canaries:
            self._load_pulse_canaries()

        worker_config = self._workers.get(worker_id)
        if not worker_config:
            return

        status = await self._get_worker_status(worker_id)
        if status and status.status not in (WorkerStatus.ONLINE, WorkerStatus.DEGRADED):
            return

        degrade_k = int(self._pulse_defaults.get("degrade_after_failures", 3))
        unhealthy_m = int(self._pulse_defaults.get("unhealthy_after_failures", 5))
        pulse_timeout = float(self._pulse_defaults.get("pulse_timeout_seconds", 30))
        throttle_mult = float(self._pulse_defaults.get("latency_throttle_multiplier", 3.0))

        # MVA-1399: heartbeat reachability check — runs before the inference
        # probe so a silent worker fails fast without consuming model resources.
        heartbeat_failure = self._check_heartbeat_reachability(worker_id, status)
        if heartbeat_failure:
            if _PULSE_METRICS_AVAILABLE:
                _pulse_failure_total.labels(
                    worker_id=worker_id, model_id="__heartbeat__", failure_class=heartbeat_failure
                ).inc()
            consecutive = self._pulse_failure_counts.get(worker_id, 0) + 1
            self._pulse_failure_counts[worker_id] = consecutive
            if consecutive >= unhealthy_m:
                new_status = NPUWorkerStatus(
                    id=worker_id,
                    status=WorkerStatus.OFFLINE,
                    error_message=f"Pulse-probe: heartbeat silent for {consecutive} consecutive checks",
                )
                await self._store_and_emit_status(
                    worker_id, new_status, status.status if status else WorkerStatus.UNKNOWN
                )
                logger.error(
                    "Pulse-probe: worker %s marked OFFLINE — heartbeat silent for %d checks",
                    worker_id,
                    consecutive,
                )
            elif consecutive >= degrade_k:
                new_status = NPUWorkerStatus(
                    id=worker_id,
                    status=WorkerStatus.DEGRADED,
                    error_message=f"Pulse-probe: heartbeat silent for {consecutive} consecutive checks",
                )
                await self._store_and_emit_status(
                    worker_id, new_status, status.status if status else WorkerStatus.UNKNOWN
                )
                logger.warning(
                    "Pulse-probe: worker %s marked DEGRADED — heartbeat silent for %d checks",
                    worker_id,
                    consecutive,
                )
            return

        # Pick a model to probe: prefer loaded_models from latest heartbeat, else skip
        model_id = None
        if status and hasattr(status, "error_message"):
            pass  # no model list on NPUWorkerStatus — rely on client
        # Use the client's available_models endpoint to pick one
        client = self._worker_clients.get(worker_id)
        if client is None:
            client = NPUWorkerClient(worker_config.url)
            self._worker_clients[worker_id] = client

        try:
            models_data = await asyncio.wait_for(client.get_available_models(), timeout=10)
            models_list = models_data.get("models", [])
            if not models_list:
                return  # nothing to probe
            model_id = random.choice(
                models_list
            )  # nosec B311 - random probe selection for health check, not cryptographic
        except Exception as e:
            logger.debug("Pulse-probe: could not fetch models for worker %s: %s", worker_id, e)
            return

        canary = self._canary_for_model(model_id)
        prompt = canary.get("canary_prompt", "Reply with exactly: PULSE_OK")
        expected = canary.get("expected_token", "PULSE_OK")
        probe_mode = canary.get("probe_mode", "inference")

        if _PULSE_METRICS_AVAILABLE:
            _pulse_total.labels(worker_id=worker_id, model_id=model_id).inc()

        start = time.monotonic()
        failure_class: Optional[str] = None

        try:
            if probe_mode == "embedding":
                result = await asyncio.wait_for(
                    client.offload_heavy_processing("embedding_batch", {"texts": [prompt]}),
                    timeout=pulse_timeout,
                )
                embeddings = result.get("embeddings") or result.get("result", {}).get("embeddings")
                if not embeddings or not isinstance(embeddings, list) or len(embeddings) == 0:
                    failure_class = "malformed_response"
            else:
                result = await asyncio.wait_for(
                    client.run_inference(model_id=model_id, input_text=prompt, max_tokens=16),
                    timeout=pulse_timeout,
                )
                if result.get("error"):
                    failure_class = "inference_error"
                else:
                    text = result.get("output") or result.get("text") or str(result)
                    if expected not in text:
                        failure_class = "canary_token_missing"
        except asyncio.TimeoutError:
            failure_class = "timeout"
        except Exception as e:
            logger.debug("Pulse-probe exception for worker %s model %s: %s", worker_id, model_id, e)
            failure_class = "exception"

        latency_s = time.monotonic() - start
        await self._store_pulse_latency(worker_id, model_id, latency_s)

        if _PULSE_METRICS_AVAILABLE:
            _pulse_latency.labels(worker_id=worker_id, model_id=model_id).observe(latency_s)

        # Throttling detection: p95 > multiplier * pool_median → treat as failure
        if failure_class is None and latency_s < pulse_timeout:
            p95 = await self._get_pulse_p95_latency(worker_id, model_id)
            pool_med = await self._get_pool_median_latency(model_id)
            if p95 is not None and pool_med is not None and pool_med > 0:
                if p95 > throttle_mult * pool_med:
                    failure_class = "throttling"

        if failure_class:
            logger.warning(
                "Pulse-probe FAILED worker=%s model=%s latency=%.2fs class=%s",
                worker_id,
                model_id,
                latency_s,
                failure_class,
                extra={
                    "worker_id": worker_id,
                    "model_id": model_id,
                    "latency_s": latency_s,
                    "failure_class": failure_class,
                },
            )
            if _PULSE_METRICS_AVAILABLE:
                _pulse_failure_total.labels(worker_id=worker_id, model_id=model_id, failure_class=failure_class).inc()

            consecutive = self._pulse_failure_counts.get(worker_id, 0) + 1
            self._pulse_failure_counts[worker_id] = consecutive

            if consecutive >= unhealthy_m:
                new_status = NPUWorkerStatus(
                    id=worker_id,
                    status=WorkerStatus.OFFLINE,
                    error_message=f"Pulse-probe: {consecutive} consecutive failures (last: {failure_class})",
                )
                await self._store_and_emit_status(
                    worker_id, new_status, status.status if status else WorkerStatus.UNKNOWN
                )
                logger.error(
                    "Pulse-probe: worker %s marked OFFLINE after %d consecutive failures",
                    worker_id,
                    consecutive,
                )
            elif consecutive >= degrade_k:
                new_status = NPUWorkerStatus(
                    id=worker_id,
                    status=WorkerStatus.DEGRADED,
                    error_message=f"Pulse-probe: {consecutive} consecutive failures (last: {failure_class})",
                )
                await self._store_and_emit_status(
                    worker_id, new_status, status.status if status else WorkerStatus.UNKNOWN
                )
                logger.warning(
                    "Pulse-probe: worker %s marked DEGRADED after %d consecutive failures",
                    worker_id,
                    consecutive,
                )
        else:
            if worker_id in self._pulse_failure_counts:
                del self._pulse_failure_counts[worker_id]
            # Recover DEGRADED → ONLINE on a clean pass
            if status and status.status == WorkerStatus.DEGRADED:
                new_status = NPUWorkerStatus(
                    id=worker_id,
                    status=WorkerStatus.ONLINE,
                    error_message=None,
                )
                await self._store_and_emit_status(worker_id, new_status, WorkerStatus.DEGRADED)
                logger.info("Pulse-probe: worker %s recovered (DEGRADED → ONLINE)", worker_id)
            logger.debug(
                "Pulse-probe OK worker=%s model=%s latency=%.2fs",
                worker_id,
                model_id,
                latency_s,
            )

    async def _pulse_probe_loop(self) -> None:
        """Background loop: probe each healthy worker at a jittered 5-minute cadence (GH#6739)."""
        if not self._pulse_canaries:
            self._load_pulse_canaries()
        base_interval = float(self._pulse_defaults.get("pulse_interval_seconds", 300))
        logger.info("NPU pulse-probe loop started (base interval %ds)", int(base_interval))

        while self._running:
            try:
                for worker_id, cfg in list(self._workers.items()):
                    if not cfg.enabled:
                        continue
                    try:
                        await self._pulse_check_worker(worker_id)
                    except Exception as e:
                        logger.debug("Pulse-probe error for worker %s: %s", worker_id, e)

                # Jitter: ±20 % of base_interval
                jitter = (
                    base_interval * 0.2 * (random.random() * 2 - 1)
                )  # nosec B311 - interval jitter to prevent thundering herd, not cryptographic
                await asyncio.sleep(max(base_interval + jitter, 60))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Pulse-probe loop error: %s", e)
                await asyncio.sleep(TimingConstants.LONG_DELAY)

    # ------------------------------------------------------------------ #
    #  GH#6739 — Load-balancer: deprioritise DEGRADED workers             #
    # ------------------------------------------------------------------ #

    async def get_healthy_workers_sorted(self) -> List[NPUWorkerDetails]:
        """Return workers sorted for task assignment: ONLINE first, then DEGRADED.

        OFFLINE/ERROR/UNKNOWN workers are excluded.  Call sites in the task
        dispatch path should prefer this method over list_workers() so that
        degraded workers receive traffic only when no healthy alternative exists.
        """
        all_workers = await self.list_workers()
        online = [w for w in all_workers if w.status.status == WorkerStatus.ONLINE and w.config.enabled]
        degraded = [w for w in all_workers if w.status.status == WorkerStatus.DEGRADED and w.config.enabled]

        def _by_priority(w: NPUWorkerDetails) -> tuple:
            return (-w.config.priority, w.status.current_load)

        return sorted(online, key=_by_priority) + sorted(degraded, key=_by_priority)

    async def _health_check_loop(self) -> None:
        """Background task that periodically checks worker health"""
        logger.info("NPU worker health check loop started")

        while self._running:
            try:
                # Issue #699: Check all enabled workers with exponential backoff
                enabled_workers = [wid for wid, cfg in self._workers.items() if cfg.enabled]
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
                logger.debug("Health check loop error: %s (NPU workers are optional)", e)
                # Error recovery delay before retry
                await asyncio.sleep(TimingConstants.LONG_DELAY)

    async def _check_worker_health(self, worker_id: str) -> None:
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
            status = NPUWorkerStatus(id=worker_id, status=WorkerStatus.ERROR, error_message=str(e))
            await self._store_and_emit_status(worker_id, status, prev_status_value)

            # Issue #699: Apply exponential backoff for consecutive failures
            self._record_worker_failure(worker_id)

    def _build_healthy_status(self, worker_id: str, health_data: Dict[str, Any]) -> NPUWorkerStatus:
        """Build worker status from health check data (Issue #665: extracted helper)."""
        return NPUWorkerStatus(
            id=worker_id,
            status=(WorkerStatus.ONLINE if health_data.get("status") == "healthy" else WorkerStatus.ERROR),
            current_load=health_data.get("current_load", 0),
            total_tasks_completed=health_data.get("total_tasks", 0),
            uptime_seconds=health_data.get("uptime_seconds", 0.0),
            last_heartbeat=now_utc(),
            error_message=(health_data.get("error") if health_data.get("status") != "healthy" else None),
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

    async def _store_worker_status(self, worker_id: str, status: NPUWorkerStatus) -> None:
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

    async def _emit_worker_event(self, event_type: str, worker_details: NPUWorkerDetails) -> None:
        """Emit worker event via event_manager (Issue #372 - refactored)"""
        try:
            event_data = {
                "event": event_type,
                "worker_id": worker_details.config.id,
                "data": {
                    "status": worker_details.status.status.value,
                    "current_load": worker_details.status.current_load,
                    "timestamp": utc_timestamp(),
                },
            }

            # Add full worker data for certain events (Issue #372, #380)
            if event_type in _WORKER_FULL_DATA_EVENTS:
                event_data["worker"] = worker_details.to_event_dict()

            await publish_event("global", f"npu.{event_type}", event_data, persist=PersistStrategy.NONE)
            logger.debug(f"Emitted event {event_type} for worker {worker_details.config.id}")

        except Exception as e:
            logger.error("Failed to emit worker event: %s", e, exc_info=True)

    async def _get_worker_status(self, worker_id: str) -> NPUWorkerStatus | None:
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

    async def get_worker(self, worker_id: str) -> NPUWorkerDetails | None:
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
            raise ValueError(f"Worker connection test failed: {test_result.error_message}")

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

    async def update_worker(self, worker_id: str, worker_config: NPUWorkerConfig) -> NPUWorkerDetails:
        """Update existing worker configuration"""
        if worker_id not in self._workers:
            raise ValueError(f"Worker with ID '{worker_id}' not found")

        # Ensure ID matches
        if worker_config.id != worker_id:
            raise ValueError("Worker ID cannot be changed")

        # Test new configuration
        test_result = await self.test_worker_connection(worker_config)
        if not test_result.success:
            raise ValueError(f"Worker connection test failed: {test_result.error_message}")

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
            status=(WorkerStatus.ONLINE if heartbeat.status == "online" else WorkerStatus.ERROR),
            current_load=heartbeat.current_load,
            total_tasks_completed=heartbeat.total_tasks_completed,
            total_tasks_failed=heartbeat.total_tasks_failed,
            uptime_seconds=heartbeat.uptime_seconds,
            last_heartbeat=now_utc(),
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

    async def remove_worker(self, worker_id: str) -> None:
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
        await publish_event(
            "global",
            "npu.worker.removed",
            {
                "event": "worker.removed",
                "worker_id": worker_id,
                "data": {"timestamp": utc_timestamp()},
            },
            persist=PersistStrategy.NONE,
        )

    async def test_worker_connection(self, worker_config: NPUWorkerConfig) -> WorkerTestResult:
        """Test connection to a worker"""
        from services.npu_profile_suggester import suggest_profile  # GH#6738: lazy import

        client = NPUWorkerClient(worker_config.url)

        try:
            start_time = now_utc()

            # Perform health check with timeout
            health_data = await asyncio.wait_for(
                client.check_health(),
                timeout=self._load_balancing_config.timeout_seconds,
            )

            end_time = now_utc()
            response_time_ms = (end_time - start_time).total_seconds() * 1000

            # GH#6738: derive profile + model suggestions from capabilities in health_data
            suggestion = suggest_profile(health_data)

            return WorkerTestResult(
                worker_id=worker_config.id,
                success=health_data.get("status") == "healthy",
                response_time_ms=response_time_ms,
                status_code=200,
                health_data=health_data,
                recommended_profile=suggestion.recommended_profile,
                recommended_models=suggestion.recommended_models,
                vram_gb=suggestion.vram_gb,
                compute_class=suggestion.compute_class,
                capabilities_summary=suggestion.capabilities_summary,
            )

        except asyncio.TimeoutError:
            return WorkerTestResult(
                worker_id=worker_config.id,
                success=False,
                error_message=f"Connection timeout after {self._load_balancing_config.timeout_seconds}s",
            )

        except Exception as e:
            return WorkerTestResult(worker_id=worker_config.id, success=False, error_message=str(e))

        finally:
            await client.close()

    async def get_worker_metrics(self, worker_id: str) -> NPUWorkerMetrics | None:
        """Get performance metrics for a worker"""
        return await self._get_worker_metrics(worker_id)

    async def _get_worker_metrics(self, worker_id: str) -> NPUWorkerMetrics | None:
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

    async def _is_worker_heartbeat_expired(self, worker_id: str) -> bool:
        """Return True if the worker's heartbeat key has expired or is missing (#1769).

        Args:
            worker_id: ID of the worker to check
        """
        if not self.redis_client:
            return False
        try:
            key = f"npu:worker:{worker_id}:status"
            ttl = await self.redis_client.ttl(key)
            # ttl == -2 means key does not exist; ttl == -1 means no expiry (treat as alive)
            return ttl == -2
        except Exception as e:
            logger.error("Failed to check heartbeat TTL for worker %s: %s", worker_id, e)
            return False

    async def _migrate_running_task(
        self,
        task_id: str,
        running_key: str,
        pending_key: str,
        failed_key: str,
        tasks_hash: str,
        max_retries: int,
    ) -> None:
        """Move one task from running back to pending or to failed (#1769).

        Args:
            task_id: Task identifier
            running_key: Redis key for the running ZSET
            pending_key: Redis key for the pending ZSET
            failed_key: Redis key for the failed ZSET
            tasks_hash: Redis hash storing task data
            max_retries: Maximum allowed retries before moving to failed
        """
        try:
            raw = await self.redis_client.hget(tasks_hash, task_id)
            task_data = json.loads(raw) if raw else {}
            metadata = task_data.get("metadata") or {}
            retry_count = metadata.get("retry_count", 0) + 1

            await self.redis_client.zrem(running_key, task_id)

            if retry_count <= max_retries:
                metadata["retry_count"] = retry_count
                task_data["metadata"] = metadata
                await self.redis_client.hset(tasks_hash, task_id, json.dumps(task_data))
                score = int(time.time())
                await self.redis_client.zadd(pending_key, {task_id: score})
                logger.info(
                    "Failover: re-queued task %s (retry %d/%d)",
                    task_id,
                    retry_count,
                    max_retries,
                )
            else:
                await self.redis_client.zadd(failed_key, {task_id: int(time.time())})
                logger.warning(
                    "Failover: task %s exceeded max_retries (%d), moved to failed",
                    task_id,
                    max_retries,
                )
        except Exception as e:
            logger.error("Failed to migrate task %s during failover: %s", task_id, e)

    def _worker_tasks_key(self, queue_name: str, worker_id: str) -> str:
        """Return the Redis SET key that tracks tasks assigned to a worker (#2496).

        Args:
            queue_name: Base name for the task queue Redis keys
            worker_id: ID of the worker

        Returns:
            Redis key string for the worker's task set
        """
        return f"{queue_name}:worker:{worker_id}:tasks"

    async def assign_task_to_worker(self, queue_name: str, worker_id: str, task_id: str) -> None:
        """Record that task_id is now running on worker_id (#2496).

        Call this whenever a task is dispatched to a specific worker so that
        the failover monitor can migrate only that worker's tasks on failure.

        Args:
            queue_name: Base name for the task queue Redis keys
            worker_id: ID of the worker that will execute the task
            task_id: ID of the task being assigned
        """
        if not self.redis_client:
            return
        try:
            key = self._worker_tasks_key(queue_name, worker_id)
            await self.redis_client.sadd(key, task_id)
            logger.debug("Assigned task %s to worker %s", task_id, worker_id)
        except Exception as e:
            logger.error("Failed to assign task %s to worker %s: %s", task_id, worker_id, e)
            # Re-raise so the caller (_worker_loop) does not process the task
            # without tracking.  An untracked task would be invisible to failover
            # and could be silently lost on worker failure (#2985).
            raise

    async def release_worker_task(self, queue_name: str, worker_id: str, task_id: str) -> None:
        """Remove task_id from the worker's task set on completion or cancellation (#2496).

        Call this when a task finishes (success or failure) so the per-worker
        set stays accurate and the failover monitor does not re-queue it.

        Args:
            queue_name: Base name for the task queue Redis keys
            worker_id: ID of the worker that executed the task
            task_id: ID of the task being released
        """
        if not self.redis_client:
            return
        try:
            key = self._worker_tasks_key(queue_name, worker_id)
            await self.redis_client.srem(key, task_id)
            logger.debug("Released task %s from worker %s", task_id, worker_id)
        except Exception as e:
            logger.error("Failed to release task %s from worker %s: %s", task_id, worker_id, e)

    async def _failover_dead_worker(
        self,
        worker_id: str,
        queue_name: str,
        max_retries: int,
    ) -> None:
        """Re-queue only the dead worker's tasks and remove it from the registry (#1769, #2496).

        Primary source: per-worker task SET ({queue}:worker:{worker_id}:tasks),
        populated by assign_task_to_worker() callers (#2944).  When the SET is
        empty (e.g. on existing deployments before callers were wired) the method
        falls back to the global {queue}:running ZSET so that task migration is
        never silently skipped.

        Args:
            worker_id: ID of the dead worker
            queue_name: Base name for the task queue Redis keys
            max_retries: Maximum retries before a task is moved to failed
        """
        running_key = f"{queue_name}:running"
        pending_key = f"{queue_name}:pending"
        failed_key = f"{queue_name}:failed"
        tasks_hash = f"{queue_name}:tasks"
        worker_tasks_key = self._worker_tasks_key(queue_name, worker_id)

        task_ids = await self.redis_client.smembers(worker_tasks_key)
        if not task_ids:
            # Per-worker SET is empty.  In a multi-worker deployment the global
            # running ZSET contains tasks from ALL live workers, so migrating it
            # would incorrectly steal work from healthy workers (#2985).  Instead,
            # log a WARNING and skip migration — stale running tasks will be
            # reclaimed by the global retry/timeout mechanism.
            logger.warning(
                "Failover: per-worker SET empty for %s — skipping migration to "
                "avoid stealing tasks from other workers. Stale tasks will be "
                "reclaimed by the global retry mechanism (#2985).",
                worker_id,
            )
            task_ids = set()
        else:
            logger.info(
                "Failover: migrating %d tasks from per-worker SET for worker %s",
                len(task_ids),
                worker_id,
            )

        for task_id in task_ids:
            await self._migrate_running_task(
                task_id,
                running_key,
                pending_key,
                failed_key,
                tasks_hash,
                max_retries,
            )

        # Remove per-worker task set and worker status/registry
        await self.redis_client.delete(worker_tasks_key)
        await self.redis_client.delete(f"npu:worker:{worker_id}:status")
        await self.redis_client.delete(f"npu:worker:{worker_id}:metrics")
        self._workers.pop(worker_id, None)
        logger.info("Failover: removed dead worker %s from registry", worker_id)

    async def failover_monitor(
        self,
        queue_name: str = "autobot_tasks",
        check_interval: int = 30,
        max_retries: int = 3,
    ) -> None:
        """Periodically detect dead workers and re-queue their tasks (#1769).

        Scans registered workers for expired heartbeat keys. When a heartbeat
        has expired the worker is considered dead: its running tasks are moved
        back to pending (up to max_retries) or to failed when retries are
        exhausted.

        Args:
            queue_name: Base name for the task queue Redis keys
            check_interval: Seconds between scans
            max_retries: Maximum re-queue attempts before marking a task failed
        """
        logger.info(
            "Failover monitor started (queue=%s, interval=%ds)",
            queue_name,
            check_interval,
        )
        while True:
            try:
                worker_ids = list(self._workers.keys())
                for worker_id in worker_ids:
                    if await self._is_worker_heartbeat_expired(worker_id):
                        logger.warning(
                            "Failover: worker %s heartbeat expired, starting failover",
                            worker_id,
                        )
                        await self._failover_dead_worker(worker_id, queue_name, max_retries)
            except Exception:
                logger.exception("Failover monitor encountered an unexpected error")
            await asyncio.sleep(check_interval)

    def get_load_balancing_config(self) -> LoadBalancingConfig:
        """Get current load balancing configuration"""
        return self._load_balancing_config

    async def update_load_balancing_config(self, config: LoadBalancingConfig) -> None:
        """Update load balancing configuration"""
        self._load_balancing_config = config
        await self._save_workers_to_config()
        logger.info("Updated load balancing config: %s", config.strategy)


# Global worker manager instance (thread-safe)
import asyncio as _asyncio_lock

_worker_manager: NPUWorkerManager | None = None
_worker_manager_lock = _asyncio_lock.Lock()


async def get_worker_manager(redis_client=None) -> NPUWorkerManager:
    """Get or create global worker manager instance (thread-safe)."""
    global _worker_manager

    if _worker_manager is None:
        async with _worker_manager_lock:
            # Double-check after acquiring lock
            if _worker_manager is None:
                _worker_manager = NPUWorkerManager(redis_client=redis_client)
                await _worker_manager.initialize()
                await _worker_manager.start_health_monitoring()

    return _worker_manager
