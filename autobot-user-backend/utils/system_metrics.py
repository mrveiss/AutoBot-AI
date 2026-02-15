# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Metrics Collection and Monitoring
Provides real-time metrics for AutoBot system components.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict

import aiohttp
import psutil

from config import UnifiedConfigManager

# Create singleton config instance
config = UnifiedConfigManager()
from autobot_shared.http_client import get_http_client
from autobot_shared.redis_client import get_redis_client


@dataclass
class SystemMetric:
    """Individual system metric data point"""

    timestamp: float
    name: str
    value: float
    unit: str
    category: str
    metadata: Dict[str, Any] = None


class SystemMetricsCollector:
    """
    Collects and aggregates system metrics in real-time.

    Phase 5 (Issue #348): Refactored to use Prometheus as the primary metrics store.
    Legacy in-memory buffers and Redis persistence have been removed.
    All metrics are now pushed directly to Prometheus.
    """

    def __init__(self):
        """Initialize system metrics collector with Prometheus integration."""
        self.logger = logging.getLogger(__name__)
        self._collection_interval = config.get(
            "monitoring.metrics.collection_interval", 5
        )
        self._is_collecting = False
        self._auth_error_logged = False  # Track if auth error was already logged

        # Phase 5 (Issue #348): Prometheus is now the primary metrics store
        try:
            from monitoring.prometheus_metrics import get_metrics_manager

            self.prometheus = get_metrics_manager()
        except (ImportError, Exception) as e:
            self.logger.warning("Prometheus metrics not available: %s", e)
            self.prometheus = None

        # Metric categories to collect
        self.metric_categories = {
            "system": ["cpu_percent", "memory_percent", "disk_usage", "network_io"],
            "services": ["backend_health", "redis_health", "ollama_health"],
            "performance": ["response_times", "error_rates", "throughput"],
            "knowledge_base": ["search_queries", "cache_hits", "vector_count"],
            "llm": ["ollama_requests", "model_switches", "token_usage"],
        }

    def _collect_cpu_metric(self, timestamp: float) -> tuple:
        """Collect CPU metric (Issue #665: extracted helper)."""
        cpu_percent = psutil.cpu_percent(interval=None)
        metric = SystemMetric(
            timestamp=timestamp,
            name="cpu_percent",
            value=cpu_percent,
            unit="percent",
            category="system",
            metadata={"cores": psutil.cpu_count()},
        )
        if self.prometheus:
            self.prometheus.update_system_cpu(cpu_percent)
        return "cpu_percent", metric

    def _collect_memory_metric(self, timestamp: float) -> tuple:
        """Collect memory metric (Issue #665: extracted helper)."""
        memory = psutil.virtual_memory()
        metric = SystemMetric(
            timestamp=timestamp,
            name="memory_percent",
            value=memory.percent,
            unit="percent",
            category="system",
            metadata={
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
            },
        )
        if self.prometheus:
            self.prometheus.update_system_memory(memory.percent)
        return "memory_percent", metric

    def _collect_disk_metric(self, timestamp: float) -> tuple:
        """Collect disk usage metric (Issue #665: extracted helper)."""
        disk = psutil.disk_usage("/")
        disk_percent = (disk.used / disk.total) * 100
        metric = SystemMetric(
            timestamp=timestamp,
            name="disk_usage",
            value=disk_percent,
            unit="percent",
            category="system",
            metadata={
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
            },
        )
        if self.prometheus:
            self.prometheus.update_system_disk("/", disk_percent)
        return "disk_usage", metric

    def _collect_network_metrics(self, timestamp: float) -> Dict[str, SystemMetric]:
        """Collect network I/O metrics (Issue #665: extracted helper)."""
        metrics = {}
        network = psutil.net_io_counters()
        if network:
            metrics["network_bytes_sent"] = SystemMetric(
                timestamp=timestamp,
                name="network_bytes_sent",
                value=network.bytes_sent,
                unit="bytes",
                category="system",
            )
            metrics["network_bytes_recv"] = SystemMetric(
                timestamp=timestamp,
                name="network_bytes_recv",
                value=network.bytes_recv,
                unit="bytes",
                category="system",
            )
            if self.prometheus:
                self.prometheus.record_network_bytes("sent", network.bytes_sent)
                self.prometheus.record_network_bytes("recv", network.bytes_recv)
        return metrics

    async def collect_system_metrics(self) -> Dict[str, SystemMetric]:
        """Collect system-level metrics (CPU, memory, disk, network)"""
        metrics = {}
        timestamp = time.time()

        try:
            # Collect all metrics using helpers
            for collector in [
                self._collect_cpu_metric,
                self._collect_memory_metric,
                self._collect_disk_metric,
            ]:
                key, metric = collector(timestamp)
                metrics[key] = metric

            # Network metrics return multiple entries
            metrics.update(self._collect_network_metrics(timestamp))

        except Exception as e:
            self.logger.error("Error collecting system metrics: %s", e)

        return metrics

    async def _check_redis_health(self) -> float:
        """Check Redis service health (Issue #315: extracted).

        Returns:
            1.0 if healthy, 0.0 if unhealthy
        """
        try:
            redis_client = get_redis_client(database="main", async_client=True)
            if asyncio.iscoroutine(redis_client):
                redis_client = await redis_client

            if not redis_client or not hasattr(redis_client, "ping"):
                return 0.0

            # Issue #361 - always await for async client
            await redis_client.ping()
            return 1.0

        except Exception as ping_error:
            self.logger.warning("Redis ping failed: %s", ping_error)
            return 0.0

    async def _check_http_service_health(
        self,
        http_client,
        url: str,
        timeout: aiohttp.ClientTimeout,
    ) -> tuple[float, float | None]:
        """Check HTTP service health (Issue #315: extracted).

        Args:
            http_client: HTTP client instance
            url: Service URL to check
            timeout: Request timeout

        Returns:
            Tuple of (health_value, response_time_ms or None on failure)
        """
        start_time = time.time()
        async with await http_client.get(url, timeout=timeout) as response:
            response_time = time.time() - start_time
            health_value = 1.0 if response.status == 200 else 0.0
            return health_value, response_time * 1000  # Convert to ms

    def _create_health_metric(
        self,
        service_name: str,
        health_value: float,
        timestamp: float,
        error: str | None = None,
    ) -> SystemMetric:
        """Create a health metric for a service (Issue #315: extracted).

        Args:
            service_name: Name of the service
            health_value: Health value (1.0 = healthy, 0.0 = unhealthy)
            timestamp: Metric timestamp
            error: Optional error message

        Returns:
            SystemMetric instance
        """
        metadata = {"error": error} if error else None
        return SystemMetric(
            timestamp=timestamp,
            name=f"{service_name}_health",
            value=health_value,
            unit="status",
            category="services",
            metadata=metadata,
        )

    def _update_prometheus_health(
        self,
        service_name: str,
        health_value: float,
        response_time: float | None = None,
    ) -> None:
        """Update Prometheus with service health (Issue #315: extracted).

        Args:
            service_name: Name of the service
            health_value: Health value (1.0 = healthy, 0.0 = unhealthy)
            response_time: Optional response time in seconds
        """
        if not self.prometheus:
            return

        status = "online" if health_value == 1.0 else "offline"
        self.prometheus.update_service_status(service_name, status)

        if response_time is not None:
            self.prometheus.record_service_response_time(service_name, response_time)

    def _get_service_endpoints(self) -> Dict[str, str | None]:
        """
        Get service endpoints for health checks.

        Issue #620, #876: Backend self-check removed to prevent circular deadlock.

        Returns:
            Dictionary mapping service names to their health check URLs
        """
        return {
            # Issue #876: Removed backend self-health-check - backend checking
            # itself during initialization creates circular deadlock.
            # Backend health is implicit: if metrics are being collected, backend is running.
            "redis": None,  # Special handling for Redis
            "ollama": (
                f"http://{config.get_host('ollama')}:{config.get_port('ollama')}/api/tags"
            ),
        }

    async def _check_single_service(
        self,
        service_name: str,
        url: str | None,
        http_client,
        timeout: aiohttp.ClientTimeout,
        timestamp: float,
        metrics: Dict[str, SystemMetric],
    ) -> None:
        """
        Check health of a single service and update metrics.

        Issue #620.

        Args:
            service_name: Name of the service
            url: Health check URL (None for Redis)
            http_client: HTTP client instance
            timeout: Request timeout
            timestamp: Metric timestamp
            metrics: Dictionary to add metrics to
        """
        health_value = 0.0
        response_time_ms = None
        error_msg = None

        try:
            if service_name == "redis":
                health_value = await self._check_redis_health()
            else:
                health_value, response_time_ms = await self._check_http_service_health(
                    http_client, url, timeout
                )
                metrics[f"{service_name}_response_time"] = SystemMetric(
                    timestamp=timestamp,
                    name=f"{service_name}_response_time",
                    value=response_time_ms,
                    unit="ms",
                    category="performance",
                )
        except Exception as e:
            self.logger.warning("Health check failed for %s: %s", service_name, e)
            error_msg = str(e)

        metrics[f"{service_name}_health"] = self._create_health_metric(
            service_name, health_value, timestamp, error_msg
        )

        response_time_sec = response_time_ms / 1000 if response_time_ms else None
        self._update_prometheus_health(service_name, health_value, response_time_sec)

    async def collect_service_health(self) -> Dict[str, SystemMetric]:
        """
        Collect health metrics for AutoBot services.

        Issue #620: Refactored to use helper methods for reduced function length.
        """
        metrics = {}
        timestamp = time.time()
        services = self._get_service_endpoints()
        timeout = aiohttp.ClientTimeout(total=5)
        http_client = get_http_client()

        for service_name, url in services.items():
            await self._check_single_service(
                service_name, url, http_client, timeout, timestamp, metrics
            )

        return metrics

    async def _get_kb_redis_client(self):
        """
        Get async Redis client for knowledge base database.

        Issue #620: Extracted from collect_knowledge_base_metrics.

        Returns:
            Async Redis client or None if unavailable
        """
        kb_redis_client = get_redis_client(database="knowledge", async_client=True)
        if asyncio.iscoroutine(kb_redis_client):
            kb_redis_client = await kb_redis_client
        return kb_redis_client

    async def _collect_kb_vector_metrics(
        self, redis_client, timestamp: float, metrics: Dict[str, "SystemMetric"]
    ) -> None:
        """
        Collect knowledge base vector count metrics.

        Issue #620: Extracted from collect_knowledge_base_metrics.

        Args:
            redis_client: Async Redis client
            timestamp: Metric timestamp
            metrics: Dictionary to add metrics to
        """
        vector_count = 0
        async for key in redis_client.scan_iter(match="doc:*"):
            vector_count += 1

        metrics["kb_vector_count"] = SystemMetric(
            timestamp=timestamp,
            name="kb_vector_count",
            value=vector_count,
            unit="count",
            category="knowledge_base",
        )

    async def _collect_kb_cache_metrics(
        self, redis_client, timestamp: float, metrics: Dict[str, "SystemMetric"]
    ) -> None:
        """
        Collect knowledge base cache metrics including hit rate.

        Issue #620: Extracted from collect_knowledge_base_metrics.

        Args:
            redis_client: Async Redis client
            timestamp: Metric timestamp
            metrics: Dictionary to add metrics to
        """
        # Count cache entries
        cache_count = 0
        async for key in redis_client.scan_iter(match="kb_cache:*"):
            cache_count += 1

        metrics["kb_cache_entries"] = SystemMetric(
            timestamp=timestamp,
            name="kb_cache_entries",
            value=cache_count,
            unit="count",
            category="knowledge_base",
        )

        # Calculate cache hit rate if stats available
        cache_stats = await redis_client.hgetall("kb_cache_stats")
        if cache_stats:
            hits = int(cache_stats.get(b"hits") or cache_stats.get("hits", 0))
            misses = int(cache_stats.get(b"misses") or cache_stats.get("misses", 0))
            total_requests = hits + misses

            if total_requests > 0:
                hit_rate = (hits / total_requests) * 100
                metrics["kb_cache_hit_rate"] = SystemMetric(
                    timestamp=timestamp,
                    name="kb_cache_hit_rate",
                    value=hit_rate,
                    unit="percent",
                    category="knowledge_base",
                )

    def _handle_kb_metrics_error(self, error: Exception) -> None:
        """
        Handle knowledge base metrics collection errors.

        Issue #620: Extracted from collect_knowledge_base_metrics.

        Args:
            error: Exception that occurred
        """
        error_msg = str(error)
        if "Authentication required" in error_msg or "NOAUTH" in error_msg:
            if not self._auth_error_logged:
                self.logger.warning(
                    "Knowledge base metrics collection skipped: Redis authentication required. "
                    "Configure Redis credentials in get_redis_client() to enable KB metrics."
                )
                self._auth_error_logged = True
        else:
            self.logger.error("Error collecting knowledge base metrics: %s", error)

    async def collect_knowledge_base_metrics(self) -> Dict[str, SystemMetric]:
        """
        Collect knowledge base performance metrics.

        Issue #620: Refactored to use helper methods.
        """
        metrics = {}
        timestamp = time.time()

        try:
            # Issue #620: Use helper to get Redis client
            kb_redis_client = await self._get_kb_redis_client()

            if not kb_redis_client:
                self.logger.debug(
                    "Knowledge base Redis client not available, skipping KB metrics"
                )
                return metrics

            # Issue #620: Use helpers for metric collection
            await self._collect_kb_vector_metrics(kb_redis_client, timestamp, metrics)
            await self._collect_kb_cache_metrics(kb_redis_client, timestamp, metrics)

        except Exception as e:
            # Issue #620: Use helper for error handling
            self._handle_kb_metrics_error(e)

        return metrics

    async def collect_all_metrics(self) -> Dict[str, SystemMetric]:
        """Collect all system metrics"""
        all_metrics = {}

        # Collect different metric categories
        metric_collectors = [
            self.collect_system_metrics(),
            self.collect_service_health(),
            self.collect_knowledge_base_metrics(),
        ]

        # Run collectors concurrently
        results = await asyncio.gather(*metric_collectors, return_exceptions=True)

        # Combine results
        for result in results:
            if isinstance(result, dict):
                all_metrics.update(result)
            elif isinstance(result, Exception):
                self.logger.error("Metric collection error: %s", result)

        return all_metrics

    async def get_metric_summary(self) -> Dict[str, Any]:
        """Get summary of current system status"""
        try:
            current_metrics = await self.collect_all_metrics()

            summary = {
                "timestamp": time.time(),
                "system": {},
                "services": {},
                "performance": {},
                "knowledge_base": {},
            }

            # Organize metrics by category
            for metric in current_metrics.values():
                if metric.category in summary:
                    summary[metric.category][metric.name] = {
                        "value": metric.value,
                        "unit": metric.unit,
                        "metadata": metric.metadata,
                    }

            # Calculate overall system health
            service_healths = [
                metric.value
                for metric in current_metrics.values()
                if metric.category == "services" and "health" in metric.name
            ]

            if service_healths:
                overall_health = sum(service_healths) / len(service_healths)
                summary["overall_health"] = {
                    "value": overall_health * 100,
                    "unit": "percent",
                    "status": (
                        "healthy"
                        if overall_health > 0.8
                        else "degraded"
                        if overall_health > 0.5
                        else "critical"
                    ),
                }

            return summary

        except Exception as e:
            self.logger.error("Error generating metric summary: %s", e)
            return {"error": str(e)}

    async def start_collection(self):
        """Start continuous metrics collection"""
        if self._is_collecting:
            self.logger.warning("Metrics collection already running")
            return

        self._is_collecting = True
        self.logger.info(
            f"Starting metrics collection (interval: {self._collection_interval}s)"
        )

        while self._is_collecting:
            try:
                # Phase 5 (Issue #348): Collect and push to Prometheus only
                # Redis storage and in-memory buffers have been removed
                metrics = await self.collect_all_metrics()

                if metrics:
                    self.logger.debug(
                        "Collected %s metrics (pushed to Prometheus)", len(metrics)
                    )

                # Wait for next collection
                await asyncio.sleep(self._collection_interval)

            except Exception as e:
                self.logger.error("Error in metrics collection loop: %s", e)
                await asyncio.sleep(self._collection_interval)

    async def stop_collection(self):
        """Stop metrics collection"""
        self.logger.info("Stopping metrics collection")
        self._is_collecting = False


# Global metrics collector instance (thread-safe)
import threading

_metrics_collector = None
_metrics_collector_lock = threading.Lock()


def get_metrics_collector() -> SystemMetricsCollector:
    """Get the global metrics collector instance (thread-safe)"""
    global _metrics_collector
    if _metrics_collector is None:
        with _metrics_collector_lock:
            # Double-check after acquiring lock
            if _metrics_collector is None:
                _metrics_collector = SystemMetricsCollector()
    return _metrics_collector
