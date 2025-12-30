# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Resource Monitor for AutoBot
Monitors system performance during workflow execution
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List

import psutil


logger = logging.getLogger(__name__)


class SystemResourceMonitor:
    """Monitors system resource usage during workflow execution"""

    def __init__(self, collection_interval: float = 5.0):
        """Initialize system resource monitor with collection interval and history storage."""
        self.collection_interval = collection_interval
        self.monitoring_active = False
        self.resource_history: List[Dict[str, Any]] = []
        self.max_history = 1000

    async def start_monitoring(self):
        """Start continuous system monitoring"""
        if self.monitoring_active:
            logger.warning("System monitoring already active")
            return

        self.monitoring_active = True
        logger.info("Started system resource monitoring")

        # Run monitoring loop
        asyncio.create_task(self._monitoring_loop())

    async def stop_monitoring(self):
        """Stop system monitoring"""
        self.monitoring_active = False
        logger.info("Stopped system resource monitoring")

    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                resource_data = await self.collect_system_metrics()
                self._store_resource_data(resource_data)
                await asyncio.sleep(self.collection_interval)
            except Exception as e:
                logger.error("System monitoring error: %s", e)
                await asyncio.sleep(self.collection_interval)

    def _collect_autobot_processes(self) -> List[Dict[str, Any]]:
        """
        Collect metrics for AutoBot-related processes.

        Issue #281: Extracted from collect_system_metrics to reduce function length.
        """
        autobot_processes = []
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "memory_info"]
        ):
            try:
                if "python" in proc.info[
                    "name"
                ].lower() or "autobot" in proc.info.get("cmdline", []):
                    autobot_processes.append(
                        {
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "cpu_percent": proc.info["cpu_percent"],
                            "memory_percent": proc.info["memory_percent"],
                            "memory_mb": (
                                proc.info["memory_info"].rss / 1024 / 1024
                                if proc.info["memory_info"]
                                else 0
                            ),
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return autobot_processes

    def _build_metrics_dict(
        self, cpu_percent, cpu_count, cpu_freq, memory, swap,
        disk_usage, disk_io, network_io, autobot_processes
    ) -> Dict[str, Any]:
        """
        Build the metrics dictionary from collected data.

        Issue #281: Extracted from collect_system_metrics to reduce function length.
        """
        return {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count,
                "frequency_mhz": cpu_freq.current if cpu_freq else None,
            },
            "memory": {
                "total_mb": memory.total / 1024 / 1024,
                "available_mb": memory.available / 1024 / 1024,
                "used_mb": memory.used / 1024 / 1024,
                "percent": memory.percent,
            },
            "swap": {
                "total_mb": swap.total / 1024 / 1024,
                "used_mb": swap.used / 1024 / 1024,
                "percent": swap.percent,
            },
            "disk": {
                "total_gb": disk_usage.total / 1024 / 1024 / 1024,
                "used_gb": disk_usage.used / 1024 / 1024 / 1024,
                "free_gb": disk_usage.free / 1024 / 1024 / 1024,
                "percent": (disk_usage.used / disk_usage.total) * 100,
                "io": {
                    "read_mb": disk_io.read_bytes / 1024 / 1024 if disk_io else 0,
                    "write_mb": disk_io.write_bytes / 1024 / 1024 if disk_io else 0,
                },
            },
            "network": {
                "bytes_sent_mb": (
                    network_io.bytes_sent / 1024 / 1024 if network_io else 0
                ),
                "bytes_recv_mb": (
                    network_io.bytes_recv / 1024 / 1024 if network_io else 0
                ),
                "packets_sent": network_io.packets_sent if network_io else 0,
                "packets_recv": network_io.packets_recv if network_io else 0,
            },
            "autobot_processes": autobot_processes,
            "total_autobot_memory_mb": sum(
                p["memory_mb"] for p in autobot_processes
            ),
            "total_autobot_cpu_percent": sum(
                p["cpu_percent"] for p in autobot_processes if p["cpu_percent"]
            ),
        }

    async def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect current system resource metrics."""
        try:
            # Collect raw metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            disk_usage = psutil.disk_usage("/")
            disk_io = psutil.disk_io_counters()
            network_io = psutil.net_io_counters()

            # Collect AutoBot process metrics
            autobot_processes = self._collect_autobot_processes()

            # Build and return metrics dict
            return self._build_metrics_dict(
                cpu_percent, cpu_count, cpu_freq, memory, swap,
                disk_usage, disk_io, network_io, autobot_processes
            )

        except Exception as e:
            logger.error("Failed to collect system metrics: %s", e)
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "cpu": {"percent": 0},
                "memory": {"percent": 0, "used_mb": 0},
                "disk": {"percent": 0},
                "network": {"bytes_sent_mb": 0, "bytes_recv_mb": 0},
            }

    def _store_resource_data(self, resource_data: Dict[str, Any]):
        """Store resource data in history"""
        self.resource_history.append(resource_data)

        # Limit history size
        if len(self.resource_history) > self.max_history:
            self.resource_history.pop(0)

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics synchronously"""
        try:
            return {
                "cpu_percent": psutil.cpu_percent(),
                "memory_mb": psutil.virtual_memory().used / 1024 / 1024,
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": (
                    psutil.disk_usage("/").used / psutil.disk_usage("/").total * 100
                ),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error("Failed to get current metrics: %s", e)
            return {"error": str(e)}

    def _filter_recent_data(self, minutes: int) -> List[Dict[str, Any]]:
        """
        Filter resource history to get data from last N minutes (Issue #665: extracted helper).

        Args:
            minutes: Number of minutes to look back

        Returns:
            List of recent data points within the time window
        """
        cutoff_time = datetime.now().timestamp() - (minutes * 60)
        recent_data = []

        for data in reversed(self.resource_history):
            try:
                data_time = datetime.fromisoformat(data["timestamp"]).timestamp()
                if data_time >= cutoff_time:
                    recent_data.append(data)
                else:
                    break
            except (ValueError, KeyError):
                continue

        return recent_data

    def _calculate_resource_stats(self, values: List[float]) -> Dict[str, float]:
        """
        Calculate min/max/avg statistics for a list of values (Issue #665: extracted helper).

        Args:
            values: List of numeric values

        Returns:
            Dict with avg_percent, max_percent, min_percent
        """
        if not values:
            return {"avg_percent": 0, "max_percent": 0, "min_percent": 0}
        return {
            "avg_percent": sum(values) / len(values),
            "max_percent": max(values),
            "min_percent": min(values),
        }

    def get_resource_summary(self, minutes: int = 10) -> Dict[str, Any]:
        """
        Get resource usage summary for the last N minutes.

        Issue #665: Refactored to use extracted helper methods for
        data filtering and statistics calculation.
        """
        try:
            if not self.resource_history:
                return {"message": "No resource history available"}

            # Filter recent data (Issue #665: uses helper)
            recent_data = self._filter_recent_data(minutes)

            if not recent_data:
                return {"message": f"No data available for last {minutes} minutes"}

            # Extract value arrays
            cpu_values = [
                d["cpu"]["percent"]
                for d in recent_data
                if "cpu" in d and "percent" in d["cpu"]
            ]
            memory_values = [
                d["memory"]["percent"]
                for d in recent_data
                if "memory" in d and "percent" in d["memory"]
            ]
            disk_values = [
                d["disk"]["percent"]
                for d in recent_data
                if "disk" in d and "percent" in d["disk"]
            ]
            autobot_memory = [d.get("total_autobot_memory_mb", 0) for d in recent_data]
            autobot_cpu = [d.get("total_autobot_cpu_percent", 0) for d in recent_data]

            # Build summary using helper (Issue #665: uses helper)
            return {
                "time_window_minutes": minutes,
                "data_points": len(recent_data),
                "system": {
                    "cpu": self._calculate_resource_stats(cpu_values),
                    "memory": self._calculate_resource_stats(memory_values),
                    "disk": self._calculate_resource_stats(disk_values),
                },
                "autobot": {
                    "memory": {
                        "avg_mb": (
                            sum(autobot_memory) / len(autobot_memory)
                            if autobot_memory
                            else 0
                        ),
                        "max_mb": max(autobot_memory) if autobot_memory else 0,
                    },
                    "cpu": {
                        "avg_percent": (
                            sum(autobot_cpu) / len(autobot_cpu) if autobot_cpu else 0
                        ),
                        "max_percent": max(autobot_cpu) if autobot_cpu else 0,
                    },
                },
            }

        except Exception as e:
            logger.error("Failed to generate resource summary: %s", e)
            return {"error": str(e)}

    def check_resource_thresholds(self) -> Dict[str, Any]:
        """Check if system resources are within acceptable thresholds"""
        try:
            current = self.get_current_metrics()

            # Define thresholds
            thresholds = {"cpu_percent": 80, "memory_percent": 85, "disk_percent": 90}

            warnings = []
            critical = []

            # Check each threshold
            for metric, threshold in thresholds.items():
                if metric in current:
                    value = current[metric]
                    if value > threshold:
                        critical.append(
                            f"{metric}: {value:.1f}% (threshold: {threshold}%)"
                        )
                    elif value > threshold * 0.8:  # 80% of threshold as warning
                        warnings.append(
                            f"{metric}: {value:.1f}% "
                            f"(approaching threshold: {threshold}%)"
                        )

            return {
                "status": "critical" if critical else ("warning" if warnings else "ok"),
                "critical_alerts": critical,
                "warnings": warnings,
                "current_metrics": current,
                "check_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Failed to check resource thresholds: %s", e)
            return {"status": "error", "error": str(e)}

    def export_resource_data(self, format: str = "json") -> str:
        """Export resource monitoring data"""
        try:
            if format.lower() == "json":
                export_data = {
                    "monitoring_active": self.monitoring_active,
                    "collection_interval": self.collection_interval,
                    "history_length": len(self.resource_history),
                    "latest_metrics": (
                        self.resource_history[-1] if self.resource_history else None
                    ),
                    "summary": self.get_resource_summary(),
                    "thresholds_check": self.check_resource_thresholds(),
                    "export_timestamp": datetime.now().isoformat(),
                }
                return json.dumps(export_data, indent=2, default=str)
            else:
                return f"Unsupported format: {format}"

        except Exception as e:
            logger.error("Failed to export resource data: %s", e)
            return f"Export failed: {str(e)}"


# Global system monitor instance
system_monitor = SystemResourceMonitor()
