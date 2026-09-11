# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Performance Metrics Collectors Module

Contains classes for collecting various performance metrics:
- GPUCollector: GPU metrics via nvidia-smi
- NPUCollector: NPU metrics via OpenVINO/NPU worker
- SystemCollector: System metrics via psutil
- ServiceCollector: Service health metrics

Extracted from performance_monitor.py as part of Issue #381 refactoring.
"""

import asyncio
import os
import time
from datetime import datetime
from typing import Any, Dict, List

import aiohttp
import psutil

from autobot_shared.gpu_telemetry import METRICS_QUERY_FIELDS, parse_nvidia_text, parse_nvidia_value, query_nvidia_gpus
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as _ssot
from constants.network_constants import NetworkConstants
from utils.performance_monitoring.hardware import HardwareDetector
from utils.performance_monitoring.metrics import (
    GPUMetrics,
    MultiModalMetrics,
    NPUMetrics,
    ServicePerformanceMetrics,
    SystemPerformanceMetrics,
)
from utils.performance_monitoring.types import AUTOBOT_PROCESS_KEYWORDS

logger = get_logger(__name__)


def _gpu_int(row: Dict[str, str], field: str) -> int | None:
    """An integer nvidia-smi cell, or None when the tool could not read it (#16289)."""
    value = parse_nvidia_value(row[field])
    return None if value is None else int(value)


class GPUCollector:
    """Collects GPU performance metrics via nvidia-smi."""

    def __init__(self, gpu_available: bool = False):
        """Initialize GPU collector."""
        self.gpu_available = gpu_available

    def _build_metrics(self, row: Dict[str, str]) -> GPUMetrics | None:
        """One GPU's metrics from a METRICS_QUERY_FIELDS row (#16289).

        None when a core value (memory, utilisation, temperature) is unreadable.
        Throttling keeps its old meaning: thermal is hw_thermal_slowdown, power
        is hw_slowdown or hw_power_brake_slowdown.
        """
        used, total, utilization, temperature = (
            parse_nvidia_value(row[field])
            for field in ("memory.used", "memory.total", "utilization.gpu", "temperature.gpu")
        )
        if used is None or total is None or utilization is None or temperature is None or not total:
            return None
        return GPUMetrics(
            timestamp=time.time(),
            name=row["name"],
            utilization_percent=utilization,
            memory_used_mb=int(used),
            memory_total_mb=int(total),
            memory_free_mb=int(total) - int(used),
            memory_utilization_percent=round((used / total) * 100, 1),
            temperature_celsius=int(temperature),
            power_draw_watts=parse_nvidia_value(row["power.draw"]) or 0.0,
            gpu_clock_mhz=_gpu_int(row, "clocks.current.graphics") or 0,
            memory_clock_mhz=_gpu_int(row, "clocks.current.memory") or 0,
            fan_speed_percent=_gpu_int(row, "fan.speed"),
            encoder_utilization=_gpu_int(row, "encoder.stats.utilization"),
            decoder_utilization=_gpu_int(row, "decoder.stats.utilization"),
            performance_state=parse_nvidia_text(row["pstate"]),
            thermal_throttling=row["clocks_throttle_reasons.hw_thermal_slowdown"] == "Active",
            power_throttling="Active"
            in (row["clocks_throttle_reasons.hw_slowdown"], row["clocks_throttle_reasons.hw_power_brake_slowdown"]),
        )

    async def collect(self) -> GPUMetrics | None:
        """The first GPU's metrics.

        #16289: autobot_shared.gpu_telemetry runs nvidia-smi and splits its rows,
        so a second GPU no longer shares the first one's comma-split. Consumers
        take one GPUMetrics; reporting every GPU to them is #16297.
        """
        if not self.gpu_available:
            return None
        rows = await asyncio.to_thread(query_nvidia_gpus, METRICS_QUERY_FIELDS)
        return self._build_metrics(rows[0]) if rows else None


class NPUCollector:
    """Collects Intel NPU performance metrics."""

    def __init__(self, npu_available: bool = False):
        """Initialize NPU collector."""
        self.npu_available = npu_available

    async def _get_worker_stats(self) -> Dict[str, Any]:
        """Get statistics from NPU worker service."""
        try:
            npu_host = _ssot.vm.npu
            npu_port = _ssot.port.npu

            http_client = get_http_client()
            async with await http_client.get(
                f"http://{npu_host}:{npu_port}/stats",
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as response:
                if response.status == 200:
                    return await response.json()

            return {}
        except Exception:
            return {}

    async def collect(self) -> NPUMetrics | None:
        """Collect Intel NPU performance metrics."""
        if not self.npu_available:
            return None

        try:
            npu_stats = await self._get_worker_stats()

            return NPUMetrics(
                timestamp=time.time(),
                hardware_detected=self.npu_available,
                driver_available=True,
                openvino_support=True,
                utilization_percent=npu_stats.get("utilization_percent", 0),
                inference_count=npu_stats.get("inference_count", 0),
                average_inference_time_ms=npu_stats.get("avg_inference_time_ms", 0),
                model_cache_hits=npu_stats.get("cache_hits", 0),
                model_cache_misses=npu_stats.get("cache_misses", 0),
                thermal_state=npu_stats.get("thermal_state", "normal"),
                power_efficiency_rating=npu_stats.get("power_efficiency", 90.0),
                acceleration_ratio=npu_stats.get("acceleration_ratio", 5.42),
                wsl_limitation=HardwareDetector.check_wsl_environment(),
            )

        except Exception as e:
            logger.error("Error collecting NPU metrics: %s", e)
            return None


class SystemCollector:
    """Collects system performance metrics via psutil."""

    def _try_add_autobot_process(self, proc_info: Dict, autobot_processes: List[Dict]) -> None:
        """Try to add process to AutoBot processes list."""
        cmdline = " ".join(proc_info["cmdline"]) if proc_info["cmdline"] else ""

        if not any(keyword in cmdline.lower() for keyword in AUTOBOT_PROCESS_KEYWORDS):
            return

        memory_mb = proc_info["memory_info"].rss / (1024 * 1024) if proc_info["memory_info"] else 0

        autobot_processes.append(
            {
                "pid": proc_info["pid"],
                "name": proc_info["name"],
                "cmdline": cmdline[:100] + "..." if len(cmdline) > 100 else cmdline,
                "cpu_percent": proc_info["cpu_percent"] or 0,
                "memory_mb": round(memory_mb, 2),
                "create_time": datetime.fromtimestamp(proc_info["create_time"]).isoformat(),
                "running_time_minutes": round((time.time() - proc_info["create_time"]) / 60, 1),
            }
        )

    def _get_autobot_processes(self) -> List[Dict[str, Any]]:
        """Get AutoBot-specific process information."""
        autobot_processes = []

        try:
            for proc in psutil.process_iter(
                [
                    "pid",
                    "name",
                    "cmdline",
                    "cpu_percent",
                    "memory_info",
                    "create_time",
                ]
            ):
                try:
                    self._try_add_autobot_process(proc.info, autobot_processes)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except Exception as e:
            logger.error("Error getting AutoBot processes: %s", e)

        return autobot_processes

    async def _measure_network_latency(self) -> float:
        """Measure network latency to backend service."""
        try:
            backend_host = _ssot.vm.main
            start_time = time.time()

            http_client = get_http_client()
            async with await http_client.get(
                f"http://{backend_host}:{NetworkConstants.BACKEND_PORT}/api/health",
                timeout=aiohttp.ClientTimeout(total=2.0),
            ) as response:
                if response.status == 200:
                    return round((time.time() - start_time) * 1000, 1)

            return 999.0
        except Exception:
            return 999.0

    def _collect_cpu_metrics(self) -> Dict[str, Any]:
        """Collect CPU-related metrics. Issue #620."""
        cpu_freq = psutil.cpu_freq()
        return {
            "percent": psutil.cpu_percent(interval=0.1),
            "per_core": psutil.cpu_percent(interval=0.1, percpu=True),
            "freq_mhz": cpu_freq.current if cpu_freq else 0,
            "load_avg": os.getloadavg() if hasattr(os, "getloadavg") else [0, 0, 0],
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
        }

    def _collect_io_metrics(self) -> Dict[str, float]:
        """Collect disk and network I/O metrics. Issue #620."""
        disk_io = psutil.disk_io_counters()
        network_io = psutil.net_io_counters()
        disk_usage = psutil.disk_usage("/")
        return {
            "disk_read_mb": getattr(disk_io, "read_bytes", 0) / (1024 * 1024),
            "disk_write_mb": getattr(disk_io, "write_bytes", 0) / (1024 * 1024),
            "disk_usage_pct": round((disk_usage.used / disk_usage.total) * 100, 1),
            "net_upload_mb": getattr(network_io, "bytes_sent", 0) / (1024 * 1024),
            "net_download_mb": getattr(network_io, "bytes_recv", 0) / (1024 * 1024),
        }

    async def _build_system_metrics(
        self, cpu: Dict, io: Dict, memory, swap, autobot_procs: List[Dict]
    ) -> SystemPerformanceMetrics:
        """Build SystemPerformanceMetrics from collected data. Issue #620."""
        return SystemPerformanceMetrics(
            timestamp=time.time(),
            cpu_usage_percent=cpu["percent"],
            cpu_cores_physical=cpu["cores_physical"],
            cpu_cores_logical=cpu["cores_logical"],
            cpu_frequency_mhz=cpu["freq_mhz"],
            cpu_load_1m=cpu["load_avg"][0],
            cpu_load_5m=cpu["load_avg"][1],
            cpu_load_15m=cpu["load_avg"][2],
            per_core_usage=cpu["per_core"],
            memory_total_gb=round(memory.total / (1024**3), 2),
            memory_used_gb=round(memory.used / (1024**3), 2),
            memory_available_gb=round(memory.available / (1024**3), 2),
            memory_usage_percent=memory.percent,
            swap_usage_percent=swap.percent,
            disk_read_mb_s=io["disk_read_mb"],
            disk_write_mb_s=io["disk_write_mb"],
            disk_usage_percent=io["disk_usage_pct"],
            disk_queue_depth=0,
            network_upload_mb_s=io["net_upload_mb"],
            network_download_mb_s=io["net_download_mb"],
            network_latency_ms=await self._measure_network_latency(),
            network_packet_loss_percent=0,
            autobot_processes=autobot_procs,
            autobot_memory_usage_mb=sum(p.get("memory_mb", 0) for p in autobot_procs),
            autobot_cpu_usage_percent=sum(p.get("cpu_percent", 0) for p in autobot_procs),
        )

    async def collect(self) -> SystemPerformanceMetrics:
        """Collect comprehensive system performance metrics. Issue #620."""
        try:
            cpu_metrics = self._collect_cpu_metrics()
            io_metrics = self._collect_io_metrics()
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            autobot_processes = self._get_autobot_processes()

            return await self._build_system_metrics(cpu_metrics, io_metrics, memory, swap, autobot_processes)
        except Exception as e:
            logger.error("Error collecting system performance metrics: %s", e)
            return self._empty_metrics()

    def _empty_metrics(self) -> SystemPerformanceMetrics:
        """Return empty metrics on error."""
        return SystemPerformanceMetrics(
            timestamp=time.time(),
            cpu_usage_percent=0,
            cpu_cores_physical=0,
            cpu_cores_logical=0,
            cpu_frequency_mhz=0,
            cpu_load_1m=0,
            cpu_load_5m=0,
            cpu_load_15m=0,
            memory_total_gb=0,
            memory_used_gb=0,
            memory_available_gb=0,
            memory_usage_percent=0,
            swap_usage_percent=0,
            disk_read_mb_s=0,
            disk_write_mb_s=0,
            disk_usage_percent=0,
            disk_queue_depth=0,
            network_upload_mb_s=0,
            network_download_mb_s=0,
            network_latency_ms=0,
            network_packet_loss_percent=0,
            autobot_memory_usage_mb=0,
            autobot_cpu_usage_percent=0,
        )


class ServiceCollector:
    """Collects distributed service performance metrics."""

    def __init__(self, redis_client=None):
        """Initialize service collector."""
        self.redis_client = redis_client

    def _calculate_health_score(self, status: str, response_time_ms: float) -> float:
        """Calculate service health score."""
        if status == "critical":
            return 0.0
        if status == "degraded":
            return 60.0
        if response_time_ms > 1000:
            return 40.0
        if response_time_ms > 500:
            return 70.0
        return 100.0

    async def _check_redis_health(self) -> str:
        """Check Redis service health."""
        if not self.redis_client:
            return "offline"
        try:
            await asyncio.to_thread(self.redis_client.ping)
            return "healthy"
        except Exception:
            return "critical"

    async def _check_http_health(self, host: str, port: int, path: str) -> str:
        """Check HTTP service health."""
        try:
            http_client = get_http_client()
            async with await http_client.get(
                f"http://{host}:{port}{path}",
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as response:
                if response.status == 200:
                    return "healthy"
                if 200 <= response.status < 400:
                    return "degraded"
                return "critical"
        except Exception:
            return "offline"

    async def _collect_single_service(self, service_config: Dict[str, Any]) -> ServicePerformanceMetrics | None:
        """Collect metrics for a single service."""
        try:
            service_name = service_config["name"]
            host = service_config["host"]
            port = service_config["port"]
            path = service_config.get("path")

            start_time = time.time()
            if service_name == "Redis":
                status = await self._check_redis_health()
            elif path:
                status = await self._check_http_health(host, port, path)
            else:
                status = "offline"

            response_time_ms = round((time.time() - start_time) * 1000, 1)

            return ServicePerformanceMetrics(
                timestamp=time.time(),
                service_name=service_name,
                host=host,
                port=port,
                status=status,
                response_time_ms=response_time_ms,
                throughput_requests_per_second=0.0,
                error_rate_percent=0.0,
                uptime_hours=24.0,
                memory_usage_mb=0.0,
                cpu_usage_percent=0.0,
                health_score=self._calculate_health_score(status, response_time_ms),
            )

        except Exception as e:
            logger.error("Error collecting single service metrics: %s", e)
            return None

    def _get_service_configs(self) -> List[Dict[str, Any]]:
        """Get configuration list for all monitored services. Issue #620."""
        return [
            {
                "name": "Backend API",
                "host": _ssot.vm.main,
                "port": _ssot.port.backend,
                "path": "/api/health",
            },
            {
                "name": "Frontend",
                "host": _ssot.vm.frontend,
                "port": _ssot.port.frontend,
                "path": "/",
            },
            {
                "name": "Redis",
                "host": _ssot.vm.redis,
                "port": _ssot.port.redis,
                "path": None,
            },
            {
                "name": "AI Stack",
                "host": _ssot.vm.aistack,
                "port": _ssot.port.aistack,
                "path": "/health",
            },
            {
                "name": "NPU Worker",
                "host": _ssot.vm.npu,
                "port": _ssot.port.npu,
                "path": "/health",
            },
            {
                "name": "Browser Service",
                "host": _ssot.vm.browser,
                "port": _ssot.port.browser,
                "path": "/health",
            },
        ]

    async def collect(self) -> List[ServicePerformanceMetrics]:
        """Collect performance metrics for all distributed services."""
        services = []

        for service_config in self._get_service_configs():
            try:
                service_metrics = await self._collect_single_service(service_config)
                if service_metrics:
                    services.append(service_metrics)
            except Exception as e:
                logger.error("Error collecting metrics for %s: %s", service_config["name"], e)

        return services


class MultiModalCollector:
    """Collects multi-modal AI processing metrics."""

    def __init__(self, redis_client=None):
        """Initialize multimodal collector."""
        self.redis_client = redis_client

    async def collect(self) -> MultiModalMetrics | None:
        """Collect multi-modal AI processing performance metrics."""
        try:
            if self.redis_client:
                multimodal_stats = await asyncio.to_thread(self.redis_client.hgetall, "multimodal:performance_stats")
                if multimodal_stats:
                    return MultiModalMetrics(
                        timestamp=time.time(),
                        text_processing_time_ms=float(multimodal_stats.get("text_time_ms", 0)),
                        image_processing_time_ms=float(multimodal_stats.get("image_time_ms", 0)),
                        audio_processing_time_ms=float(multimodal_stats.get("audio_time_ms", 0)),
                        combined_processing_time_ms=float(multimodal_stats.get("combined_time_ms", 0)),
                        pipeline_efficiency=float(multimodal_stats.get("pipeline_efficiency", 0)),
                        memory_peak_usage_mb=float(multimodal_stats.get("memory_peak_mb", 0)),
                        gpu_acceleration_used=multimodal_stats.get("gpu_used", "false") == "true",
                        npu_acceleration_used=multimodal_stats.get("npu_used", "false") == "true",
                        batch_size=int(multimodal_stats.get("batch_size", 1)),
                        throughput_items_per_second=float(multimodal_stats.get("throughput_ips", 0)),
                        error_rate_percent=float(multimodal_stats.get("error_rate", 0)),
                    )

            return None

        except Exception as e:
            logger.error("Error collecting multimodal metrics: %s", e)
            return None
