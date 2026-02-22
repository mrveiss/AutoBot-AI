#!/usr/bin/env python3
"""
AutoBot Performance Monitor
Comprehensive performance monitoring system for the 6-VM distributed architecture.
Tracks resource utilization, API response times, database performance, and hardware acceleration.

Issue #396: Converted blocking subprocess.run to asyncio.create_subprocess_exec.
"""

import asyncio
import json
import logging
import os
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import aiohttp
import psutil
from config import ConfigManager

from autobot_shared.network_constants import NetworkConstants
from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Create singleton config instance
config = ConfigManager()

# Performance monitoring configuration
MONITORING_INTERVAL = 30  # seconds

# Load alert thresholds from config with defaults
ALERT_THRESHOLDS = config.get(
    "monitoring.alert_thresholds",
    {
        "cpu_percent": 80.0,
        "memory_percent": 85.0,
        "disk_percent": 90.0,
        "api_response_time": 5.0,  # seconds
        "db_query_time": 1.0,  # seconds
        "websocket_latency": 500,  # milliseconds
    },
)

# Distributed VM configuration
VMS = {
    "main": NetworkConstants.MAIN_MACHINE_IP,  # Main machine (WSL) - Backend API
    "frontend": NetworkConstants.FRONTEND_VM_IP,  # VM1 Frontend
    "npu-worker": NetworkConstants.NPU_WORKER_VM_IP,  # VM2 NPU Worker
    "redis": NetworkConstants.REDIS_VM_IP,  # VM3 Redis
    "ai-stack": NetworkConstants.AI_STACK_VM_IP,  # VM4 AI Stack
    "browser": NetworkConstants.BROWSER_VM_IP,  # VM5 Browser
}

# Service endpoints for monitoring
SERVICE_ENDPOINTS = {
    "backend": f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}/api/health",
    "frontend": f"http://{NetworkConstants.FRONTEND_VM_IP}:{NetworkConstants.FRONTEND_PORT}/",
    "npu-worker": f"http://{NetworkConstants.NPU_WORKER_VM_IP}:{NetworkConstants.NPU_WORKER_PORT}/health",
    "ai-stack": f"http://{NetworkConstants.AI_STACK_VM_IP}:{NetworkConstants.AI_STACK_PORT}/health",
    "browser": f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}/health",
    "ollama": f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.OLLAMA_PORT}/api/version",
    "redis": f"{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.REDIS_PORT}",
}


@dataclass
class SystemMetrics:
    """System performance metrics data class."""

    timestamp: str
    hostname: str
    cpu_percent: float
    memory_percent: float
    memory_available_gb: float
    disk_percent: float
    disk_free_gb: float
    load_average: List[float]
    network_sent_mb: float
    network_recv_mb: float
    process_count: int
    gpu_utilization: Optional[float] = None
    gpu_memory_used: Optional[float] = None
    npu_utilization: Optional[float] = None


@dataclass
class ServiceMetrics:
    """Service-specific performance metrics."""

    timestamp: str
    service_name: str
    response_time: float
    status_code: Optional[int]
    is_healthy: bool
    error_message: Optional[str] = None
    custom_metrics: Optional[Dict[str, Any]] = None


@dataclass
class DatabaseMetrics:
    """Database performance metrics."""

    timestamp: str
    database_type: str
    connection_time: float
    query_count: int
    memory_usage_mb: float
    operations_per_second: float
    error_count: int = 0
    database_size_mb: Optional[float] = None


@dataclass
class InterVMMetrics:
    """Inter-VM communication performance metrics."""

    timestamp: str
    source_vm: str
    target_vm: str
    latency_ms: float
    throughput_mbps: float
    packet_loss_percent: float
    jitter_ms: float


