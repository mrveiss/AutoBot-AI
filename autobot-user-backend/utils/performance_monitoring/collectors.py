# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
import psutil

from config import UnifiedConfigManager
from backend.constants.network_constants import NetworkConstants
from autobot_shared.http_client import get_http_client
from backend.utils.performance_monitoring.hardware import HardwareDetector
from backend.utils.performance_monitoring.metrics import (
    GPUMetrics,
    MultiModalMetrics,
    NPUMetrics,
    ServicePerformanceMetrics,
    SystemPerformanceMetrics,
)
from backend.utils.performance_monitoring.types import AUTOBOT_PROCESS_KEYWORDS

logger = logging.getLogger(__name__)
config = UnifiedConfigManager()


class GPUCollector:
    """Collects GPU performance metrics via nvidia-smi."""

    def __init__(self, gpu_available: bool = False):
        """Initialize GPU collector."""
        self.gpu_available = gpu_available

    def _parse_metric_value(
        self, parts: List[str], index: int, as_int: bool = False
    ) -> Optional[Any]:
        """Parse GPU metric value from nvidia-smi output."""
        if index >= len(parts):
            return None
        value = parts[index]
        if value == "[Not Supported]":
            return None
        try:
            return int(float(value)) if as_int else float(value)
        except (ValueError, TypeError):
            return None

    def _parse_throttling(self, parts: List[str]) -> tuple:
        """Parse GPU throttling status.

        Returns:
            Tuple of (thermal_throttling, power_throttling)
        """
        if len(parts) <= 16:
            return False, False
        thermal_throttling = parts[16] == "Active"
        power_throttling = (
            (parts[15] == "Active" or parts[17] == "Active")
            if len(parts) > 17
            else False
        )
        return thermal_throttling, power_throttling

    def _build_metrics(self, parts: List[str]) -> Optional[GPUMetrics]:
        """Build GPUMetrics from parsed nvidia-smi output."""
        if len(parts) < 8:
            return None

        memory_used = int(float(parts[1]))
        memory_total = int(float(parts[2]))
        memory_free = memory_total - memory_used
        thermal_throttling, power_throttling = self._parse_throttling(parts)

        return GPUMetrics(
            timestamp=time.time(),
            name=parts[0],
            utilization_percent=float(parts[3]),
            memory_used_mb=memory_used,
            memory_total_mb=memory_total,
            memory_free_mb=memory_free,
            memory_utilization_percent=round((memory_used / memory_total) * 100, 1),
            temperature_celsius=int(float(parts[4])),
            power_draw_watts=self._parse_metric_value(parts, 5) or 0.0,
            gpu_clock_mhz=self._parse_metric_value(parts, 6, as_int=True) or 0,
            memory_clock_mhz=self._parse_metric_value(parts, 7, as_int=True) or 0,
            fan_speed_percent=self._parse_metric_value(parts, 8, as_int=True),
            encoder_utilization=self._parse_metric_value(parts, 9, as_int=True),
            decoder_utilization=self._parse_metric_value(parts, 10, as_int=True),
            performance_state=(
                parts[11]
                if len(parts) > 11 and parts[11] != "[Not Supported]"
                else None
            ),
            thermal_throttling=thermal_throttling,
            power_throttling=power_throttling,
        )

    async def collect(self) -> Optional[GPUMetrics]:
        """Collect comprehensive GPU performance metrics."""
        if not self.gpu_available:
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu,"
                "temperature.gpu,power.draw,clocks.current.graphics,"
                "clocks.current.memory,fan.speed,encoder.stats.utilization,"
                "decoder.stats.utilization,pstate,clocks_throttle_reasons.gpu_idle,"
                "clocks_throttle_reasons.applications_clocks_setting,"
                "clocks_throttle_reasons.sw_power_cap,"
                "clocks_throttle_reasons.hw_slowdown,"
                "clocks_throttle_reasons.hw_thermal_slowdown,"
                "clocks_throttle_reasons.hw_power_brake_slowdown",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                result_stdout = stdout.decode("utf-8")
                returncode = proc.returncode
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                logger.warning("nvidia-smi command timed out")
                return None

            if returncode != 0:
                return None

            parts = [p.strip() for p in result_stdout.strip().split(",")]
            return self._build_metrics(parts)

        except Exception as e:
            logger.error("Error collecting GPU metrics: %s", e)
            return None


