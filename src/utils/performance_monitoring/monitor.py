# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Monitor Module

Contains the main PerformanceMonitor class that coordinates metric collection,
analysis, and storage using the extracted component modules.

Extracted from performance_monitor.py as part of Issue #381 refactoring.
Extended with Prometheus integration as part of Issue #469.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict
from typing import Any, Callable, Dict, List

# Issue #469: Import Prometheus metrics manager
from src.monitoring.prometheus_metrics import get_metrics_manager
from src.utils.performance_monitoring.analyzers import (
    AlertAnalyzer,
    RecommendationGenerator,
)
from src.utils.performance_monitoring.collectors import (
    GPUCollector,
    MultiModalCollector,
    NPUCollector,
    ServiceCollector,
    SystemCollector,
)
from src.utils.performance_monitoring.decorator import set_redis_client
from src.utils.performance_monitoring.hardware import HardwareDetector
from src.utils.performance_monitoring.types import (
    DEFAULT_COLLECTION_INTERVAL,
    DEFAULT_PERFORMANCE_BASELINES,
    DEFAULT_RETENTION_HOURS,
)

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    Comprehensive performance monitoring system for AutoBot.
    Focuses on GPU/NPU acceleration, multi-modal AI performance, and
    distributed system optimization.

    Note: Renamed from Phase9PerformanceMonitor - "Phase9" naming is deprecated.
    """

    def __init__(self):
        """Initialize performance monitor with hardware detection and thresholds."""
        self.logger = logging.getLogger(__name__)
        self.monitoring_active = False
        self.collection_interval = DEFAULT_COLLECTION_INTERVAL
        self.retention_hours = DEFAULT_RETENTION_HOURS

        # Lock for thread-safe access to shared mutable state
        self._lock = asyncio.Lock()

        # Performance baselines and thresholds
        self.performance_baselines = dict(DEFAULT_PERFORMANCE_BASELINES)

        # Real-time alerting
        self.alert_callbacks: List[Callable] = []

        # Hardware acceleration tracking
        self.gpu_available = HardwareDetector.check_gpu_availability()
        self.npu_available = HardwareDetector.check_npu_availability()

        # Redis client for persistent storage
        self.redis_client = None
        self._initialize_redis()

        # Initialize collectors
        self._gpu_collector = GPUCollector(self.gpu_available)
        self._npu_collector = NPUCollector(self.npu_available)
        self._system_collector = SystemCollector()
        self._service_collector = ServiceCollector(self.redis_client)
        self._multimodal_collector = MultiModalCollector(self.redis_client)

        # Initialize analyzers
        self._alert_analyzer = AlertAnalyzer(self.performance_baselines)
        self._recommendation_generator = RecommendationGenerator()

        # Background monitoring task
        self.monitoring_task = None

        # Metrics buffers for backward compatibility with monitoring API (Issue #427)
        # These store recent metrics for status endpoint access
        self.gpu_metrics_buffer: List[Any] = []
        self.npu_metrics_buffer: List[Any] = []
        self.multimodal_metrics_buffer: List[Any] = []
        self.system_metrics_buffer: List[Any] = []
        self.service_metrics_buffer: Dict[str, List[Any]] = {}

        # Performance alerts buffer (Issue #427)
        self.performance_alerts: List[Dict[str, Any]] = []

        # Issue #469: Prometheus metrics manager for unified monitoring
        self._prometheus = get_metrics_manager()

        self.logger.info("Performance Monitor initialized")
        self.logger.info("GPU Available: %s", self.gpu_available)
        self.logger.info("NPU Available: %s", self.npu_available)

    def _initialize_redis(self):
        """Initialize Redis client for metrics storage."""
        try:
            from src.utils.redis_client import get_redis_client

            self.redis_client = get_redis_client(database="metrics")
            if self.redis_client is None:
                raise Exception("Redis client initialization returned None")

            self.redis_client.ping()
            self.logger.info("Redis client initialized for performance metrics")

            # Set redis client for decorator module
            set_redis_client(self.redis_client)
        except Exception as e:
            self.logger.warning(
                f"Could not initialize Redis for performance metrics: {e}"
            )
            self.redis_client = None

    async def collect_gpu_metrics(self):
        """Collect GPU metrics (delegates to collector)."""
        return await self._gpu_collector.collect()

    async def collect_npu_metrics(self):
        """Collect NPU metrics (delegates to collector)."""
        return await self._npu_collector.collect()

    async def collect_multimodal_metrics(self):
        """Collect multimodal metrics (delegates to collector)."""
        return await self._multimodal_collector.collect()

    async def collect_system_performance_metrics(self):
        """Collect system metrics (delegates to collector)."""
        return await self._system_collector.collect()

    async def collect_service_performance_metrics(self):
        """Collect service metrics (delegates to collector)."""
        return await self._service_collector.collect()

    def _handle_metric_exception(self, metric_name: str, result: Any) -> Any:
        """Handle exception from metric collection (Issue #398: extracted).

        Args:
            metric_name: Name of the metric for logging
            result: Collection result (may be Exception)

        Returns:
            None if exception, original result otherwise
        """
        if isinstance(result, Exception):
            self.logger.error("%s metrics collection failed: %s", metric_name, result)
            return None
        return result

    def _update_metric_buffer(
        self, buffer: List[Any], metrics: Any, max_size: int = 100
    ) -> List[Any]:
        """Update metrics buffer with size limit (Issue #398: extracted).

        Args:
            buffer: Buffer list to update
            metrics: Metrics to append
            max_size: Maximum buffer size

        Returns:
            Updated buffer (may be new list if trimmed)
        """
        if metrics:
            buffer.append(metrics)
            if len(buffer) > max_size:
                return buffer[-max_size:]
        return buffer

    def _update_service_buffer(
        self, service_metrics: List[Any], max_size: int = 100
    ) -> None:
        """Update service metrics buffer by service name (Issue #398: extracted).

        Args:
            service_metrics: List of service metric objects
            max_size: Maximum buffer size per service
        """
        if not service_metrics:
            return

        for service_metric in service_metrics:
            service_name = getattr(service_metric, "service_name", "unknown")
            if service_name not in self.service_metrics_buffer:
                self.service_metrics_buffer[service_name] = []
            self.service_metrics_buffer[service_name].append(service_metric)
            if len(self.service_metrics_buffer[service_name]) > max_size:
                self.service_metrics_buffer[service_name] = self.service_metrics_buffer[
                    service_name
                ][-max_size:]

    def _process_collection_results(
        self, results: List[Any]
    ) -> tuple[Any, Any, Any, Any, List[Any]]:
        """
        Process asyncio.gather results and handle exceptions. Issue #620.

        Args:
            results: Results from asyncio.gather with return_exceptions=True

        Returns:
            Tuple of (gpu_metrics, npu_metrics, multimodal_metrics, system_metrics, service_metrics)
        """
        gpu_metrics = self._handle_metric_exception("GPU", results[0])
        npu_metrics = self._handle_metric_exception("NPU", results[1])
        multimodal_metrics = self._handle_metric_exception("Multimodal", results[2])
        system_metrics = self._handle_metric_exception("System", results[3])
        service_metrics = results[4] if not isinstance(results[4], Exception) else []
        if isinstance(results[4], Exception):
            self.logger.error("Service metrics collection failed: %s", results[4])
        return (
            gpu_metrics,
            npu_metrics,
            multimodal_metrics,
            system_metrics,
            service_metrics,
        )

    def _update_all_metric_buffers(
        self,
        gpu_metrics,
        npu_metrics,
        multimodal_metrics,
        system_metrics,
        service_metrics,
    ) -> None:
        """
        Update all metric buffers with collected data. Issue #620.

        Args:
            gpu_metrics: GPU metrics data
            npu_metrics: NPU metrics data
            multimodal_metrics: Multimodal metrics data
            system_metrics: System metrics data
            service_metrics: Service metrics list
        """
        self.gpu_metrics_buffer = self._update_metric_buffer(
            self.gpu_metrics_buffer, gpu_metrics
        )
        self.npu_metrics_buffer = self._update_metric_buffer(
            self.npu_metrics_buffer, npu_metrics
        )
        self.multimodal_metrics_buffer = self._update_metric_buffer(
            self.multimodal_metrics_buffer, multimodal_metrics
        )
        self.system_metrics_buffer = self._update_metric_buffer(
            self.system_metrics_buffer, system_metrics
        )
        self._update_service_buffer(service_metrics)

    def _build_metrics_response(
        self,
        gpu_metrics,
        npu_metrics,
        multimodal_metrics,
        system_metrics,
        service_metrics,
    ) -> Dict[str, Any]:
        """
        Build the metrics response dictionary. Issue #620.

        Args:
            gpu_metrics: GPU metrics data
            npu_metrics: NPU metrics data
            multimodal_metrics: Multimodal metrics data
            system_metrics: System metrics data
            service_metrics: Service metrics list

        Returns:
            Formatted metrics dictionary
        """
        return {
            "timestamp": time.time(),
            "gpu": asdict(gpu_metrics) if gpu_metrics else None,
            "npu": asdict(npu_metrics) if npu_metrics else None,
            "multimodal": asdict(multimodal_metrics) if multimodal_metrics else None,
            "system": asdict(system_metrics) if system_metrics else None,
            "services": [asdict(s) for s in (service_metrics or [])],
            "collection_successful": True,
        }

    async def collect_all_metrics(self) -> Dict[str, Any]:
        """Collect all performance metrics in parallel. Issue #620: Refactored with helpers."""
        try:
            tasks = [
                self.collect_gpu_metrics(),
                self.collect_npu_metrics(),
                self.collect_multimodal_metrics(),
                self.collect_system_performance_metrics(),
                self.collect_service_performance_metrics(),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)
            gpu, npu, multimodal, system, services = self._process_collection_results(
                results
            )

            self._update_all_metric_buffers(gpu, npu, multimodal, system, services)

            if self.redis_client:
                await self._persist_metrics_to_redis(
                    {
                        "gpu": gpu,
                        "npu": npu,
                        "multimodal": multimodal,
                        "system": system,
                        "services": services,
                    }
                )

            self._push_to_prometheus(gpu, npu, multimodal, system)

            return self._build_metrics_response(gpu, npu, multimodal, system, services)

        except Exception as e:
            self.logger.error("Error collecting all metrics: %s", e)
            return {
                "timestamp": time.time(),
                "collection_successful": False,
                "error": str(e),
            }

    async def _persist_metrics_to_redis(self, metrics: Dict[str, Any]):
        """Persist metrics to Redis for historical analysis."""
        try:
            if not self.redis_client:
                return

            timestamp = time.time()
            retention_seconds = self.retention_hours * 3600

            def _persist_ops():
                pipe = self.redis_client.pipeline()
                for category, metric_data in metrics.items():
                    if metric_data:
                        key = f"performance_metrics:{category}"
                        value = json.dumps(
                            (
                                asdict(metric_data)
                                if hasattr(metric_data, "__dict__")
                                else metric_data
                            ),
                            default=str,
                        )
                        pipe.zadd(key, {value: timestamp})
                        pipe.expire(key, retention_seconds)
                pipe.execute()

            await asyncio.to_thread(_persist_ops)

        except Exception as e:
            self.logger.error("Error persisting metrics to Redis: %s", e)

    def _push_gpu_metrics_to_prometheus(self, gpu_metrics) -> None:
        """Push GPU metrics to Prometheus. Issue #620."""
        if gpu_metrics:
            self._prometheus.set_gpu_available(True)
            self._prometheus.update_gpu_metrics(
                gpu_id="0",
                gpu_name=getattr(gpu_metrics, "name", "NVIDIA GPU"),
                utilization=getattr(gpu_metrics, "utilization_percent", 0),
                memory_utilization=getattr(
                    gpu_metrics, "memory_utilization_percent", 0
                ),
                temperature=getattr(gpu_metrics, "temperature_celsius", 0),
                power_watts=getattr(gpu_metrics, "power_draw_watts", 0),
            )
            if getattr(gpu_metrics, "thermal_throttling", False):
                self._prometheus.record_gpu_throttling("0", "thermal")
            if getattr(gpu_metrics, "power_throttling", False):
                self._prometheus.record_gpu_throttling("0", "power")
        else:
            self._prometheus.set_gpu_available(False)

    def _push_npu_metrics_to_prometheus(self, npu_metrics) -> None:
        """Push NPU metrics to Prometheus. Issue #620."""
        if npu_metrics:
            self._prometheus.set_npu_available(
                getattr(npu_metrics, "hardware_detected", False)
            )
            self._prometheus.set_npu_wsl_limitation(
                getattr(npu_metrics, "wsl_limitation", False)
            )
            self._prometheus.update_npu_metrics(
                utilization=getattr(npu_metrics, "utilization_percent", 0),
                acceleration_ratio=getattr(npu_metrics, "acceleration_ratio", 0),
            )
        else:
            self._prometheus.set_npu_available(False)

    def _push_multimodal_metrics_to_prometheus(self, multimodal_metrics) -> None:
        """Push multimodal processing metrics to Prometheus. Issue #620."""
        if not multimodal_metrics:
            return
        text_time = getattr(multimodal_metrics, "text_processing_time_ms", 0)
        if text_time > 0:
            self._prometheus.record_multimodal_processing(
                "text", text_time / 1000, True
            )
        image_time = getattr(multimodal_metrics, "image_processing_time_ms", 0)
        if image_time > 0:
            self._prometheus.record_multimodal_processing(
                "vision", image_time / 1000, True
            )
        audio_time = getattr(multimodal_metrics, "audio_processing_time_ms", 0)
        if audio_time > 0:
            self._prometheus.record_multimodal_processing(
                "audio", audio_time / 1000, True
            )

    def _push_to_prometheus(
        self, gpu_metrics, npu_metrics, multimodal_metrics, system_metrics
    ):
        """
        Push collected metrics to Prometheus for unified monitoring.

        Issue #469: Consolidates all monitoring to Prometheus/Grafana stack.
        Issue #620: Refactored with helper methods.
        """
        try:
            self._push_gpu_metrics_to_prometheus(gpu_metrics)
            self._push_npu_metrics_to_prometheus(npu_metrics)
            self._push_multimodal_metrics_to_prometheus(multimodal_metrics)
        except Exception as e:
            self.logger.debug("Error pushing metrics to Prometheus: %s", e)

    async def start_monitoring(self):
        """Start continuous performance monitoring."""
        if self.monitoring_active:
            self.logger.warning("Performance monitoring already active")
            return

        self.monitoring_active = True
        self.logger.info("Starting comprehensive performance monitoring...")

        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

        return self.monitoring_task

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.monitoring_active:
            try:
                metrics = await self.collect_all_metrics()
                await self._analyze_performance_and_generate_alerts(metrics)
                self._log_performance_summary(metrics)
                await asyncio.sleep(self.collection_interval)

            except Exception as e:
                self.logger.error("Error in monitoring loop: %s", e)
                await asyncio.sleep(self.collection_interval)

    async def _analyze_performance_and_generate_alerts(self, metrics: Dict[str, Any]):
        """Analyze metrics and generate performance alerts."""
        try:
            alerts = self._alert_analyzer.analyze_all(metrics)

            # Update performance_alerts buffer for backward compatibility (Issue #427)
            # Keep last 100 alerts to prevent unbounded memory growth
            if alerts:
                self.performance_alerts.extend(alerts)
                if len(self.performance_alerts) > 100:
                    self.performance_alerts = self.performance_alerts[-100:]

            # Store alerts in Redis
            if self.redis_client and alerts:
                try:

                    def _store_alerts():
                        key = "performance_alerts"
                        for alert in alerts:
                            self.redis_client.zadd(
                                key, {json.dumps(alert): time.time()}
                            )
                        self.redis_client.expire(key, 3600)

                    await asyncio.to_thread(_store_alerts)
                except Exception as e:
                    self.logger.debug("Could not store alerts in Redis: %s", e)

            # Issue #469: Push alerts to Prometheus for unified monitoring
            if alerts:
                for alert in alerts:
                    category = alert.get("category", "unknown")
                    severity = alert.get("severity", "info")
                    self._prometheus.record_performance_alert(category, severity)

            # Update active alert counts in Prometheus
            critical_count = sum(
                1 for a in self.performance_alerts if a.get("severity") == "critical"
            )
            warning_count = sum(
                1 for a in self.performance_alerts if a.get("severity") == "warning"
            )
            info_count = sum(
                1 for a in self.performance_alerts if a.get("severity") == "info"
            )
            self._prometheus.update_active_alerts("critical", critical_count)
            self._prometheus.update_active_alerts("warning", warning_count)
            self._prometheus.update_active_alerts("info", info_count)

            # Get callbacks under lock
            async with self._lock:
                callbacks = list(self.alert_callbacks)

            # Trigger alert callbacks outside lock
            for callback in callbacks:
                try:
                    await callback(alerts)
                except Exception as e:
                    self.logger.error("Error in alert callback: %s", e)

        except Exception as e:
            self.logger.error("Error analyzing performance: %s", e)

    def _log_performance_summary(self, metrics: Dict[str, Any]):
        """Log comprehensive performance summary."""
        try:
            summary_parts = []

            if metrics.get("gpu"):
                gpu = metrics["gpu"]
                summary_parts.append(
                    f"GPU: {gpu['utilization_percent']:.0f}% util, {gpu['temperature_celsius']}°C"
                )

            if metrics.get("npu"):
                npu = metrics["npu"]
                summary_parts.append(f"NPU: {npu['acceleration_ratio']:.1f}x speedup")

            if metrics.get("system"):
                system = metrics["system"]
                cpu_pct = system["cpu_usage_percent"]
                mem_pct = system["memory_usage_percent"]
                summary_parts.append(f"CPU: {cpu_pct:.0f}%, MEM: {mem_pct:.0f}%")
                summary_parts.append(f"Load: {system['cpu_load_1m']:.1f}")

            if metrics.get("services"):
                healthy_services = sum(
                    1 for s in metrics["services"] if s["status"] == "healthy"
                )
                total_services = len(metrics["services"])
                summary_parts.append(
                    f"Services: {healthy_services}/{total_services} healthy"
                )

            self.logger.info("PERFORMANCE: %s", " | ".join(summary_parts))

        except Exception as e:
            self.logger.error("Error logging performance summary: %s", e)

    async def stop_monitoring(self):
        """Stop performance monitoring."""
        if not self.monitoring_active:
            return

        self.monitoring_active = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                self.logger.debug("Monitoring task cancelled during shutdown")

        self.logger.info("Performance monitoring stopped")

    async def get_current_performance_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive performance dashboard data."""
        try:
            dashboard = {
                "timestamp": time.time(),
                "monitoring_active": self.monitoring_active,
                "hardware_acceleration": {
                    "gpu_available": self.gpu_available,
                    "npu_available": self.npu_available,
                },
                "performance_baselines": dict(self.performance_baselines),
                "recent_alerts": [],
                "note": "Use Prometheus PromQL for historical data.",
            }

            if self.redis_client:
                try:

                    def _fetch_dashboard_data():
                        gpu_data = self.redis_client.zrange(
                            "performance_metrics:gpu", -1, -1
                        )
                        npu_data = self.redis_client.zrange(
                            "performance_metrics:npu", -1, -1
                        )
                        system_data = self.redis_client.zrange(
                            "performance_metrics:system", -1, -1
                        )
                        alerts_data = self.redis_client.zrange(
                            "performance_alerts", -10, -1
                        )
                        return gpu_data, npu_data, system_data, alerts_data

                    (
                        gpu_data,
                        npu_data,
                        system_data,
                        alerts_data,
                    ) = await asyncio.to_thread(_fetch_dashboard_data)

                    if gpu_data:
                        dashboard["gpu"] = json.loads(gpu_data[0])
                    if npu_data:
                        dashboard["npu"] = json.loads(npu_data[0])
                    if system_data:
                        dashboard["system"] = json.loads(system_data[0])
                    dashboard["recent_alerts"] = [json.loads(a) for a in alerts_data]

                except Exception as e:
                    self.logger.debug(f"Could not fetch dashboard data from Redis: {e}")

            dashboard["trends"] = await self._calculate_performance_trends()

            return dashboard

        except Exception as e:
            self.logger.error("Error generating performance dashboard: %s", e)
            return {"error": str(e), "timestamp": time.time()}

    def _calculate_trend_direction(self, values: list) -> str:
        """
        Calculate trend direction from a list of values.

        (Issue #398: extracted helper)
        """
        if not values or len(values) < 2:
            return "stable"
        if values[-1] > values[0]:
            return "increasing"
        if values[-1] < values[0]:
            return "decreasing"
        return "stable"

    def _compute_metric_trend(
        self, values: list, metric_name: str, decimals: int = 1
    ) -> Dict[str, Any]:
        """
        Compute trend statistics for a metric.

        (Issue #398: extracted helper)
        """
        return {
            "average": round(sum(values) / len(values), decimals),
            "trend": self._calculate_trend_direction(values),
        }

    async def _calculate_performance_trends(self) -> Dict[str, Any]:
        """
        Calculate performance trends from recent metrics.

        (Issue #398: refactored to use extracted helpers)
        """
        try:
            trends = {}

            if not self.redis_client:
                return {
                    "note": "Trends require Redis. Use Prometheus PromQL for historical analysis."
                }

            try:

                def _fetch_trend_data():
                    gpu_data = self.redis_client.zrange(
                        "performance_metrics:gpu", -5, -1
                    )
                    system_data = self.redis_client.zrange(
                        "performance_metrics:system", -5, -1
                    )
                    return gpu_data, system_data

                gpu_data, system_data = await asyncio.to_thread(_fetch_trend_data)

                if gpu_data and len(gpu_data) >= 2:
                    gpu_metrics = [json.loads(d) for d in gpu_data]
                    utilizations = [
                        g.get("utilization_percent", 0) for g in gpu_metrics
                    ]
                    trends["gpu_utilization"] = self._compute_metric_trend(
                        utilizations, "gpu"
                    )

                if system_data and len(system_data) >= 2:
                    system_metrics = [json.loads(d) for d in system_data]

                    loads = [s.get("cpu_load_1m", 0) for s in system_metrics]
                    trends["cpu_load"] = self._compute_metric_trend(
                        loads, "cpu", decimals=2
                    )

                    memory_usage = [
                        s.get("memory_usage_percent", 0) for s in system_metrics
                    ]
                    trends["memory_usage"] = self._compute_metric_trend(
                        memory_usage, "memory"
                    )

            except Exception as e:
                self.logger.debug("Could not calculate trends from Redis: %s", e)

            return trends

        except Exception as e:
            self.logger.error("Error calculating performance trends: %s", e)
            return {}

    async def add_alert_callback(self, callback: Callable):
        """Add callback function for performance alerts (thread-safe)."""
        async with self._lock:
            self.alert_callbacks.append(callback)

    def _fetch_recommendation_data(self):
        """Fetch metrics data from Redis for recommendations."""
        gpu_data = self.redis_client.zrange("performance_metrics:gpu", -1, -1)
        npu_data = (
            self.redis_client.zrange("performance_metrics:npu", -1, -1)
            if self.npu_available
            else []
        )
        system_data = self.redis_client.zrange("performance_metrics:system", -1, -1)
        return gpu_data, npu_data, system_data

    async def get_performance_optimization_recommendations(
        self,
    ) -> List[Dict[str, Any]]:
        """Generate performance optimization recommendations."""
        try:
            latest_gpu, latest_npu, latest_system = None, None, None

            if self.redis_client:
                try:
                    gpu_data, npu_data, system_data = await asyncio.to_thread(
                        self._fetch_recommendation_data
                    )

                    class MetricObj:
                        def __init__(self, d):
                            self.__dict__.update(d)

                    if gpu_data:
                        latest_gpu = MetricObj(json.loads(gpu_data[0]))
                    if npu_data:
                        latest_npu = MetricObj(json.loads(npu_data[0]))
                    if system_data:
                        latest_system = MetricObj(json.loads(system_data[0]))

                except Exception as e:
                    self.logger.debug(
                        f"Could not fetch metrics for recommendations: {e}"
                    )

            return self._recommendation_generator.generate_all(
                latest_gpu, latest_npu, latest_system
            )

        except Exception as e:
            self.logger.error("Error generating optimization recommendations: %s", e)
            return []