class PerformanceMonitor:
    """Main performance monitoring class for AutoBot distributed system."""

    def __init__(self, log_level: str = "INFO"):
        self.setup_logging(log_level)
        self.logger = logging.getLogger(__name__)
        self.monitoring_active = False
        self.metrics_history = []
        self.alert_history = []
        self.redis_client = None
        _base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        self.performance_data_path = Path(_base) / "logs" / "performance"
        self.performance_data_path.mkdir(parents=True, exist_ok=True)

    def setup_logging(self, log_level: str):
        """Configure logging for performance monitoring."""
        logging.basicConfig(
            level=getattr(logging, log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(
                    os.path.join(
                        os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot"),
                        "logs/performance_monitor.log",
                    )
                ),
            ],
        )

    async def initialize_redis_connection(self):
        """Initialize Redis connection for metrics storage using canonical utility."""
        try:
            # Use canonical Redis utility following CLAUDE.md "🔴 REDIS CLIENT USAGE" policy
            from autobot_shared.redis_client import get_redis_client

            self.redis_client = get_redis_client(database="metrics")
            if self.redis_client is None:
                raise Exception("Redis client initialization returned None")

            # Test connection
            self.redis_client.ping()
            self.logger.info("✅ Redis connection established for metrics storage")
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to Redis for metrics: {e}")
            self.redis_client = None

    async def collect_system_metrics(
        self, hostname: str = "localhost"
    ) -> SystemMetrics:
        """Collect comprehensive system performance metrics."""
        try:
            # CPU and memory metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            load_avg = os.getloadavg()

            # Network metrics
            net_io = psutil.net_io_counters()

            # Process count
            process_count = len(psutil.pids())

            # GPU metrics (if available)
            gpu_util, gpu_mem = await self.get_gpu_metrics()

            # NPU metrics (Intel NPU if available)
            npu_util = await self.get_npu_metrics()

            return SystemMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                hostname=hostname,
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_available_gb=memory.available / (1024**3),
                disk_percent=disk.percent,
                disk_free_gb=disk.free / (1024**3),
                load_average=list(load_avg),
                network_sent_mb=net_io.bytes_sent / (1024**2),
                network_recv_mb=net_io.bytes_recv / (1024**2),
                process_count=process_count,
                gpu_utilization=gpu_util,
                gpu_memory_used=gpu_mem,
                npu_utilization=npu_util,
            )
        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")
            raise

    async def get_gpu_metrics(self) -> tuple[Optional[float], Optional[float]]:
        """Get GPU utilization and memory usage."""
        try:
            # Check for NVIDIA GPU (RTX 4070) using async subprocess
            process = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
                if process.returncode == 0:
                    lines = stdout.decode("utf-8").strip().split("\n")
                    if lines and lines[0]:
                        gpu_util, mem_used, mem_total = map(int, lines[0].split(", "))
                        return float(gpu_util), (mem_used / mem_total) * 100
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        except (FileNotFoundError, Exception):
            pass
        return None, None

    async def get_npu_metrics(self) -> Optional[float]:
        """Get NPU utilization (Intel AI Boost chip)."""
        try:
            # Check Intel NPU via OpenVINO tools using async subprocess
            # This is a placeholder - actual implementation depends on Intel NPU drivers
            process = await asyncio.create_subprocess_exec(
                "python3",
                "-c",
                'import openvino as ov; print("NPU Available")',  # noqa
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=3.0)
                if process.returncode == 0:
                    # NPU is available but actual utilization requires specific Intel tools
                    return 0.0  # Placeholder
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        except Exception:
            self.logger.debug("Suppressed exception in try block", exc_info=True)
        return None

    async def test_service_performance(
        self, service_name: str, endpoint: str
    ) -> ServiceMetrics:
        """Test individual service performance and health."""
        start_time = time.time()

        try:
            if service_name == "redis":
                # Special handling for Redis - use canonical pattern
                redis_test = get_redis_client(async_client=False, database="main")
                redis_test.ping()
                response_time = time.time() - start_time
                return ServiceMetrics(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    service_name=service_name,
                    response_time=response_time,
                    status_code=200,
                    is_healthy=True,
                )
            else:
                # HTTP service test
                timeout = aiohttp.ClientTimeout(total=10.0)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(endpoint) as response:
                        response_time = time.time() - start_time
                        is_healthy = response.status < 400

                        return ServiceMetrics(
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            service_name=service_name,
                            response_time=response_time,
                            status_code=response.status,
                            is_healthy=is_healthy,
                            error_message=(
                                None if is_healthy else f"HTTP {response.status}"
                            ),
                        )
        except Exception as e:
            response_time = time.time() - start_time
            return ServiceMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                service_name=service_name,
                response_time=response_time,
                status_code=None,
                is_healthy=False,
                error_message=str(e),
            )

    async def test_database_performance(self) -> List[DatabaseMetrics]:
        """Test database performance across all Redis databases."""
        db_metrics = []

        try:
            # Test Redis performance across different databases
            redis_dbs = [
                0,
                1,
                2,
                4,
                7,
                8,
            ]  # Main, Knowledge, Prompts, Metrics, Workflows, Vectors

            # Map database numbers to names for canonical Redis client
            db_map = {
                0: "main",
                1: "knowledge",
                2: "prompts",
                4: "metrics",
                7: "workflows",
                8: "vectors",
            }

            for db_num in redis_dbs:
                start_time = time.time()
                try:
                    # Use canonical Redis client pattern
                    db_name = db_map.get(db_num, "main")
                    test_client = get_redis_client(async_client=False, database=db_name)

                    # Test connection and basic operations
                    test_client.ping()
                    connection_time = time.time() - start_time

                    # Get database info
                    info = test_client.info()
                    memory_usage = info.get("used_memory", 0) / (1024**2)  # MB

                    # Test query performance
                    query_start = time.time()
                    test_client.dbsize()
                    query_time = time.time() - query_start

                    ops_per_second = 1.0 / query_time if query_time > 0 else 0

                    db_metrics.append(
                        DatabaseMetrics(
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            database_type=f"Redis_DB_{db_num}",
                            connection_time=connection_time,
                            query_count=1,
                            memory_usage_mb=memory_usage,
                            operations_per_second=ops_per_second,
                            database_size_mb=info.get("used_memory_dataset", 0)
                            / (1024**2),
                        )
                    )

                except Exception as e:
                    self.logger.error(f"Error testing Redis DB {db_num}: {e}")
                    db_metrics.append(
                        DatabaseMetrics(
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            database_type=f"Redis_DB_{db_num}",
                            connection_time=0.0,
                            query_count=0,
                            memory_usage_mb=0.0,
                            operations_per_second=0.0,
                            error_count=1,
                        )
                    )
        except Exception as e:
            self.logger.error(f"Error in database performance testing: {e}")

        return db_metrics

    def _parse_packet_loss(self, ping_output: str) -> float:
        """Parse packet loss percentage from ping output.

        Helper for test_inter_vm_performance.
        """
        lines = ping_output.split("\n")
        for line in lines:
            if "packet loss" in line:
                return float(line.split("%")[0].split()[-1])
        return 0.0

    def _parse_latency_stats(self, ping_output: str) -> tuple[float, float]:
        """Parse latency and jitter from ping output.

        Helper for test_inter_vm_performance.
        """
        lines = ping_output.split("\n")
        for line in lines:
            if "rtt min/avg/max/mdev" in line:
                stats = line.split("=")[1].strip().split("/")
                latency_ms = float(stats[1])
                jitter_ms = float(stats[3])
                return latency_ms, jitter_ms
        return 0.0, 0.0

    def _create_failed_vm_metric(self, vm_name: str) -> InterVMMetrics:
        """Create metric for failed ping test.

        Helper for test_inter_vm_performance.
        """
        return InterVMMetrics(
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_vm="main",
            target_vm=vm_name,
            latency_ms=999.0,
            throughput_mbps=0.0,
            packet_loss_percent=100.0,
            jitter_ms=0.0,
        )

    async def _execute_ping_test(self, vm_ip: str) -> tuple[int, str]:
        """Execute ping test and return returncode and stdout.

        Helper for test_inter_vm_performance.
        """
        process = await asyncio.create_subprocess_exec(
            "ping",
            "-c",
            "5",
            "-W",
            "3",
            vm_ip,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=20.0)
            return process.returncode, stdout.decode("utf-8")
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return 1, ""

    async def test_inter_vm_performance(self) -> List[InterVMMetrics]:
        """Test inter-VM communication performance."""
        inter_vm_metrics = []

        for vm_name, vm_ip in VMS.items():
            if vm_name == "main":
                continue

            try:
                ping_returncode, ping_stdout = await self._execute_ping_test(vm_ip)

                if ping_returncode == 0:
                    packet_loss = self._parse_packet_loss(ping_stdout)
                    latency_ms, jitter_ms = self._parse_latency_stats(ping_stdout)
                    throughput_mbps = max(100.0 - (latency_ms * 2), 10.0)

                    inter_vm_metrics.append(
                        InterVMMetrics(
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            source_vm="main",
                            target_vm=vm_name,
                            latency_ms=latency_ms,
                            throughput_mbps=throughput_mbps,
                            packet_loss_percent=packet_loss,
                            jitter_ms=jitter_ms,
                        )
                    )
                else:
                    inter_vm_metrics.append(self._create_failed_vm_metric(vm_name))

            except Exception as e:
                self.logger.error(
                    f"Error testing communication to {vm_name} ({vm_ip}): {e}"
                )

        return inter_vm_metrics

    async def check_performance_alerts(self, metrics: Dict[str, Any]) -> List[str]:
        """Check performance metrics against alert thresholds."""
        alerts = []

        # System metrics alerts
        if "system" in metrics:
            sys_metrics = metrics["system"]

            if sys_metrics.cpu_percent > ALERT_THRESHOLDS["cpu_percent"]:
                alerts.append(
                    f"HIGH CPU: {sys_metrics.cpu_percent:.1f}% > {ALERT_THRESHOLDS['cpu_percent']}%"
                )

            if sys_metrics.memory_percent > ALERT_THRESHOLDS["memory_percent"]:
                alerts.append(
                    f"HIGH MEMORY: {sys_metrics.memory_percent:.1f}% > {ALERT_THRESHOLDS['memory_percent']}%"
                )

            if sys_metrics.disk_percent > ALERT_THRESHOLDS["disk_percent"]:
                alerts.append(
                    f"HIGH DISK: {sys_metrics.disk_percent:.1f}% > {ALERT_THRESHOLDS['disk_percent']}%"
                )

        # Service performance alerts
        if "services" in metrics:
            for service_metric in metrics["services"]:
                if not service_metric.is_healthy:
                    alerts.append(
                        f"SERVICE DOWN: {service_metric.service_name} - {service_metric.error_message}"
                    )

                if service_metric.response_time > ALERT_THRESHOLDS["api_response_time"]:
                    alerts.append(
                        f"SLOW RESPONSE: {service_metric.service_name} - {service_metric.response_time:.2f}s"
                    )

        # Database performance alerts
        if "databases" in metrics:
            for db_metric in metrics["databases"]:
                if db_metric.error_count > 0:
                    alerts.append(
                        f"DB ERROR: {db_metric.database_type} has {db_metric.error_count} errors"
                    )

                if db_metric.connection_time > ALERT_THRESHOLDS["db_query_time"]:
                    alerts.append(
                        f"SLOW DB: {db_metric.database_type} connection time {db_metric.connection_time:.2f}s"
                    )

        # Inter-VM communication alerts
        if "inter_vm" in metrics:
            for vm_metric in metrics["inter_vm"]:
                if vm_metric.packet_loss_percent > 10.0:
                    alerts.append(
                        f"PACKET LOSS: {vm_metric.source_vm} → {vm_metric.target_vm} - {vm_metric.packet_loss_percent}%"
                    )

                if vm_metric.latency_ms > 100.0:
                    alerts.append(
                        f"HIGH LATENCY: {vm_metric.source_vm} → {vm_metric.target_vm} - {vm_metric.latency_ms:.1f}ms"
                    )

        return alerts

    async def store_metrics(self, metrics: Dict[str, Any]):
        """Store performance metrics in Redis and local files."""
        timestamp = datetime.now(timezone.utc).isoformat()

        # Store in Redis (if available)
        if self.redis_client:
            try:
                # Store latest metrics
                self.redis_client.hset(
                    "autobot:performance:latest",
                    mapping={
                        "timestamp": timestamp,
                        "data": json.dumps(metrics, default=str),
                    },
                )

                # Store historical metrics (keep last 1000 entries)
                self.redis_client.lpush(
                    "autobot:performance:history",
                    json.dumps({"timestamp": timestamp, "data": metrics}, default=str),
                )
                self.redis_client.ltrim("autobot:performance:history", 0, 999)

            except Exception as e:
                self.logger.error(f"Error storing metrics in Redis: {e}")

        # Store in local file
        try:
            metrics_file = (
                self.performance_data_path
                / f"metrics_{datetime.now().strftime('%Y%m%d')}.jsonl"
            )
            async with aiofiles.open(metrics_file, "a", encoding="utf-8") as f:
                await f.write(
                    json.dumps({"timestamp": timestamp, "data": metrics}, default=str)
                    + "\n"
                )
        except OSError as e:
            self.logger.error(f"Failed to write metrics to file {metrics_file}: {e}")
        except Exception as e:
            self.logger.error(f"Error storing metrics to file: {e}")

    async def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        try:
            # Collect all performance metrics
            system_metrics = await self.collect_system_metrics()

            # Test all services
            service_metrics = []
            for service_name, endpoint in SERVICE_ENDPOINTS.items():
                service_metric = await self.test_service_performance(
                    service_name, endpoint
                )
                service_metrics.append(service_metric)

            # Test database performance
            database_metrics = await self.test_database_performance()

            # Test inter-VM communication
            inter_vm_metrics = await self.test_inter_vm_performance()

            # Compile comprehensive metrics
            comprehensive_metrics = {
                "system": system_metrics,
                "services": service_metrics,
                "databases": database_metrics,
                "inter_vm": inter_vm_metrics,
                "hardware": {
                    "cpu_cores": psutil.cpu_count(),
                    "total_memory_gb": psutil.virtual_memory().total / (1024**3),
                    "gpu_available": system_metrics.gpu_utilization is not None,
                    "npu_available": system_metrics.npu_utilization is not None,
                },
            }

            # Check for alerts
            alerts = await self.check_performance_alerts(comprehensive_metrics)
            comprehensive_metrics["alerts"] = alerts

            # Store metrics
            await self.store_metrics(comprehensive_metrics)

            return comprehensive_metrics

        except Exception as e:
            self.logger.error(f"Error generating performance report: {e}")
            self.logger.error(traceback.format_exc())
            raise

    async def start_continuous_monitoring(self, interval: int = MONITORING_INTERVAL):
        """Start continuous performance monitoring."""
        self.logger.info(
            f"🚀 Starting AutoBot Performance Monitoring (interval: {interval}s)"
        )
        self.monitoring_active = True

        # Initialize Redis connection
        await self.initialize_redis_connection()

        try:
            while self.monitoring_active:
                try:
                    # Generate performance report
                    metrics = await self.generate_performance_report()

                    # Log summary
                    sys_metrics = metrics.get("system")
                    if sys_metrics:
                        self.logger.info(
                            f"📊 Performance: CPU={sys_metrics.cpu_percent:.1f}% "
                            f"MEM={sys_metrics.memory_percent:.1f}% "
                            f"DISK={sys_metrics.disk_percent:.1f}% "
                            f"GPU={sys_metrics.gpu_utilization or 'N/A'}%"
                        )

                    # Log alerts
                    alerts = metrics.get("alerts", [])
                    if alerts:
                        for alert in alerts:
                            self.logger.warning(f"🚨 ALERT: {alert}")

                    # Log service status
                    healthy_services = sum(
                        1 for s in metrics.get("services", []) if s.is_healthy
                    )
                    total_services = len(metrics.get("services", []))
                    self.logger.info(
                        f"🔧 Services: {healthy_services}/{total_services} healthy"
                    )

                except Exception as e:
                    self.logger.error(f"Error in monitoring cycle: {e}")

                # Wait for next cycle
                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            self.logger.info("🛑 Monitoring stopped by user")
        finally:
            self.monitoring_active = False

    def stop_monitoring(self):
        """Stop continuous monitoring."""
        self.monitoring_active = False
        self.logger.info("🛑 Stopping performance monitoring")