class NPUCollector:
    """Collects Intel NPU performance metrics."""

    def __init__(self, npu_available: bool = False):
        """Initialize NPU collector."""
        self.npu_available = npu_available

    async def _get_worker_stats(self) -> Dict[str, Any]:
        """Get statistics from NPU worker service."""
        try:
            npu_host = config.get_host("npu_worker")
            npu_port = config.get_port("npu_worker")

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

    async def collect(self) -> Optional[NPUMetrics]:
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

    def _try_add_autobot_process(
        self, proc_info: Dict, autobot_processes: List[Dict]
    ) -> None:
        """Try to add process to AutoBot processes list."""
        cmdline = " ".join(proc_info["cmdline"]) if proc_info["cmdline"] else ""

        if not any(keyword in cmdline.lower() for keyword in AUTOBOT_PROCESS_KEYWORDS):
            return

        memory_mb = (
            proc_info["memory_info"].rss / (1024 * 1024)
            if proc_info["memory_info"]
            else 0
        )

        autobot_processes.append(
            {
                "pid": proc_info["pid"],
                "name": proc_info["name"],
                "cmdline": cmdline[:100] + "..." if len(cmdline) > 100 else cmdline,
                "cpu_percent": proc_info["cpu_percent"] or 0,
                "memory_mb": round(memory_mb, 2),
                "create_time": datetime.fromtimestamp(
                    proc_info["create_time"]
                ).isoformat(),
                "running_time_minutes": round(
                    (time.time() - proc_info["create_time"]) / 60, 1
                ),
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
            backend_host = config.get_host("backend")
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
            autobot_cpu_usage_percent=sum(
                p.get("cpu_percent", 0) for p in autobot_procs
            ),
        )

    async def collect(self) -> SystemPerformanceMetrics:
        """Collect comprehensive system performance metrics. Issue #620."""
        try:
            cpu_metrics = self._collect_cpu_metrics()
            io_metrics = self._collect_io_metrics()
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            autobot_processes = self._get_autobot_processes()

            return await self._build_system_metrics(
                cpu_metrics, io_metrics, memory, swap, autobot_processes
            )
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

    async def _collect_single_service(
        self, service_config: Dict[str, Any]
    ) -> Optional[ServicePerformanceMetrics]:
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
                "host": config.get_host("backend"),
                "port": config.get_port("backend"),
                "path": "/api/health",
            },
            {
                "name": "Frontend",
                "host": config.get_host("frontend"),
                "port": config.get_port("frontend"),
                "path": "/",
            },
            {
                "name": "Redis",
                "host": config.get_host("redis"),
                "port": config.get_port("redis"),
                "path": None,
            },
            {
                "name": "AI Stack",
                "host": config.get_host("ai_stack"),
                "port": config.get_port("ai_stack"),
                "path": "/health",
            },
            {
                "name": "NPU Worker",
                "host": config.get_host("npu_worker"),
                "port": config.get_port("npu_worker"),
                "path": "/health",
            },
            {
                "name": "Browser Service",
                "host": config.get_host("browser_service"),
                "port": config.get_port("browser_service"),
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
                logger.error(
                    "Error collecting metrics for %s: %s", service_config["name"], e
                )

        return services


class MultiModalCollector:
    """Collects multi-modal AI processing metrics."""

    def __init__(self, redis_client=None):
        """Initialize multimodal collector."""
        self.redis_client = redis_client

    async def collect(self) -> Optional[MultiModalMetrics]:
        """Collect multi-modal AI processing performance metrics."""
        try:
            if self.redis_client:
                multimodal_stats = await asyncio.to_thread(
                    self.redis_client.hgetall, "multimodal:performance_stats"
                )
                if multimodal_stats:
                    return MultiModalMetrics(
                        timestamp=time.time(),
                        text_processing_time_ms=float(
                            multimodal_stats.get("text_time_ms", 0)
                        ),
                        image_processing_time_ms=float(
                            multimodal_stats.get("image_time_ms", 0)
                        ),
                        audio_processing_time_ms=float(
                            multimodal_stats.get("audio_time_ms", 0)
                        ),
                        combined_processing_time_ms=float(
                            multimodal_stats.get("combined_time_ms", 0)
                        ),
                        pipeline_efficiency=float(
                            multimodal_stats.get("pipeline_efficiency", 0)
                        ),
                        memory_peak_usage_mb=float(
                            multimodal_stats.get("memory_peak_mb", 0)
                        ),
                        gpu_acceleration_used=multimodal_stats.get("gpu_used", "false")
                        == "true",
                        npu_acceleration_used=multimodal_stats.get("npu_used", "false")
                        == "true",
                        batch_size=int(multimodal_stats.get("batch_size", 1)),
                        throughput_items_per_second=float(
                            multimodal_stats.get("throughput_ips", 0)
                        ),
                        error_rate_percent=float(multimodal_stats.get("error_rate", 0)),
                    )

            return None

        except Exception as e:
            logger.error("Error collecting multimodal metrics: %s", e)
            return None
