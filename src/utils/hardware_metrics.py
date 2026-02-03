"""
AutoBot Phase 9 Comprehensive Performance Monitoring System
Advanced GPU/NPU utilization tracking, multi-modal AI performance monitoring,
and real-time system optimization for Intel Ultra 9 185H + RTX 4070 hardware.
"""

import asyncio
import json
import logging
import os
import subprocess  # nosec B404 - Required for nvidia-smi GPU queries
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional

import aiohttp
import psutil
import redis

from src.config_helper import cfg

# Import existing monitoring infrastructure

logger = logging.getLogger(__name__)


@dataclass
class GPUMetrics:
    """Comprehensive GPU performance metrics"""

    timestamp: float
    name: str
    utilization_percent: float
    memory_used_mb: int
    memory_total_mb: int
    memory_free_mb: int
    memory_utilization_percent: float
    temperature_celsius: int
    power_draw_watts: float
    gpu_clock_mhz: int
    memory_clock_mhz: int
    fan_speed_percent: Optional[int] = None
    encoder_utilization: Optional[int] = None
    decoder_utilization: Optional[int] = None
    performance_state: Optional[str] = None  # P0-P12
    thermal_throttling: bool = False
    power_throttling: bool = False


@dataclass
class NPUMetrics:
    """Intel NPU acceleration metrics"""

    timestamp: float
    hardware_detected: bool
    driver_available: bool
    openvino_support: bool
    utilization_percent: float
    inference_count: int
    average_inference_time_ms: float
    model_cache_hits: int
    model_cache_misses: int
    thermal_state: str  # "normal", "throttling", "critical"
    power_efficiency_rating: float  # 0-100
    acceleration_ratio: float  # NPU vs CPU speedup
    wsl_limitation: bool = False


@dataclass
class MultiModalMetrics:
    """Multi-modal AI processing performance metrics"""

    timestamp: float
    text_processing_time_ms: float
    image_processing_time_ms: float
    audio_processing_time_ms: float
    combined_processing_time_ms: float
    pipeline_efficiency: float  # 0-100
    memory_peak_usage_mb: float
    gpu_acceleration_used: bool
    npu_acceleration_used: bool
    batch_size: int
    throughput_items_per_second: float
    error_rate_percent: float


@dataclass
class SystemPerformanceMetrics:
    """Comprehensive system performance snapshot"""

    timestamp: float

    # CPU Performance (Intel Ultra 9 185H - 22 cores)
    cpu_usage_percent: float
    cpu_cores_physical: int
    cpu_cores_logical: int
    cpu_frequency_mhz: float
    cpu_load_1m: float
    cpu_load_5m: float
    cpu_load_15m: float
    cpu_temperature_celsius: Optional[float] = None
    per_core_usage: List[float] = field(default_factory=list)

    # Memory Performance
    memory_total_gb: float
    memory_used_gb: float
    memory_available_gb: float
    memory_usage_percent: float
    swap_usage_percent: float
    memory_bandwidth_gb_s: Optional[float] = None

    # Storage I/O Performance
    disk_read_mb_s: float
    disk_write_mb_s: float
    disk_usage_percent: float
    disk_queue_depth: float
    nvme_temperature_celsius: Optional[float] = None

    # Network Performance
    network_upload_mb_s: float
    network_download_mb_s: float
    network_latency_ms: float
    network_packet_loss_percent: float

    # AutoBot Process Performance
    autobot_processes: List[Dict[str, Any]] = field(default_factory=list)
    autobot_memory_usage_mb: float = 0
    autobot_cpu_usage_percent: float = 0


@dataclass
class ServicePerformanceMetrics:
    """Distributed service performance metrics"""

    timestamp: float
    service_name: str
    host: str
    port: int
    status: str  # "healthy", "degraded", "critical", "offline"
    response_time_ms: float
    throughput_requests_per_second: float
    error_rate_percent: float
    uptime_hours: float
    memory_usage_mb: float
    cpu_usage_percent: float
    health_score: float  # 0-100