def _print_performance_report(metrics: dict) -> None:
    """Print a formatted performance report to stdout.

    Helper for main (#832).
    """
    logger.info("%s", "\n" + "=" * 80)
    logger.info("AutoBot Performance Report")
    logger.info("%s", "=" * 80)

    # System metrics
    sys_metrics = metrics.get("system")
    if sys_metrics:
        logger.info("\n🖥️  System Metrics:")
        logger.info(f"   CPU Usage: {sys_metrics.cpu_percent:.1f}%")
        mem_pct = sys_metrics.memory_percent
        mem_avail = sys_metrics.memory_available_gb
        logger.info(f"   Memory Usage: {mem_pct:.1f}% ({mem_avail:.1f}GB available)")
        disk_pct = sys_metrics.disk_percent
        disk_free = sys_metrics.disk_free_gb
        logger.info(f"   Disk Usage: {disk_pct:.1f}% ({disk_free:.1f}GB free)")
        logger.info(f"   Load Average: {sys_metrics.load_average}")
        logger.info(f"   Process Count: {sys_metrics.process_count}")
        if sys_metrics.gpu_utilization is not None:
            logger.info(f"   GPU Utilization: {sys_metrics.gpu_utilization:.1f}%")
        if sys_metrics.npu_utilization is not None:
            logger.info(f"   NPU Utilization: {sys_metrics.npu_utilization:.1f}%")

    # Service status
    services = metrics.get("services", [])
    if services:
        logger.info("\n🔧 Service Status:")
        for service in services:
            status = "✅ UP" if service.is_healthy else "❌ DOWN"
            logger.info(
                f"   {service.service_name}: {status} ({service.response_time:.3f}s)"
            )

    # Database performance
    databases = metrics.get("databases", [])
    if databases:
        logger.info("\n🗄️  Database Performance:")
        for db in databases:
            conn = db.connection_time
            ops = db.operations_per_second
            logger.info(
                f"   {db.database_type}: {conn:.3f}s connection, {ops:.1f} ops/s"
            )

    # Inter-VM performance
    inter_vm = metrics.get("inter_vm", [])
    if inter_vm:
        logger.info("\n🔗 Inter-VM Communication:")
        for vm in inter_vm:
            lat = vm.latency_ms
            loss = vm.packet_loss_percent
            logger.info(
                f"   {vm.source_vm} → {vm.target_vm}: {lat:.1f}ms latency, {loss:.1f}% loss"
            )

    # Alerts
    alerts = metrics.get("alerts", [])
    if alerts:
        logger.info("\n🚨 Alerts:")
        for alert in alerts:
            logger.info(f"   {alert}")
    else:
        logger.info("\n✅ No performance alerts")

    logger.info("%s", "\n" + "=" * 80)


async def main():
    """Main function for standalone performance monitoring."""
    import argparse

    parser = argparse.ArgumentParser(description="AutoBot Performance Monitor")
    parser.add_argument(
        "--interval", type=int, default=30, help="Monitoring interval in seconds"
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )

    args = parser.parse_args()

    monitor = PerformanceMonitor(log_level=args.log_level)

    if args.once:
        metrics = await monitor.generate_performance_report()
        _print_performance_report(metrics)
    else:
        await monitor.start_continuous_monitoring(interval=args.interval)


if __name__ == "__main__":
    asyncio.run(main())
