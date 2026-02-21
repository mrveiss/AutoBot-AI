#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Performance Metrics Collection and Alerting
==================================================

Real-time performance monitoring with metrics collection, analysis, and alerting.

Features:
- System metrics (CPU, memory, disk, network)
- Service-specific metrics (response times, error rates, throughput)
- Custom metrics API for application instrumentation
- Time-series data storage with automatic aggregation
- Alert thresholds and notification system
- Prometheus-compatible export format
- Grafana dashboard templates
- Performance baselines and anomaly detection

Usage:
    python scripts/metrics_collector.py --collect --interval 30
    python scripts/metrics_collector.py --export --format prometheus
    python scripts/metrics_collector.py --analyze --last-hours 24
    python scripts/metrics_collector.py --setup-alerts --config alerts.yml
"""

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.script_utils import ScriptFormatter
from utils.service_registry import get_service_registry


@dataclass
class Metric:
    """Single metric data point."""

    name: str
    value: float
    timestamp: float
    labels: Dict[str, str]
    unit: str = ""

    def to_prometheus(self) -> str:
        """Convert to Prometheus format."""
        label_str = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
        return f"{self.name}{{{label_str}}} {self.value} {int(self.timestamp * 1000)}"


@dataclass
class Alert:
    """Alert configuration."""

    name: str
    metric: str
    condition: str  # "above", "below", "outside_range"
    threshold: float
    threshold_high: Optional[float] = None  # For outside_range
    duration: int = 60  # Seconds condition must persist
    severity: str = "warning"  # warning, critical
    action: str = "log"  # log, webhook, email

    def check(self, value: float, duration_met: bool) -> bool:
        """Check if alert condition is met."""
        if not duration_met:
            return False

        if self.condition == "above":
            return value > self.threshold
        elif self.condition == "below":
            return value < self.threshold
        elif self.condition == "outside_range":
            return value < self.threshold or value > self.threshold_high
        return False


class MetricsCollector:
    """Collects and manages performance metrics."""

    def __init__(self, storage_dir: str = "data/metrics", retention_days: int = 30):
        """Initialize metrics collector with storage path and retention settings."""
        self.project_root = Path(__file__).parent.parent
        self.storage_dir = self.project_root / storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.service_registry = get_service_registry()
        self.retention_days = retention_days

        # In-memory metrics storage (last 1 hour)
        self.metrics_buffer: Dict[str, deque] = defaultdict(lambda: deque(maxlen=3600))

        # Alert configurations
        self.alerts: List[Alert] = []
        self.alert_states: Dict[str, Dict[str, Any]] = {}

        # Default system metrics to collect
        self.system_metrics = [
            "cpu_usage_percent",
            "memory_usage_percent",
            "disk_usage_percent",
            "network_bytes_sent",
            "network_bytes_recv",
            "open_files",
            "thread_count",
        ]

        # Locks for thread-safe file access
        self._alerts_file_lock = threading.Lock()
        self._metrics_file_lock = threading.Lock()

        logger.info("📊 AutoBot Metrics Collector initialized")
        logger.info(f"   Storage Directory: {self.storage_dir}")
        logger.info(f"   Retention: {retention_days} days")

    def print_header(self, title: str):
        """Print formatted header."""
        ScriptFormatter.print_header(title)

    def print_step(self, step: str, status: str = "info"):
        """Print step with status."""
        ScriptFormatter.print_step(step, status)

    def _collect_cpu_and_memory_metrics(self, timestamp: float) -> List[Metric]:
        """Collect CPU and memory metrics.

        Helper for collect_system_metrics (#825).
        """
        host = os.uname().nodename
        metrics = []

        cpu_percent = psutil.cpu_percent(interval=1)
        metrics.append(
            Metric(
                name="system_cpu_usage",
                value=cpu_percent,
                timestamp=timestamp,
                labels={"host": host},
                unit="percent",
            )
        )

        memory = psutil.virtual_memory()
        metrics.append(
            Metric(
                name="system_memory_usage",
                value=memory.percent,
                timestamp=timestamp,
                labels={"host": host},
                unit="percent",
            )
        )
        metrics.append(
            Metric(
                name="system_memory_available",
                value=memory.available / (1024 * 1024 * 1024),
                timestamp=timestamp,
                labels={"host": host},
                unit="gigabytes",
            )
        )
        return metrics

    def _collect_disk_and_network_metrics(self, timestamp: float) -> List[Metric]:
        """Collect disk and network I/O metrics.

        Helper for collect_system_metrics (#825).
        """
        host = os.uname().nodename
        metrics = []

        disk = psutil.disk_usage("/")
        metrics.append(
            Metric(
                name="system_disk_usage",
                value=disk.percent,
                timestamp=timestamp,
                labels={"host": host, "mount": "/"},
                unit="percent",
            )
        )

        net_io = psutil.net_io_counters()
        metrics.append(
            Metric(
                name="system_network_bytes_sent",
                value=net_io.bytes_sent,
                timestamp=timestamp,
                labels={"host": host},
                unit="bytes",
            )
        )
        metrics.append(
            Metric(
                name="system_network_bytes_recv",
                value=net_io.bytes_recv,
                timestamp=timestamp,
                labels={"host": host},
                unit="bytes",
            )
        )
        return metrics

    def _collect_process_metrics(self, timestamp: float) -> List[Metric]:
        """Collect process-level thread and file metrics.

        Helper for collect_system_metrics (#825).
        """
        metrics = []
        process = psutil.Process()
        metrics.append(
            Metric(
                name="process_thread_count",
                value=process.num_threads(),
                timestamp=timestamp,
                labels={"process": "autobot"},
                unit="threads",
            )
        )
        metrics.append(
            Metric(
                name="process_open_files",
                value=len(process.open_files()),
                timestamp=timestamp,
                labels={"process": "autobot"},
                unit="files",
            )
        )
        return metrics

    async def collect_system_metrics(self) -> List[Metric]:
        """Collect system-level metrics."""
        timestamp = time.time()
        metrics = self._collect_cpu_and_memory_metrics(timestamp)
        metrics.extend(self._collect_disk_and_network_metrics(timestamp))
        metrics.extend(self._collect_process_metrics(timestamp))
        return metrics

    async def collect_service_metrics(self) -> List[Metric]:
        """Collect service-specific metrics."""
        metrics = []
        timestamp = time.time()

        # Check health of all services and measure response times
        health_results = await self.service_registry.check_all_services_health()

        for service_name, health in health_results.items():
            # Service availability
            is_healthy = 1.0 if health.status.value == "healthy" else 0.0
            metrics.append(
                Metric(
                    name="service_availability",
                    value=is_healthy,
                    timestamp=timestamp,
                    labels={"service": service_name},
                    unit="boolean",
                )
            )

            # Response time
            if hasattr(health, "response_time") and health.response_time > 0:
                metrics.append(
                    Metric(
                        name="service_response_time",
                        value=health.response_time,
                        timestamp=timestamp,
                        labels={"service": service_name},
                        unit="seconds",
                    )
                )

        # Collect Redis metrics if available
        try:
            redis_metrics = await self._collect_redis_metrics()
            metrics.extend(redis_metrics)
        except Exception as e:
            self.print_step(f"Failed to collect Redis metrics: {e}", "warning")

        return metrics

    async def _collect_redis_metrics(self) -> List[Metric]:
        """Collect Redis-specific metrics."""
        metrics = []
        timestamp = time.time()

        try:
            import redis

            redis_url = self.service_registry.get_service_url("redis")
            r = redis.from_url(redis_url)

            # Get Redis info
            info = r.info()

            # Memory metrics
            metrics.append(
                Metric(
                    name="redis_memory_used",
                    value=info.get("used_memory", 0) / (1024 * 1024),  # MB
                    timestamp=timestamp,
                    labels={"service": "redis"},
                    unit="megabytes",
                )
            )

            # Connection metrics
            metrics.append(
                Metric(
                    name="redis_connected_clients",
                    value=info.get("connected_clients", 0),
                    timestamp=timestamp,
                    labels={"service": "redis"},
                    unit="connections",
                )
            )

            # Command stats
            metrics.append(
                Metric(
                    name="redis_total_commands",
                    value=info.get("total_commands_processed", 0),
                    timestamp=timestamp,
                    labels={"service": "redis"},
                    unit="commands",
                )
            )

        except Exception:
            logger.debug("Suppressed exception in try block", exc_info=True)

        return metrics

    async def collect_custom_metric(
        self, name: str, value: float, labels: Dict[str, str] = None, unit: str = ""
    ) -> None:
        """Record a custom metric."""
        metric = Metric(
            name=name,
            value=value,
            timestamp=time.time(),
            labels=labels or {},
            unit=unit,
        )

        # Store in buffer
        key = f"{name}:{json.dumps(labels or {}, sort_keys=True)}"
        self.metrics_buffer[key].append(metric)

        # Check alerts
        await self._check_alerts(metric)

    async def start_collection(self, interval: int = 30) -> None:
        """Start continuous metrics collection."""
        self.print_header("Starting Metrics Collection")
        logger.info(f"Collection interval: {interval} seconds")

        while True:
            try:
                # Collect all metrics
                system_metrics = await self.collect_system_metrics()
                service_metrics = await self.collect_service_metrics()

                all_metrics = system_metrics + service_metrics

                # Store metrics
                for metric in all_metrics:
                    key = f"{metric.name}:{json.dumps(metric.labels, sort_keys=True)}"
                    self.metrics_buffer[key].append(metric)

                # Check alerts
                for metric in all_metrics:
                    await self._check_alerts(metric)

                # Save to disk periodically (every 5 minutes)
                if int(time.time()) % 300 < interval:
                    await self._save_metrics_to_disk()

                self.print_step(f"Collected {len(all_metrics)} metrics", "metric")

                await asyncio.sleep(interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                self.print_step(f"Collection error: {e}", "error")
                await asyncio.sleep(interval)

    async def _save_metrics_to_disk(self) -> None:
        """Save metrics buffer to disk."""
        timestamp = datetime.now()

        # Group metrics by hour
        hour_str = timestamp.strftime("%Y%m%d_%H")
        output_file = self.storage_dir / f"metrics_{hour_str}.json"

        # Convert buffer to list
        metrics_data = []
        for key, metrics_deque in self.metrics_buffer.items():
            for metric in metrics_deque:
                metrics_data.append(asdict(metric))

        # Thread-safe file access
        with self._metrics_file_lock:
            # Append to existing file or create new
            existing_data = []
            if output_file.exists():
                try:
                    with open(output_file, "r") as f:
                        existing_data = json.load(f)
                except Exception:
                    existing_data = []

            # Combine and save
            all_data = existing_data + metrics_data
            with open(output_file, "w") as f:
                json.dump(all_data, f)

        # Clean old files
        self._cleanup_old_metrics()

    def _cleanup_old_metrics(self) -> None:
        """Remove metrics older than retention period."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)

        for file_path in self.storage_dir.glob("metrics_*.json"):
            try:
                # Extract date from filename
                file_date_str = file_path.stem.replace("metrics_", "")[:8]
                file_date = datetime.strptime(file_date_str, "%Y%m%d")

                if file_date < cutoff_date:
                    file_path.unlink()
            except Exception:
                logger.debug("Suppressed exception in try block", exc_info=True)

    def load_alerts(self, config_file: str) -> None:
        """Load alert configurations from file."""
        try:
            with open(config_file, "r") as f:
                alert_config = yaml.safe_load(f)

            self.alerts = []
            for alert_data in alert_config.get("alerts", []):
                alert = Alert(**alert_data)
                self.alerts.append(alert)

            self.print_step(
                f"Loaded {len(self.alerts)} alert configurations", "success"
            )

        except Exception as e:
            self.print_step(f"Failed to load alerts: {e}", "error")

    async def _check_alerts(self, metric: Metric) -> None:
        """Check if metric triggers any alerts."""
        for alert in self.alerts:
            # Check if this alert applies to this metric
            if not metric.name.startswith(alert.metric):
                continue

            # Get or create alert state
            alert_key = f"{alert.name}:{metric.name}"
            if alert_key not in self.alert_states:
                self.alert_states[alert_key] = {
                    "triggered": False,
                    "first_seen": None,
                    "last_value": None,
                }

            state = self.alert_states[alert_key]

            # Check condition
            condition_met = False
            if alert.condition == "above" and metric.value > alert.threshold:
                condition_met = True
            elif alert.condition == "below" and metric.value < alert.threshold:
                condition_met = True
            elif alert.condition == "outside_range":
                if (
                    metric.value < alert.threshold
                    or metric.value > alert.threshold_high
                ):
                    condition_met = True

            # Update state
            if condition_met:
                if state["first_seen"] is None:
                    state["first_seen"] = time.time()

                # Check duration
                duration_met = (time.time() - state["first_seen"]) >= alert.duration

                if duration_met and not state["triggered"]:
                    # Trigger alert
                    state["triggered"] = True
                    await self._trigger_alert(alert, metric)
            else:
                # Reset state
                state["first_seen"] = None
                state["triggered"] = False

            state["last_value"] = metric.value

    async def _trigger_alert(self, alert: Alert, metric: Metric) -> None:
        """Trigger an alert action."""
        alert_data = {
            "timestamp": datetime.now().isoformat(),
            "alert_name": alert.name,
            "metric_name": metric.name,
            "metric_value": metric.value,
            "threshold": alert.threshold,
            "severity": alert.severity,
            "labels": metric.labels,
        }

        self.print_step(
            f"🚨 ALERT: {alert.name} - {metric.name}={metric.value} {alert.condition} {alert.threshold}",
            "error" if alert.severity == "critical" else "warning",
        )

        # Log alert (thread-safe)
        alert_file = self.storage_dir / "alerts.json"

        with self._alerts_file_lock:
            alerts = []
            if alert_file.exists():
                try:
                    with open(alert_file, "r") as f:
                        alerts = json.load(f)
                except Exception:
                    alerts = []

            alerts.append(alert_data)

            # Keep last 1000 alerts
            if len(alerts) > 1000:
                alerts = alerts[-1000:]

            with open(alert_file, "w") as f:
                json.dump(alerts, f, indent=2)

        # Execute action
        if alert.action == "webhook":
            # Send webhook notification
            pass
        elif alert.action == "email":
            # Send email notification
            pass

    def _export_prometheus(self, metrics: List[Metric]) -> str:
        """Export metrics in Prometheus text format.

        Helper for export_metrics (#825).
        """
        output_lines = []
        by_name = defaultdict(list)
        for metric in metrics:
            by_name[metric.name].append(metric)

        for name, metric_list in by_name.items():
            output_lines.append(f"# HELP {name} {name.replace('_', ' ').title()}")
            output_lines.append(f"# TYPE {name} gauge")
            for metric in metric_list:
                output_lines.append(metric.to_prometheus())
            output_lines.append("")

        return "\n".join(output_lines)

    def _export_csv(self, metrics: List[Metric]) -> str:
        """Export metrics in CSV format.

        Helper for export_metrics (#825).
        """
        import csv
        import io

        output = io.StringIO()
        if metrics:
            fieldnames = ["timestamp", "name", "value", "unit", "labels"]
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for metric in metrics:
                writer.writerow(
                    {
                        "timestamp": datetime.fromtimestamp(
                            metric.timestamp
                        ).isoformat(),
                        "name": metric.name,
                        "value": metric.value,
                        "unit": metric.unit,
                        "labels": json.dumps(metric.labels),
                    }
                )
        return output.getvalue()

    def export_metrics(
        self, format_type: str = "prometheus", last_hours: int = 1
    ) -> str:
        """Export metrics in specified format."""
        self.print_header(f"Exporting Metrics ({format_type})")

        cutoff_time = time.time() - (last_hours * 3600)
        metrics = []
        for key, metrics_deque in self.metrics_buffer.items():
            for metric in metrics_deque:
                if metric.timestamp >= cutoff_time:
                    metrics.append(metric)

        if format_type == "prometheus":
            return self._export_prometheus(metrics)
        elif format_type == "json":
            metrics_data = [asdict(m) for m in metrics]
            return json.dumps(
                {
                    "metrics": metrics_data,
                    "exported_at": datetime.now().isoformat(),
                    "total_metrics": len(metrics_data),
                },
                indent=2,
            )
        else:
            return self._export_csv(metrics)

    def _load_disk_metrics(
        self, metric_name: str, cutoff_time: float, last_hours: int
    ) -> List[Metric]:
        """Load historical metrics from disk files.

        Helper for analyze_metrics (#825).
        """
        disk_metrics = []
        for hours_ago in range(1, last_hours + 1):
            timestamp = datetime.now() - timedelta(hours=hours_ago)
            hour_file = (
                self.storage_dir / f"metrics_{timestamp.strftime('%Y%m%d_%H')}.json"
            )
            if not hour_file.exists():
                continue
            try:
                with open(hour_file, "r") as f:
                    data = json.load(f)
                for metric_data in data:
                    if metric_data["timestamp"] >= cutoff_time:
                        if not metric_name or metric_data["name"] == metric_name:
                            disk_metrics.append(Metric(**metric_data))
            except Exception:
                logger.debug("Suppressed exception in try block", exc_info=True)
        return disk_metrics

    def _compute_metric_stats(self, values: List[float]) -> Dict[str, Any]:
        """Compute statistical summary for a list of metric values.

        Helper for analyze_metrics (#825).
        """
        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "min": min(values),
            "max": max(values),
            "std_dev": (statistics.stdev(values) if len(values) > 1 else 0),
            "percentiles": {
                "p50": statistics.median(values),
                "p95": self._percentile(values, 0.95),
                "p99": self._percentile(values, 0.99),
            },
        }

    def analyze_metrics(
        self, metric_name: str = None, last_hours: int = 24
    ) -> Dict[str, Any]:
        """Analyze metrics and generate statistics."""
        self.print_header("Analyzing Metrics")
        cutoff_time = time.time() - (last_hours * 3600)

        all_metrics = []
        for key, metrics_deque in self.metrics_buffer.items():
            for metric in metrics_deque:
                if metric.timestamp >= cutoff_time:
                    if not metric_name or metric.name == metric_name:
                        all_metrics.append(metric)

        all_metrics.extend(
            self._load_disk_metrics(metric_name, cutoff_time, last_hours)
        )

        by_metric = defaultdict(list)
        for metric in all_metrics:
            by_metric[metric.name].append(metric.value)

        analysis = {
            "period": {
                "start": datetime.fromtimestamp(cutoff_time).isoformat(),
                "end": datetime.now().isoformat(),
                "hours": last_hours,
            },
            "total_data_points": len(all_metrics),
            "metrics": {},
        }

        for name, values in by_metric.items():
            if values:
                analysis["metrics"][name] = self._compute_metric_stats(values)

        return analysis

    def _percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile of values."""
        if not values:
            return 0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile)
        return sorted_values[min(index, len(sorted_values) - 1)]

    def create_grafana_dashboard(self) -> Dict[str, Any]:
        """Create Grafana dashboard configuration."""
        dashboard = {
            "dashboard": {
                "title": "AutoBot Performance Metrics",
                "panels": [
                    {
                        "title": "System CPU Usage",
                        "targets": [{"expr": "system_cpu_usage"}],
                        "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
                    },
                    {
                        "title": "System Memory Usage",
                        "targets": [{"expr": "system_memory_usage"}],
                        "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8},
                    },
                    {
                        "title": "Service Response Times",
                        "targets": [{"expr": "service_response_time"}],
                        "gridPos": {"x": 0, "y": 8, "w": 24, "h": 8},
                    },
                    {
                        "title": "Service Availability",
                        "targets": [{"expr": "service_availability"}],
                        "gridPos": {"x": 0, "y": 16, "w": 24, "h": 8},
                    },
                ],
                "refresh": "30s",
                "time": {"from": "now-1h", "to": "now"},
            }
        }

        return dashboard


async def _handle_collect_command(collector, args) -> int:
    """Handle --collect command (Issue #315: extracted helper)."""
    await collector.start_collection(args.interval)
    return 0


async def _handle_export_command(collector, args) -> int:
    """Handle --export command (Issue #315: extracted helper)."""
    output = collector.export_metrics(args.format, args.last_hours)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        logger.info(f"✅ Metrics exported to: {args.output}")
    else:
        logger.info(output)
    return 0


async def _handle_analyze_command(collector, args) -> int:
    """Handle --analyze command (Issue #315: extracted helper)."""
    analysis = collector.analyze_metrics(args.metric, args.last_hours)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(analysis, f, indent=2)
        logger.info(f"✅ Analysis saved to: {args.output}")
        return 0

    logger.info("\n📊 Metrics Analysis:")
    logger.info(f"   Period: {analysis['period']['hours']} hours")
    logger.info(f"   Total data points: {analysis['total_data_points']}")

    for metric_name, stats in analysis["metrics"].items():
        logger.info(f"\n   {metric_name}:")
        logger.info(f"     Mean: {stats['mean']:.2f}")
        logger.info(f"     Min/Max: {stats['min']:.2f} / {stats['max']:.2f}")
        logger.info(f"     P95: {stats['percentiles']['p95']:.2f}")
    return 0


async def _handle_setup_alerts_command(collector, args) -> int:
    """Handle --setup-alerts command (Issue #315: extracted helper)."""
    if args.config:
        collector.load_alerts(args.config)
        return 0

    # Create sample alert config
    sample_config = {
        "alerts": [
            {
                "name": "high_cpu_usage",
                "metric": "system_cpu_usage",
                "condition": "above",
                "threshold": 80.0,
                "duration": 300,
                "severity": "warning",
            },
            {
                "name": "low_memory",
                "metric": "system_memory_available",
                "condition": "below",
                "threshold": 1.0,
                "duration": 180,
                "severity": "critical",
            },
            {
                "name": "service_down",
                "metric": "service_availability",
                "condition": "below",
                "threshold": 1.0,
                "duration": 60,
                "severity": "critical",
            },
        ]
    }

    config_file = "config/alerts.yml"
    Path(config_file).parent.mkdir(exist_ok=True)

    with open(config_file, "w") as f:
        yaml.dump(sample_config, f)

    logger.info(f"✅ Sample alert configuration created: {config_file}")
    return 0


async def _handle_dashboard_command(collector, args) -> int:
    """Handle --dashboard command (Issue #315: extracted helper)."""
    dashboard = collector.create_grafana_dashboard()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(dashboard, f, indent=2)
        logger.info(f"✅ Grafana dashboard saved to: {args.output}")
    else:
        logger.info(json.dumps(dashboard, indent=2))
    return 0


def _build_metrics_argparser() -> argparse.ArgumentParser:
    """Build the argument parser for the metrics CLI.

    Helper for main (#825).
    """
    parser = argparse.ArgumentParser(
        description="AutoBot Performance Metrics Collection and Alerting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/metrics_collector.py --collect --interval 30
  python scripts/metrics_collector.py --export --format prometheus
  python scripts/metrics_collector.py --analyze --metric system_cpu_usage
  python scripts/metrics_collector.py --setup-alerts --config alerts.yml
  python scripts/metrics_collector.py --dashboard --output grafana_dashboard.json
        """,
    )
    parser.add_argument(
        "--collect", action="store_true", help="Start metrics collection"
    )
    parser.add_argument("--export", action="store_true", help="Export metrics")
    parser.add_argument("--analyze", action="store_true", help="Analyze metrics")
    parser.add_argument("--setup-alerts", action="store_true", help="Setup alert rules")
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Generate Grafana dashboard",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Collection interval (seconds)",
    )
    parser.add_argument(
        "--format",
        choices=["prometheus", "json", "csv"],
        default="prometheus",
        help="Export format",
    )
    parser.add_argument("--metric", help="Specific metric to analyze")
    parser.add_argument("--last-hours", type=int, default=1, help="Hours to look back")
    parser.add_argument("--config", help="Alert configuration file")
    parser.add_argument("--output", help="Output file")
    parser.add_argument(
        "--storage-dir",
        default="data/metrics",
        help="Metrics storage directory",
    )
    return parser


async def main():
    """Entry point for metrics collection and analysis CLI."""
    parser = _build_metrics_argparser()
    args = parser.parse_args()

    if not any(
        [
            args.collect,
            args.export,
            args.analyze,
            args.setup_alerts,
            args.dashboard,
        ]
    ):
        parser.print_help()
        return 1

    collector = MetricsCollector(args.storage_dir)

    command_handlers = {
        "collect": (_handle_collect_command, args.collect),
        "export": (_handle_export_command, args.export),
        "analyze": (_handle_analyze_command, args.analyze),
        "setup_alerts": (_handle_setup_alerts_command, args.setup_alerts),
        "dashboard": (_handle_dashboard_command, args.dashboard),
    }

    try:
        for cmd_name, (handler, is_active) in command_handlers.items():
            if is_active:
                return await handler(collector, args)
        return 0
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Operation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