class Phase9PerformanceMonitor:
    """
    Comprehensive Phase 9 performance monitoring system for AutoBot.
    Focuses on GPU/NPU acceleration, multi-modal AI performance, and
    distributed system optimization.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.monitoring_active = False
        self.collection_interval = 5.0  # Collect metrics every 5 seconds
        self.retention_hours = 24

        # Performance data buffers
        self.gpu_metrics_buffer = deque(maxlen=1440)  # 2 hours at 5s intervals
        self.npu_metrics_buffer = deque(maxlen=1440)
        self.multimodal_metrics_buffer = deque(maxlen=1440)
        self.system_metrics_buffer = deque(maxlen=1440)
        self.service_metrics_buffer = defaultdict(lambda: deque(maxlen=1440))

        # Performance baselines and thresholds
        self.performance_baselines = {
            "gpu_utilization_target": 80.0,  # Target GPU utilization for AI workloads
            "npu_acceleration_target": 5.0,  # Target 5x speedup over CPU
            "multimodal_pipeline_efficiency": 85.0,  # Target pipeline efficiency
            "api_response_time_threshold": 200.0,  # 200ms threshold
            "memory_usage_warning": 80.0,  # 80% memory usage warning
            "cpu_load_warning": 16.0,  # Load average warning for 22-core system
        }

        # Real-time alerting
        self.alert_callbacks = []
        self.performance_alerts = deque(maxlen=100)

        # Hardware acceleration tracking
        self.gpu_available = self._check_gpu_availability()
        self.npu_available = self._check_npu_availability()

        # Redis client for persistent storage
        self.redis_client = None
        self._initialize_redis()

        # Background monitoring task
        self.monitoring_task = None

        self.logger.info("Phase 9 Performance Monitor initialized")
        self.logger.info(f"GPU Available: {self.gpu_available}")
        self.logger.info(f"NPU Available: {self.npu_available}")

    def _initialize_redis(self):
        """Initialize Redis client for metrics storage. Issue #694."""
        try:
            # Use SSOT config for Redis connection
            from src.config.ssot_config import get_config

            ssot_config = get_config()

            self.redis_client = redis.Redis(
                host=ssot_config.vm.redis,
                port=6379,
                db=cfg.get("redis.databases.metrics.db", 4),
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=2.0,
            )
            self.redis_client.ping()
            self.logger.info("Redis client initialized for performance metrics")
        except Exception as e:
            self.logger.warning(
                f"Could not initialize Redis for performance metrics: {e}"
            )
            self.redis_client = None

    def _check_gpu_availability(self) -> bool:
        """Check if NVIDIA GPU is available and accessible"""
        try:
            result = subprocess.run(  # nosec B607 - nvidia-smi is a trusted system tool
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "RTX 4070" in result.stdout
        except Exception:
            return False

    def _check_npu_availability(self) -> bool:
        """Check if Intel NPU is available"""
        try:
            # Check CPU model for Intel Ultra series
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
                if "Intel(R) Core(TM) Ultra" in cpuinfo:
                    # Check for OpenVINO NPU support
                    try:
                        from openvino.runtime import Core

                        core = Core()
                        npu_devices = [d for d in core.available_devices if "NPU" in d]
                        return len(npu_devices) > 0
                    except ImportError:
                        return False
            return False
        except Exception:
            return False

    async def collect_gpu_metrics(self) -> Optional[GPUMetrics]:
        """Collect comprehensive GPU performance metrics"""
        if not self.gpu_available:
            return None

        try:
            # Extended nvidia-smi query for comprehensive metrics
            result = subprocess.run(  # nosec B607 - nvidia-smi is trusted
                [
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
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                parts = [p.strip() for p in result.stdout.strip().split(",")]
                if len(parts) >= 8:
                    memory_used = int(float(parts[1]))
                    memory_total = int(float(parts[2]))
                    memory_free = memory_total - memory_used

                    # Parse throttling reasons
                    thermal_throttling = False
                    power_throttling = False
                    if len(parts) > 16:
                        thermal_throttling = parts[16] == "Active"
                        power_throttling = (
                            parts[15] == "Active" or parts[17] == "Active"
                        )

                    return GPUMetrics(
                        timestamp=time.time(),
                        name=parts[0],
                        utilization_percent=float(parts[3]),
                        memory_used_mb=memory_used,
                        memory_total_mb=memory_total,
                        memory_free_mb=memory_free,
                        memory_utilization_percent=round(
                            (memory_used / memory_total) * 100, 1
                        ),
                        temperature_celsius=int(float(parts[4])),
                        power_draw_watts=float(parts[5])
                        if parts[5] != "[Not Supported]"
                        else 0.0,
                        gpu_clock_mhz=int(float(parts[6]))
                        if parts[6] != "[Not Supported]"
                        else 0,
                        memory_clock_mhz=int(float(parts[7]))
                        if parts[7] != "[Not Supported]"
                        else 0,
                        fan_speed_percent=int(float(parts[8]))
                        if len(parts) > 8 and parts[8] != "[Not Supported]"
                        else None,
                        encoder_utilization=int(float(parts[9]))
                        if len(parts) > 9 and parts[9] != "[Not Supported]"
                        else None,
                        decoder_utilization=int(float(parts[10]))
                        if len(parts) > 10 and parts[10] != "[Not Supported]"
                        else None,
                        performance_state=parts[11]
                        if len(parts) > 11 and parts[11] != "[Not Supported]"
                        else None,
                        thermal_throttling=thermal_throttling,
                        power_throttling=power_throttling,
                    )

            return None

        except Exception as e:
            self.logger.error(f"Error collecting GPU metrics: {e}")
            return None

    async def collect_npu_metrics(self) -> Optional[NPUMetrics]:
        """Collect Intel NPU performance metrics"""
        if not self.npu_available:
            return None

        try:
            # Get NPU inference statistics from Redis or NPU worker API
            npu_stats = await self._get_npu_worker_stats()

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
                acceleration_ratio=npu_stats.get(
                    "acceleration_ratio", 5.42
                ),  # From existing metrics
                wsl_limitation=self._check_wsl_environment(),
            )

        except Exception as e:
            self.logger.error(f"Error collecting NPU metrics: {e}")
            return None

    async def _get_npu_worker_stats(self) -> Dict[str, Any]:
        """Get statistics from NPU worker service. Issue #694."""
        try:
            from src.config.ssot_config import get_config

            ssot_config = get_config()

            timeout = aiohttp.ClientTimeout(total=5.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"http://{ssot_config.vm.npu_worker}:8081/stats"
                ) as response:
                    if response.status == 200:
                        return await response.json()

            return {}
        except Exception:
            return {}

    def _check_wsl_environment(self) -> bool:
        """Check if running in WSL environment"""
        try:
            with open("/proc/version", "r") as f:
                version_info = f.read()
                return "WSL" in version_info or "Microsoft" in version_info
        except Exception:
            return False

    async def collect_multimodal_metrics(self) -> Optional[MultiModalMetrics]:
        """Collect multi-modal AI processing performance metrics"""
        try:
            # Get multimodal processing stats from Redis
            if self.redis_client:
                multimodal_stats = self.redis_client.hgetall(
                    "multimodal:performance_stats"
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
            self.logger.error(f"Error collecting multimodal metrics: {e}")
            return None

    async def collect_system_performance_metrics(self) -> SystemPerformanceMetrics:
        """Collect comprehensive system performance metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
            cpu_freq = psutil.cpu_freq()
            load_avg = os.getloadavg() if hasattr(os, "getloadavg") else [0, 0, 0]

            # Memory metrics
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Disk I/O metrics
            disk_io = psutil.disk_io_counters()
            disk_usage = psutil.disk_usage("/")

            # Network metrics
            network_io = psutil.net_io_counters()

            # Get AutoBot process metrics
            autobot_processes = self._get_autobot_processes()
            autobot_memory = sum(p.get("memory_mb", 0) for p in autobot_processes)
            autobot_cpu = sum(p.get("cpu_percent", 0) for p in autobot_processes)

            # Calculate derived metrics
            disk_read_speed = getattr(disk_io, "read_bytes", 0) / (1024 * 1024)  # MB/s
            disk_write_speed = getattr(disk_io, "write_bytes", 0) / (
                1024 * 1024
            )  # MB/s
            network_upload_speed = getattr(network_io, "bytes_sent", 0) / (
                1024 * 1024
            )  # MB/s
            network_download_speed = getattr(network_io, "bytes_recv", 0) / (
                1024 * 1024
            )  # MB/s

            return SystemPerformanceMetrics(
                timestamp=time.time(),
                cpu_usage_percent=cpu_percent,
                cpu_cores_physical=psutil.cpu_count(logical=False),
                cpu_cores_logical=psutil.cpu_count(logical=True),
                cpu_frequency_mhz=cpu_freq.current if cpu_freq else 0,
                cpu_load_1m=load_avg[0],
                cpu_load_5m=load_avg[1],
                cpu_load_15m=load_avg[2],
                per_core_usage=cpu_per_core,
                memory_total_gb=round(memory.total / (1024**3), 2),
                memory_used_gb=round(memory.used / (1024**3), 2),
                memory_available_gb=round(memory.available / (1024**3), 2),
                memory_usage_percent=memory.percent,
                swap_usage_percent=swap.percent,
                disk_read_mb_s=disk_read_speed,
                disk_write_mb_s=disk_write_speed,
                disk_usage_percent=round((disk_usage.used / disk_usage.total) * 100, 1),
                disk_queue_depth=0,  # Would need specialized tools to get this
                network_upload_mb_s=network_upload_speed,
                network_download_mb_s=network_download_speed,
                network_latency_ms=await self._measure_network_latency(),
                network_packet_loss_percent=0,  # Would need specialized monitoring
                autobot_processes=autobot_processes,
                autobot_memory_usage_mb=autobot_memory,
                autobot_cpu_usage_percent=autobot_cpu,
            )

        except Exception as e:
            self.logger.error(f"Error collecting system performance metrics: {e}")
            # Return empty metrics on error
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

    def _get_autobot_processes(self) -> List[Dict[str, Any]]:
        """Get AutoBot-specific process information"""
        autobot_processes = []

        try:
            for proc in psutil.process_iter(
                ["pid", "name", "cmdline", "cpu_percent", "memory_info", "create_time"]
            ):
                try:
                    proc_info = proc.info
                    cmdline = (
                        " ".join(proc_info["cmdline"]) if proc_info["cmdline"] else ""
                    )

                    # Look for AutoBot-related processes
                    if any(
                        keyword in cmdline.lower()
                        for keyword in [
                            "autobot",
                            "fast_app_factory",
                            "run_autobot",
                            "npu-worker",
                            "ai-stack",
                            "browser-service",
                            "redis-stack",
                        ]
                    ):
                        memory_mb = (
                            proc_info["memory_info"].rss / (1024 * 1024)
                            if proc_info["memory_info"]
                            else 0
                        )

                        autobot_processes.append(
                            {
                                "pid": proc_info["pid"],
                                "name": proc_info["name"],
                                "cmdline": cmdline[:100] + "..."
                                if len(cmdline) > 100
                                else cmdline,
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
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except Exception as e:
            self.logger.error(f"Error getting AutoBot processes: {e}")

        return autobot_processes

    async def _measure_network_latency(self) -> float:
        """Measure network latency to backend service. Issue #694."""
        try:
            from src.config.ssot_config import get_config

            ssot_config = get_config()
            start_time = time.time()

            timeout = aiohttp.ClientTimeout(total=2.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"http://{ssot_config.vm.main}:8001/api/health"
                ) as response:
                    if response.status == 200:
                        return round(
                            (time.time() - start_time) * 1000, 1
                        )  # Convert to ms

            return 999.0  # High latency if failed
        except Exception:
            return 999.0

    async def collect_service_performance_metrics(
        self,
    ) -> List[ServicePerformanceMetrics]:
        """Collect performance metrics for all distributed services. Issue #694."""
        services = []

        # Use SSOT config for service endpoints
        from src.config.ssot_config import get_config

        ssot_config = get_config()

        # Define services to monitor
        service_configs = [
            {
                "name": "Backend API",
                "host": ssot_config.vm.main,
                "port": 8001,
                "path": "/api/health",
            },
            {
                "name": "Frontend",
                "host": ssot_config.vm.frontend,
                "port": 5173,
                "path": "/",
            },
            {"name": "Redis", "host": ssot_config.vm.redis, "port": 6379, "path": None},
            {
                "name": "AI Stack",
                "host": ssot_config.vm.ai_stack,
                "port": 8080,
                "path": "/health",
            },
            {
                "name": "NPU Worker",
                "host": ssot_config.vm.npu_worker,
                "port": 8081,
                "path": "/health",
            },
            {
                "name": "Browser Service",
                "host": ssot_config.vm.browser,
                "port": 3000,
                "path": "/health",
            },
        ]

        for service_config in service_configs:
            try:
                service_metrics = await self._collect_single_service_metrics(
                    service_config
                )
                if service_metrics:
                    services.append(service_metrics)
            except Exception as e:
                self.logger.error(
                    f"Error collecting metrics for {service_config['name']}: {e}"
                )

        return services

    async def _collect_single_service_metrics(
        self, service_config: Dict[str, Any]
    ) -> Optional[ServicePerformanceMetrics]:
        """Collect metrics for a single service"""
        try:
            service_name = service_config["name"]
            host = service_config["host"]
            port = service_config["port"]
            path = service_config.get("path")

            # Measure response time and check health
            start_time = time.time()
            status = "offline"

            if service_name == "Redis":
                # Special handling for Redis
                if self.redis_client:
                    try:
                        self.redis_client.ping()
                        status = "healthy"
                    except Exception:
                        status = "critical"
            else:
                # HTTP health check
                if path:
                    timeout = aiohttp.ClientTimeout(total=5.0)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(
                            f"http://{host}:{port}{path}"
                        ) as response:
                            if response.status == 200:
                                status = "healthy"
                            elif 200 <= response.status < 400:
                                status = "degraded"
                            else:
                                status = "critical"

            response_time_ms = round((time.time() - start_time) * 1000, 1)

            # Calculate additional metrics (would need service-specific implementation)
            throughput = 0.0  # Requests per second
            error_rate = 0.0  # Error percentage
            uptime_hours = 24.0  # Placeholder
            memory_usage_mb = 0.0  # Service-specific memory usage
            cpu_usage_percent = 0.0  # Service-specific CPU usage

            # Health score calculation
            health_score = 100.0
            if status == "critical":
                health_score = 0.0
            elif status == "degraded":
                health_score = 60.0
            elif response_time_ms > 1000:
                health_score = 40.0
            elif response_time_ms > 500:
                health_score = 70.0

            return ServicePerformanceMetrics(
                timestamp=time.time(),
                service_name=service_name,
                host=host,
                port=port,
                status=status,
                response_time_ms=response_time_ms,
                throughput_requests_per_second=throughput,
                error_rate_percent=error_rate,
                uptime_hours=uptime_hours,
                memory_usage_mb=memory_usage_mb,
                cpu_usage_percent=cpu_usage_percent,
                health_score=health_score,
            )

        except Exception as e:
            self.logger.error(f"Error collecting single service metrics: {e}")
            return None

    async def collect_all_metrics(self) -> Dict[str, Any]:
        """Collect all performance metrics in parallel"""
        try:
            # Collect all metrics concurrently
            tasks = [
                self.collect_gpu_metrics(),
                self.collect_npu_metrics(),
                self.collect_multimodal_metrics(),
                self.collect_system_performance_metrics(),
                self.collect_service_performance_metrics(),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            (
                gpu_metrics,
                npu_metrics,
                multimodal_metrics,
                system_metrics,
                service_metrics,
            ) = results

            # Handle exceptions
            if isinstance(gpu_metrics, Exception):
                self.logger.error(f"GPU metrics collection failed: {gpu_metrics}")
                gpu_metrics = None

            if isinstance(npu_metrics, Exception):
                self.logger.error(f"NPU metrics collection failed: {npu_metrics}")
                npu_metrics = None

            if isinstance(multimodal_metrics, Exception):
                self.logger.error(
                    f"Multimodal metrics collection failed: {multimodal_metrics}"
                )
                multimodal_metrics = None

            if isinstance(system_metrics, Exception):
                self.logger.error(f"System metrics collection failed: {system_metrics}")
                system_metrics = None

            if isinstance(service_metrics, Exception):
                self.logger.error(
                    f"Service metrics collection failed: {service_metrics}"
                )
                service_metrics = []

            # Store metrics in buffers
            if gpu_metrics:
                self.gpu_metrics_buffer.append(gpu_metrics)
            if npu_metrics:
                self.npu_metrics_buffer.append(npu_metrics)
            if multimodal_metrics:
                self.multimodal_metrics_buffer.append(multimodal_metrics)
            if system_metrics:
                self.system_metrics_buffer.append(system_metrics)

            for service_metric in service_metrics or []:
                self.service_metrics_buffer[service_metric.service_name].append(
                    service_metric
                )

            # Persist to Redis if available
            if self.redis_client:
                await self._persist_metrics_to_redis(
                    {
                        "gpu": gpu_metrics,
                        "npu": npu_metrics,
                        "multimodal": multimodal_metrics,
                        "system": system_metrics,
                        "services": service_metrics,
                    }
                )

            return {
                "timestamp": time.time(),
                "gpu": asdict(gpu_metrics) if gpu_metrics else None,
                "npu": asdict(npu_metrics) if npu_metrics else None,
                "multimodal": asdict(multimodal_metrics)
                if multimodal_metrics
                else None,
                "system": asdict(system_metrics) if system_metrics else None,
                "services": [asdict(s) for s in (service_metrics or [])],
                "collection_successful": True,
            }

        except Exception as e:
            self.logger.error(f"Error collecting all metrics: {e}")
            return {
                "timestamp": time.time(),
                "collection_successful": False,
                "error": str(e),
            }

    async def _persist_metrics_to_redis(self, metrics: Dict[str, Any]):
        """Persist metrics to Redis for historical analysis"""
        try:
            if not self.redis_client:
                return

            timestamp = time.time()

            # Store metrics with timestamp as score in sorted sets
            pipe = self.redis_client.pipeline()

            for category, metric_data in metrics.items():
                if metric_data:
                    key = f"performance_metrics:{category}"
                    value = json.dumps(
                        asdict(metric_data)
                        if hasattr(metric_data, "__dict__")
                        else metric_data,
                        default=str,
                    )
                    pipe.zadd(key, {value: timestamp})

                    # Set expiration for automatic cleanup
                    expire_seconds = self.retention_hours * 3600
                    pipe.expire(key, expire_seconds)

            pipe.execute()

        except Exception as e:
            self.logger.error(f"Error persisting metrics to Redis: {e}")

    async def start_monitoring(self):
        """Start continuous performance monitoring"""
        if self.monitoring_active:
            self.logger.warning("Performance monitoring already active")
            return

        self.monitoring_active = True
        self.logger.info("Starting Phase 9 comprehensive performance monitoring...")

        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

        return self.monitoring_task

    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Collect all metrics
                metrics = await self.collect_all_metrics()

                # Analyze for performance issues and alerts
                await self._analyze_performance_and_generate_alerts(metrics)

                # Log performance summary
                self._log_performance_summary(metrics)

                # Wait for next collection cycle
                await asyncio.sleep(self.collection_interval)

            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.collection_interval)

    async def _analyze_performance_and_generate_alerts(self, metrics: Dict[str, Any]):
        """
        Analyze metrics and generate performance alerts.

        Issue #620: Refactored to use helper functions for each analysis type.
        """
        try:
            alerts = []
            self._analyze_gpu_performance(metrics.get("gpu"), alerts)
            self._analyze_npu_performance(metrics.get("npu"), alerts)
            self._analyze_system_performance(metrics.get("system"), alerts)
            self._analyze_service_performance(metrics.get("services"), alerts)
            await self._store_and_notify_alerts(alerts)
        except Exception as e:
            self.logger.error(f"Error analyzing performance: {e}")

    def _analyze_gpu_performance(
        self, gpu: Optional[Dict[str, Any]], alerts: List[Dict[str, Any]]
    ) -> None:
        """Analyze GPU metrics and append alerts. Issue #620."""
        if not gpu:
            return
        if (
            gpu["utilization_percent"]
            < self.performance_baselines["gpu_utilization_target"]
        ):
            alerts.append(
                {
                    "category": "gpu",
                    "severity": "warning",
                    "message": (
                        f"GPU utilization below target: {gpu['utilization_percent']:.1f}% "
                        f"< {self.performance_baselines['gpu_utilization_target']}%"
                    ),
                    "recommendation": "Verify AI workloads are GPU-accelerated",
                    "timestamp": time.time(),
                }
            )
        if gpu["thermal_throttling"]:
            alerts.append(
                {
                    "category": "gpu",
                    "severity": "critical",
                    "message": f"GPU thermal throttling active at {gpu['temperature_celsius']}°C",
                    "recommendation": "Check cooling and reduce workload",
                    "timestamp": time.time(),
                }
            )

    def _analyze_npu_performance(
        self, npu: Optional[Dict[str, Any]], alerts: List[Dict[str, Any]]
    ) -> None:
        """Analyze NPU metrics and append alerts. Issue #620."""
        if not npu:
            return
        if (
            npu["acceleration_ratio"]
            < self.performance_baselines["npu_acceleration_target"]
        ):
            alerts.append(
                {
                    "category": "npu",
                    "severity": "warning",
                    "message": (
                        f"NPU acceleration ratio below target: {npu['acceleration_ratio']:.1f}x "
                        f"< {self.performance_baselines['npu_acceleration_target']}x"
                    ),
                    "recommendation": "Optimize NPU utilization or check driver status",
                    "timestamp": time.time(),
                }
            )

    def _analyze_system_performance(
        self, system: Optional[Dict[str, Any]], alerts: List[Dict[str, Any]]
    ) -> None:
        """Analyze system metrics and append alerts. Issue #620."""
        if not system:
            return
        if (
            system["memory_usage_percent"]
            > self.performance_baselines["memory_usage_warning"]
        ):
            alerts.append(
                {
                    "category": "memory",
                    "severity": "warning",
                    "message": f"High memory usage: {system['memory_usage_percent']:.1f}%",
                    "recommendation": "Enable aggressive cleanup or check for memory leaks",
                    "timestamp": time.time(),
                }
            )
        if system["cpu_load_1m"] > self.performance_baselines["cpu_load_warning"]:
            alerts.append(
                {
                    "category": "cpu",
                    "severity": "warning",
                    "message": (
                        f"High CPU load: {system['cpu_load_1m']:.1f} "
                        f"on {system['cpu_cores_logical']}-core system"
                    ),
                    "recommendation": "Check for CPU-intensive processes",
                    "timestamp": time.time(),
                }
            )

    def _analyze_service_performance(
        self, services: Optional[List[Dict[str, Any]]], alerts: List[Dict[str, Any]]
    ) -> None:
        """Analyze service metrics and append alerts. Issue #620."""
        if not services:
            return
        for service in services:
            if service["status"] in ["critical", "offline"]:
                alerts.append(
                    {
                        "category": "service",
                        "severity": "critical",
                        "message": f"Service {service['service_name']} is {service['status']}",
                        "recommendation": "Check service health and restart if necessary",
                        "timestamp": time.time(),
                    }
                )
            if (
                service["response_time_ms"]
                > self.performance_baselines["api_response_time_threshold"]
            ):
                alerts.append(
                    {
                        "category": "performance",
                        "severity": "warning",
                        "message": f"{service['service_name']} slow response: {service['response_time_ms']:.0f}ms",
                        "recommendation": "Investigate service performance bottlenecks",
                        "timestamp": time.time(),
                    }
                )

    async def _store_and_notify_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        """Store alerts and trigger callbacks. Issue #620."""
        for alert in alerts:
            self.performance_alerts.append(alert)
        if alerts:
            for callback in self.alert_callbacks:
                try:
                    await callback(alerts)
                except Exception as e:
                    self.logger.error(f"Error in alert callback: {e}")

    def _log_performance_summary(self, metrics: Dict[str, Any]):
        """Log comprehensive performance summary"""
        try:
            summary_parts = []

            # GPU summary
            if metrics.get("gpu"):
                gpu = metrics["gpu"]
                summary_parts.append(
                    f"GPU: {gpu['utilization_percent']:.0f}% util, {gpu['temperature_celsius']}°C"
                )

            # NPU summary
            if metrics.get("npu"):
                npu = metrics["npu"]
                summary_parts.append(f"NPU: {npu['acceleration_ratio']:.1f}x speedup")

            # System summary
            if metrics.get("system"):
                system = metrics["system"]
                summary_parts.append(
                    f"CPU: {system['cpu_usage_percent']:.0f}%, MEM: {system['memory_usage_percent']:.0f}%"
                )
                summary_parts.append(f"Load: {system['cpu_load_1m']:.1f}")

            # Service summary
            if metrics.get("services"):
                healthy_services = sum(
                    1 for s in metrics["services"] if s["status"] == "healthy"
                )
                total_services = len(metrics["services"])
                summary_parts.append(
                    f"Services: {healthy_services}/{total_services} healthy"
                )

            self.logger.info(f"PHASE9 PERFORMANCE: {' | '.join(summary_parts)}")

        except Exception as e:
            self.logger.error(f"Error logging performance summary: {e}")

    async def stop_monitoring(self):
        """Stop performance monitoring"""
        if not self.monitoring_active:
            return

        self.monitoring_active = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        self.logger.info("Phase 9 performance monitoring stopped")

    def get_current_performance_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive performance dashboard data"""
        try:
            dashboard = {
                "timestamp": time.time(),
                "monitoring_active": self.monitoring_active,
                "hardware_acceleration": {
                    "gpu_available": self.gpu_available,
                    "npu_available": self.npu_available,
                },
                "performance_baselines": self.performance_baselines,
                "recent_alerts": list(self.performance_alerts)[-10:],  # Last 10 alerts
            }

            # Add latest metrics
            if self.gpu_metrics_buffer:
                dashboard["gpu"] = asdict(self.gpu_metrics_buffer[-1])

            if self.npu_metrics_buffer:
                dashboard["npu"] = asdict(self.npu_metrics_buffer[-1])

            if self.multimodal_metrics_buffer:
                dashboard["multimodal"] = asdict(self.multimodal_metrics_buffer[-1])

            if self.system_metrics_buffer:
                dashboard["system"] = asdict(self.system_metrics_buffer[-1])

            # Add service statuses
            dashboard["services"] = {}
            for service_name, service_buffer in self.service_metrics_buffer.items():
                if service_buffer:
                    dashboard["services"][service_name] = asdict(service_buffer[-1])

            # Calculate performance trends
            dashboard["trends"] = self._calculate_performance_trends()

            return dashboard

        except Exception as e:
            self.logger.error(f"Error generating performance dashboard: {e}")
            return {"error": str(e), "timestamp": time.time()}

    def _calculate_performance_trends(self) -> Dict[str, Any]:
        """Calculate performance trends from recent metrics"""
        try:
            trends = {}

            # GPU utilization trend
            if len(self.gpu_metrics_buffer) >= 5:
                recent_gpu = list(self.gpu_metrics_buffer)[-5:]
                utilizations = [g.utilization_percent for g in recent_gpu]
                trends["gpu_utilization"] = {
                    "average": round(sum(utilizations) / len(utilizations), 1),
                    "trend": "increasing"
                    if utilizations[-1] > utilizations[0]
                    else "decreasing"
                    if utilizations[-1] < utilizations[0]
                    else "stable",
                }

            # System load trend
            if len(self.system_metrics_buffer) >= 5:
                recent_system = list(self.system_metrics_buffer)[-5:]
                loads = [s.cpu_load_1m for s in recent_system]
                trends["cpu_load"] = {
                    "average": round(sum(loads) / len(loads), 2),
                    "trend": "increasing"
                    if loads[-1] > loads[0]
                    else "decreasing"
                    if loads[-1] < loads[0]
                    else "stable",
                }

                # Memory usage trend
                memory_usage = [s.memory_usage_percent for s in recent_system]
                trends["memory_usage"] = {
                    "average": round(sum(memory_usage) / len(memory_usage), 1),
                    "trend": "increasing"
                    if memory_usage[-1] > memory_usage[0]
                    else "decreasing"
                    if memory_usage[-1] < memory_usage[0]
                    else "stable",
                }

            return trends

        except Exception as e:
            self.logger.error(f"Error calculating performance trends: {e}")
            return {}

    def add_alert_callback(self, callback):
        """Add callback function for performance alerts"""
        self.alert_callbacks.append(callback)

    def get_performance_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Generate performance optimization recommendations"""
        recommendations = []

        try:
            # GPU optimization recommendations
            if self.gpu_metrics_buffer:
                latest_gpu = self.gpu_metrics_buffer[-1]

                if latest_gpu.utilization_percent < 50:
                    recommendations.append(
                        {
                            "category": "gpu",
                            "priority": "medium",
                            "recommendation": "GPU underutilized - verify AI workloads use GPU acceleration",
                            "action": "Check CUDA availability and batch sizes in semantic chunking",
                            "expected_improvement": "2-3x performance increase for AI tasks",
                        }
                    )

                if latest_gpu.memory_utilization_percent > 90:
                    recommendations.append(
                        {
                            "category": "gpu",
                            "priority": "high",
                            "recommendation": "GPU memory near capacity - optimize memory usage",
                            "action": "Reduce batch sizes or implement gradient checkpointing",
                            "expected_improvement": "Prevent out-of-memory errors",
                        }
                    )

            # NPU optimization recommendations
            if self.npu_available and self.npu_metrics_buffer:
                latest_npu = self.npu_metrics_buffer[-1]

                if latest_npu.acceleration_ratio < 3.0:
                    recommendations.append(
                        {
                            "category": "npu",
                            "priority": "medium",
                            "recommendation": "NPU acceleration below optimal - check model optimization",
                            "action": "Verify OpenVINO model optimization and NPU driver status",
                            "expected_improvement": "Up to 5x speedup for inference tasks",
                        }
                    )

            # System optimization recommendations
            if self.system_metrics_buffer:
                latest_system = self.system_metrics_buffer[-1]

                if latest_system.memory_usage_percent > 85:
                    recommendations.append(
                        {
                            "category": "memory",
                            "priority": "high",
                            "recommendation": "High memory usage detected",
                            "action": "Enable aggressive cleanup in chat history and conversation managers",
                            "expected_improvement": "Prevent system slowdown and swapping",
                        }
                    )

                if latest_system.cpu_load_1m > 20:  # High for 22-core system
                    recommendations.append(
                        {
                            "category": "cpu",
                            "priority": "medium",
                            "recommendation": "High CPU load detected",
                            "action": "Optimize parallel processing and check for CPU-intensive tasks",
                            "expected_improvement": "Better system responsiveness",
                        }
                    )

            return recommendations

        except Exception as e:
            self.logger.error(f"Error generating optimization recommendations: {e}")
            return []


# Global Phase 9 performance monitor instance
phase9_monitor = Phase9PerformanceMonitor()


# Convenience functions for easy integration
async def start_phase9_monitoring():
    """Start Phase 9 comprehensive performance monitoring"""
    return await phase9_monitor.start_monitoring()


async def stop_phase9_monitoring():
    """Stop Phase 9 performance monitoring"""
    await phase9_monitor.stop_monitoring()


def get_phase9_performance_dashboard() -> Dict[str, Any]:
    """Get Phase 9 performance dashboard"""
    return phase9_monitor.get_current_performance_dashboard()


def get_phase9_optimization_recommendations() -> List[Dict[str, Any]]:
    """Get Phase 9 performance optimization recommendations"""
    return phase9_monitor.get_performance_optimization_recommendations()


async def collect_phase9_metrics() -> Dict[str, Any]:
    """Collect all Phase 9 performance metrics once"""
    return await phase9_monitor.collect_all_metrics()


def add_phase9_alert_callback(callback):
    """Add callback for Phase 9 performance alerts"""
    phase9_monitor.add_alert_callback(callback)


# Performance monitoring decorator for functions
def monitor_performance(category: str = "general"):
    """Decorator to monitor function performance"""

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time

                # Log performance
                logger.info(
                    f"PERFORMANCE [{category}]: {func.__name__} executed in {execution_time:.3f}s"
                )

                # Store in Redis if available
                if phase9_monitor.redis_client:
                    try:
                        key = f"function_performance:{category}:{func.__name__}"
                        phase9_monitor.redis_client.zadd(
                            key,
                            {
                                json.dumps(
                                    {
                                        "execution_time_ms": execution_time * 1000,
                                        "timestamp": time.time(),
                                        "args_count": len(args),
                                        "kwargs_count": len(kwargs),
                                    }
                                ): time.time()
                            },
                        )
                        phase9_monitor.redis_client.expire(
                            key, 3600
                        )  # 1 hour retention
                    except Exception:
                        pass  # nosec B110 - Non-critical metric logging

                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    f"PERFORMANCE [{category}]: {func.__name__} failed after {execution_time:.3f}s: {e}"
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                # Log performance
                logger.info(
                    f"PERFORMANCE [{category}]: {func.__name__} executed in {execution_time:.3f}s"
                )

                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    f"PERFORMANCE [{category}]: {func.__name__} failed after {execution_time:.3f}s: {e}"
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


if __name__ == "__main__":

    async def test_phase9_monitoring():
        """Test Phase 9 performance monitoring"""
        print("Testing Phase 9 Performance Monitoring System...")

        # Collect metrics
        metrics = await phase9_monitor.collect_all_metrics()
        print(f"Collected metrics: {json.dumps(metrics, indent=2, default=str)}")

        # Get dashboard
        dashboard = phase9_monitor.get_current_performance_dashboard()
        print(f"Performance dashboard: {json.dumps(dashboard, indent=2, default=str)}")

        # Get recommendations
        recommendations = phase9_monitor.get_performance_optimization_recommendations()
        print(f"Optimization recommendations: {json.dumps(recommendations, indent=2)}")

    # Run test
    asyncio.run(test_phase9_monitoring())
