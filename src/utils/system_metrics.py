# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Metrics Collection and Monitoring
Provides real-time metrics for AutoBot system components.
"""

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
import psutil

from src.unified_config_manager import UnifiedConfigManager

# Create singleton config instance
config = UnifiedConfigManager()
from src.constants.network_constants import NetworkConstants
from src.utils.http_client import get_http_client
from src.utils.redis_client import get_redis_client


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
    """Collects and aggregates system metrics in real-time"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # REFACTORED: Centralized Redis client management
        # Don't cache clients - always use get_redis_client() for proper connection pooling
        self._metrics_buffer = deque(maxlen=1000)  # Buffer for recent metrics
        self._collection_interval = config.get(
            "monitoring.metrics.collection_interval", 5
        )
        self._retention_hours = config.get("monitoring.metrics.retention_hours", 24)
        self._is_collecting = False
        self._auth_error_logged = False  # Track if auth error was already logged

        # Metric categories to collect
        self.metric_categories = {
            "system": ["cpu_percent", "memory_percent", "disk_usage", "network_io"],
            "services": ["backend_health", "redis_health", "ollama_health"],
            "performance": ["response_times", "error_rates", "throughput"],
            "knowledge_base": ["search_queries", "cache_hits", "vector_count"],
            "llm": ["ollama_requests", "model_switches", "token_usage"],
        }

    async def _get_redis_client(self, database: str = "metrics"):
        """
        Get Redis client for specified database using centralized client management.

        REFACTORED: Always use get_redis_client() for proper connection pooling.
        Do not cache clients - let the centralized manager handle that.

        Args:
            database: Redis database name ("metrics", "knowledge", etc.)

        Returns:
            Redis client or None if unavailable
        """
        try:
            client = get_redis_client(database=database, async_client=True)
            if asyncio.iscoroutine(client):
                client = await client
            return client
        except Exception as e:
            self.logger.error(f"Failed to get {database} Redis client: {e}")
            return None

    async def collect_system_metrics(self) -> Dict[str, SystemMetric]:
        """Collect system-level metrics (CPU, memory, disk, network)"""
        metrics = {}
        timestamp = time.time()

        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=None)
            metrics["cpu_percent"] = SystemMetric(
                timestamp=timestamp,
                name="cpu_percent",
                value=cpu_percent,
                unit="percent",
                category="system",
                metadata={"cores": psutil.cpu_count()},
            )

            # Memory metrics
            memory = psutil.virtual_memory()
            metrics["memory_percent"] = SystemMetric(
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

            # Disk usage
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100
            metrics["disk_usage"] = SystemMetric(
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

            # Network I/O
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

        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")

        return metrics

    async def collect_service_health(self) -> Dict[str, SystemMetric]:
        """Collect health metrics for AutoBot services"""
        metrics = {}
        timestamp = time.time()

        # Service endpoints to check
        services = {
            "backend": (
                f"http://{config.get_host('backend')}:{config.get_port('backend')}/api/health"
            ),
            "redis": None,  # Special handling for Redis
            "ollama": (
                f"http://{config.get_host('ollama')}:{config.get_port('ollama')}/api/tags"
            ),
        }

        # HTTP timeout for health checks
        timeout = aiohttp.ClientTimeout(total=5)

        # Use singleton HTTP client for connection pooling
        http_client = get_http_client()
        for service_name, url in services.items():
            try:
                if service_name == "redis":
                    # Special Redis health check
                    redis_client = await self._get_redis_client()
                    if redis_client:
                        # Handle both sync and async Redis clients
                        try:
                            if hasattr(redis_client, "ping"):
                                ping_result = redis_client.ping()
                                if asyncio.iscoroutine(ping_result):
                                    await ping_result
                                health_value = 1.0
                            else:
                                health_value = 0.0
                        except Exception as ping_error:
                            self.logger.warning(f"Redis ping failed: {ping_error}")
                            health_value = 0.0
                    else:
                        health_value = 0.0
                else:
                    # HTTP health check
                    start_time = time.time()
                    async with await http_client.get(url, timeout=timeout) as response:
                        response_time = time.time() - start_time
                        health_value = 1.0 if response.status == 200 else 0.0

                        # Also collect response time
                        metrics[f"{service_name}_response_time"] = SystemMetric(
                            timestamp=timestamp,
                            name=f"{service_name}_response_time",
                            value=response_time * 1000,  # Convert to ms
                            unit="ms",
                            category="performance",
                        )

                        metrics[f"{service_name}_health"] = SystemMetric(
                            timestamp=timestamp,
                            name=f"{service_name}_health",
                            value=health_value,
                            unit="status",
                            category="services",
                        )

            except Exception as e:
                self.logger.warning(f"Health check failed for {service_name}: {e}")
                metrics[f"{service_name}_health"] = SystemMetric(
                    timestamp=timestamp,
                    name=f"{service_name}_health",
                    value=0.0,
                    unit="status",
                    category="services",
                    metadata={"error": str(e)},
                )

        return metrics

    async def collect_knowledge_base_metrics(self) -> Dict[str, SystemMetric]:
        """Collect knowledge base performance metrics"""
        metrics = {}
        timestamp = time.time()

        try:
            # REFACTORED: Use centralized client management for "knowledge" database
            # Knowledge base data (doc:*, kb_cache:*) is stored in the "knowledge" Redis database
            kb_redis_client = await self._get_redis_client(database="knowledge")

            if not kb_redis_client:
                self.logger.debug(
                    "Knowledge base Redis client not available, skipping KB metrics"
                )
                return metrics

            # Get knowledge base statistics from Redis
            # Count vector entries
            vector_count = 0
            async for key in kb_redis_client.scan_iter(match="doc:*"):
                vector_count += 1

            metrics["kb_vector_count"] = SystemMetric(
                timestamp=timestamp,
                name="kb_vector_count",
                value=vector_count,
                unit="count",
                category="knowledge_base",
            )

            # Get cache statistics
            cache_count = 0
            async for key in kb_redis_client.scan_iter(match="kb_cache:*"):
                cache_count += 1

            metrics["kb_cache_entries"] = SystemMetric(
                timestamp=timestamp,
                name="kb_cache_entries",
                value=cache_count,
                unit="count",
                category="knowledge_base",
            )

            # Estimate cache hit rate (if available)
            cache_stats_key = "kb_cache_stats"
            cache_stats = await kb_redis_client.hgetall(cache_stats_key)
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

        except Exception as e:
            # CRITICAL FIX: Don't spam logs with authentication errors - log once and skip
            error_msg = str(e)
            if "Authentication required" in error_msg or "NOAUTH" in error_msg:
                if not self._auth_error_logged:
                    self.logger.warning(
                        "Knowledge base metrics collection skipped: Redis authentication required. "
                        "Configure Redis credentials in get_redis_client() to enable KB metrics."
                    )
                    self._auth_error_logged = True
            else:
                self.logger.error(f"Error collecting knowledge base metrics: {e}")

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
                self.logger.error(f"Metric collection error: {result}")

        return all_metrics

    async def store_metrics(self, metrics: Dict[str, SystemMetric]) -> bool:
        """Store metrics in Redis for historical tracking"""
        try:
            redis_client = await self._get_redis_client()
            if not redis_client:
                return False

            # Use pipeline for efficient bulk operations
            async with redis_client.pipeline() as pipe:
                for metric in metrics.values():
                    # Store metric in time series format
                    key = f"metrics:{metric.category}:{metric.name}"

                    # Store as sorted set with timestamp as score
                    metric_data = {
                        "value": metric.value,
                        "unit": metric.unit,
                        "metadata": json.dumps(metric.metadata or {}),
                    }

                    pipe.zadd(key, {json.dumps(metric_data): metric.timestamp})

                    # Set expiration for automatic cleanup
                    expire_seconds = self._retention_hours * 3600
                    pipe.expire(key, expire_seconds)

                # Execute all commands
                await pipe.execute()

            # Also store in buffer for real-time access
            for metric in metrics.values():
                self._metrics_buffer.append(metric)

            return True

        except Exception as e:
            # CRITICAL FIX: Don't spam logs with authentication errors - log once and skip
            error_msg = str(e)
            if "Authentication required" in error_msg or "NOAUTH" in error_msg:
                if not self._auth_error_logged:
                    self.logger.warning(
                        "Metrics storage skipped: Redis authentication required. "
                        "Metrics will be buffered in memory only until authentication is configured."
                    )
                    self._auth_error_logged = True
            else:
                self.logger.error(f"Error storing metrics: {e}")
            return False

    async def get_recent_metrics(
        self, category: str = None, minutes: int = 10
    ) -> List[SystemMetric]:
        """Get recent metrics from the buffer or Redis"""
        try:
            if category:
                # Filter by category from buffer
                cutoff_time = time.time() - (minutes * 60)
                return [
                    metric
                    for metric in self._metrics_buffer
                    if metric.category == category and metric.timestamp >= cutoff_time
                ]
            else:
                # Return all recent metrics
                cutoff_time = time.time() - (minutes * 60)
                return [
                    metric
                    for metric in self._metrics_buffer
                    if metric.timestamp >= cutoff_time
                ]
        except Exception as e:
            self.logger.error(f"Error getting recent metrics: {e}")
            return []

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
                        else "degraded" if overall_health > 0.5 else "critical"
                    ),
                }

            return summary

        except Exception as e:
            self.logger.error(f"Error generating metric summary: {e}")
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
                # Collect metrics
                metrics = await self.collect_all_metrics()

                # Store metrics
                if metrics:
                    await self.store_metrics(metrics)
                    self.logger.debug(f"Collected and stored {len(metrics)} metrics")

                # Wait for next collection
                await asyncio.sleep(self._collection_interval)

            except Exception as e:
                self.logger.error(f"Error in metrics collection loop: {e}")
                await asyncio.sleep(self._collection_interval)

    async def stop_collection(self):
        """Stop metrics collection"""
        self.logger.info("Stopping metrics collection")
        self._is_collecting = False


# Global metrics collector instance
_metrics_collector = None


def get_metrics_collector() -> SystemMetricsCollector:
    """Get the global metrics collector instance"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = SystemMetricsCollector()
    return _metrics_collector
