# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Monitoring API
Comprehensive monitoring of all AutoBot services

Issue #471: Added Prometheus metrics integration
"""

import asyncio
import logging
import subprocess
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import List, Optional

from backend.type_defs.common import Metadata

import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Import unified configuration system - NO HARDCODED VALUES
from src.constants.network_constants import NetworkConstants, ServiceURLs
from src.constants.path_constants import PATH
from src.monitoring.prometheus_metrics import get_metrics_manager
from src.config import UnifiedConfigManager
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)

# Issue #471: Get metrics manager for Prometheus integration
_metrics = get_metrics_manager()

# Create singleton config instance
config = UnifiedConfigManager()
router = APIRouter()

# Performance optimization: O(1) lookup for local machine IPs (Issue #326)
LOCAL_MACHINE_IPS = {
    NetworkConstants.LOCALHOST_IP,
    NetworkConstants.LOCALHOST_NAME,
    NetworkConstants.MAIN_MACHINE_IP,
}


def _parse_uptime_info(uptime_line: str) -> tuple:
    """Parse uptime line to extract load average and display string (Issue #315).

    Returns:
        Tuple of (load_avg, uptime_display)
    """
    load_avg = "unknown"
    uptime_display = "unknown"

    if "load average:" not in uptime_line:
        return load_avg, uptime_display

    load_avg = uptime_line.split("load average:")[-1].strip()
    uptime_part = uptime_line.split("load average:")[0].strip()

    if "up " not in uptime_part:
        return load_avg, uptime_display

    uptime_display = uptime_part.split("up ", 1)[1].strip()
    # Clean up extra info after the uptime (users, etc.)
    if "," in uptime_display and ("user" in uptime_display or "load" in uptime_display):
        uptime_display = uptime_display.split(",")[0].strip()

    return load_avg, uptime_display


def _parse_service_status(vm_name: str, service_result: str) -> tuple:
    """Parse service status result for a VM (Issue #315: extracted).

    Returns:
        Tuple of (service_status, active_services)
    """
    if vm_name == "redis":
        if service_result == "active":
            return "Redis active", ["redis-server"]
        return f"Redis: {service_result}", []

    if service_result.isdigit():
        service_count = int(service_result)
        if service_count > 0:
            return f"{service_count} processes", [f"{vm_name}_services"]
        return "No expected services running", []

    return service_result, []


# Issue #398: ServiceStatus factory for error cases (reduces repetition)
def _service_error_status(
    name: str,
    message: str,
    icon: str = "fas fa-server",
    category: str = "core",
    response_time: Optional[int] = None,
) -> "ServiceStatus":
    """Create a ServiceStatus for error cases (Issue #398: extracted)."""
    return ServiceStatus(
        name=name,
        status="error",
        message=message,
        response_time=response_time,
        last_check=datetime.now(),
        icon=icon,
        category=category,
    )


def _service_warning_status(
    name: str,
    message: str,
    icon: str = "fas fa-server",
    category: str = "core",
    response_time: Optional[int] = None,
) -> "ServiceStatus":
    """Create a ServiceStatus for warning cases (Issue #398: extracted)."""
    return ServiceStatus(
        name=name,
        status="warning",
        message=message,
        response_time=response_time,
        last_check=datetime.now(),
        icon=icon,
        category=category,
    )


def _vm_error_status(
    vm_name: str,
    host: str,
    message: str,
    details: Optional[Metadata] = None,
) -> "VMStatus":
    """Create a VMStatus for error cases (Issue #398: extracted)."""
    return VMStatus(
        name=vm_name.title().replace("_", " "),
        host=host,
        status="error",
        message=message,
        last_check=datetime.now(),
        icon="fas fa-server",
        services=[],
        details=details or {},
    )


def _vm_warning_status(
    vm_name: str,
    host: str,
    message: str,
    details: Optional[Metadata] = None,
) -> "VMStatus":
    """Create a VMStatus for warning cases (Issue #398: extracted)."""
    return VMStatus(
        name=vm_name.title().replace("_", " "),
        host=host,
        status="warning",
        message=message,
        last_check=datetime.now(),
        icon="fas fa-server",
        services=[],
        details=details or {},
    )


# Issue #398: Module-level VM icon mapping (used in check_vm_ssh)
_VM_ICONS = {
    "frontend": "fas fa-globe",
    "redis": "fas fa-database",
    "ai_stack": "fas fa-brain",
    "npu_worker": "fas fa-microchip",
    "browser_service": "fas fa-chrome",
}


def _build_vm_success_status(
    vm_name: str,
    host: str,
    output_lines: List[str],
    response_time: int,
) -> "VMStatus":
    """Build VMStatus for successful SSH check (Issue #398: extracted).

    Args:
        vm_name: Name of the VM
        host: Host IP/hostname
        output_lines: Lines from SSH command output
        response_time: Response time in milliseconds

    Returns:
        VMStatus with parsed details
    """
    hostname = output_lines[0] if len(output_lines) > 0 else "unknown"
    uptime_line = output_lines[1] if len(output_lines) > 1 else ""

    # Extract load average from uptime
    load_avg, uptime_display = _parse_uptime_info(uptime_line)

    # Extract service status
    service_status = "unknown"
    active_services: List[str] = []
    if len(output_lines) > 2:
        service_result = output_lines[2].strip()
        service_status, active_services = _parse_service_status(vm_name, service_result)

    return VMStatus(
        name=vm_name.title().replace("_", " "),
        host=host,
        status="online",
        message=f"Up: {uptime_display}",
        response_time=response_time,
        last_check=datetime.now(),
        icon=_VM_ICONS.get(vm_name, "fas fa-server"),
        services=active_services,
        details={
            "hostname": hostname,
            "uptime": uptime_display,
            "uptime_raw": uptime_line,
            "load_average": load_avg,
            "service_status": service_status,
            "active_services_count": len(active_services),
        },
    )


class ServiceStatus(BaseModel):
    name: str
    status: str  # "online", "offline", "warning", "error"
    message: str
    response_time: Optional[int] = None
    last_check: datetime
    details: Optional[Metadata] = None
    icon: str = "fas fa-server"
    category: str = "system"


class VMStatus(BaseModel):
    name: str
    host: str
    status: str  # "online", "offline", "warning", "error"
    message: str
    response_time: Optional[int] = None
    last_check: datetime
    details: Optional[Metadata] = None
    icon: str = "fas fa-server"
    services: List[str] = []


class ServiceMonitor:
    """Monitors all AutoBot services"""

    def __init__(self):
        """Initialize monitor with Redis and HTTP clients."""
        self.redis_client = None
        self._http_client = get_http_client()  # Use singleton HTTP client
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize monitoring clients using canonical Redis utility"""
        try:
            # Use canonical Redis utility following CLAUDE.md "🔴 REDIS CLIENT USAGE" policy
            from src.utils.redis_client import get_redis_client

            self.redis_client = get_redis_client(database="monitoring")
            if self.redis_client is None:
                logger.warning(
                    "Redis client initialization returned None (Redis disabled?)"
                )
        except Exception as e:
            logger.warning("Could not initialize Redis client: %s", e)

        # Note: Docker client initialization removed - we use VM monitoring instead
        # Services now run on VMs via systemd, not Docker containers

    async def check_backend_api(self) -> ServiceStatus:
        """Check backend API health (Issue #398: refactored with helpers).

        Issue #471: Now emits Prometheus metrics for backend API health.
        """
        import aiohttp

        start_time = time.time()
        backend_url = config.get_service_url("backend", "/api/health")

        try:
            timeout = aiohttp.ClientTimeout(
                total=config.get_timeout("http", "standard"),
                connect=config.get_timeout("tcp", "connect"),
            )
            async with await self._http_client.get(backend_url, timeout=timeout) as response:
                response_time = int((time.time() - start_time) * 1000)
                response_time_seconds = response_time / 1000.0

                # Issue #471: Emit Prometheus metrics
                _metrics.update_service_health("backend_api", 1.0 if response.status == 200 else 0.5)
                _metrics.record_service_response_time("backend_api", response_time_seconds)
                _metrics.update_service_status("backend_api", "online" if response.status == 200 else "warning")

                if response.status == 200:
                    data = await response.json()
                    return ServiceStatus(
                        name="Backend API",
                        status="online",
                        message=f"Mode: {data.get('mode', 'unknown')}",
                        response_time=response_time,
                        last_check=datetime.now(),
                        icon="fas fa-server",
                        category="core",
                        details=data,
                    )
                return _service_warning_status(
                    "Backend API", f"HTTP {response.status}", response_time=response_time
                )
        except asyncio.TimeoutError:
            logger.warning("Backend API health check timed out: %s", backend_url)
            # Issue #471: Record failure metrics
            _metrics.update_service_health("backend_api", 0.0)
            _metrics.update_service_status("backend_api", "error")
            return _service_error_status("Backend API", "Connection timed out")
        except aiohttp.ClientConnectorError as e:
            logger.warning("Backend API connection refused: %s - %s", backend_url, e)
            _metrics.update_service_health("backend_api", 0.0)
            _metrics.update_service_status("backend_api", "error")
            return _service_error_status("Backend API", "Connection refused")
        except aiohttp.ClientError as e:
            logger.warning("Backend API HTTP error: %s", e)
            _metrics.update_service_health("backend_api", 0.0)
            _metrics.update_service_status("backend_api", "error")
            return _service_error_status("Backend API", f"HTTP error: {str(e)[:50]}")
        except Exception as e:
            logger.error("Backend API check unexpected error: %s", e, exc_info=True)
            _metrics.update_service_health("backend_api", 0.0)
            _metrics.update_service_status("backend_api", "error")
            return _service_error_status("Backend API", str(e)[:100])

    def check_redis(self) -> ServiceStatus:
        """Check Redis database.

        Issue #471: Now emits Prometheus metrics for Redis health.
        """
        try:
            start_time = time.time()
            self.redis_client.ping()
            response_time = int((time.time() - start_time) * 1000)
            response_time_seconds = response_time / 1000.0

            info = self.redis_client.info()
            memory_used = info.get("used_memory_human", "Unknown")
            connected_clients = info.get("connected_clients", 0)

            # Issue #471: Emit Prometheus metrics
            _metrics.update_service_health("redis", 1.0)
            _metrics.record_service_response_time("redis", response_time_seconds)
            _metrics.update_service_status("redis", "online")
            _metrics.set_redis_server_available("main", True)

            # Also update Redis-specific metrics
            used_bytes = info.get("used_memory", 0)
            peak_bytes = info.get("used_memory_peak", 0)
            frag_ratio = info.get("mem_fragmentation_ratio", 1.0)
            _metrics.update_redis_memory_stats("main", used_bytes, peak_bytes, frag_ratio)
            _metrics.set_redis_key_count("main", info.get("db0", {}).get("keys", 0) if isinstance(info.get("db0"), dict) else 0)

            return ServiceStatus(
                name="Redis Database",
                status="online",
                message=f"Memory: {memory_used}, Clients: {connected_clients}",
                response_time=response_time,
                last_check=datetime.now(),
                icon="fas fa-database",
                category="database",
                details={
                    "memory_used": memory_used,
                    "connected_clients": connected_clients,
                    "redis_version": info.get("redis_version", "unknown"),
                },
            )
        except redis.ConnectionError:
            # Issue #471: Record failure metrics
            _metrics.update_service_health("redis", 0.0)
            _metrics.update_service_status("redis", "error")
            _metrics.set_redis_server_available("main", False)
            return ServiceStatus(
                name="Redis Database",
                status="error",
                message="Connection failed",
                last_check=datetime.now(),
                icon="fas fa-database",
                category="database",
            )
        except Exception as e:
            _metrics.update_service_health("redis", 0.5)
            _metrics.update_service_status("redis", "warning")
            return ServiceStatus(
                name="Redis Database",
                status="warning",
                message=str(e)[:100],
                last_check=datetime.now(),
                icon="fas fa-database",
                category="database",
            )

    def check_distributed_services(self) -> List[ServiceStatus]:
        """Check distributed VM services (replaces Docker checking)"""
        services = []

        # Services now run on VMs via systemd, not Docker
        # This is handled by the VM monitoring system instead
        services.append(
            ServiceStatus(
                name="Distributed Services",
                status="online",
                message="Running on VM infrastructure",
                last_check=datetime.now(),
                icon="fas fa-server",
                category="infrastructure",
                details={
                    "architecture": "distributed_vms",
                    "vm_count": 5,
                    "note": "Services monitored via VM status checks",
                },
            )
        )

        return services

    async def check_llm_services(self) -> List[ServiceStatus]:
        """Check LLM service availability (Issue #398: refactored with helpers).

        Issue #471: Now emits Prometheus metrics for LLM service health.
        """
        import aiohttp

        llm_url = config.get_service_url("backend", "/api/llm/status/comprehensive")

        try:
            start_time = time.time()
            timeout = aiohttp.ClientTimeout(
                total=config.get_timeout("http", "long"),
                connect=config.get_timeout("tcp", "connect"),
            )
            async with await self._http_client.get(llm_url, timeout=timeout) as response:
                response_time = int((time.time() - start_time) * 1000)
                response_time_seconds = response_time / 1000.0

                # Issue #471: Emit Prometheus metrics
                _metrics.update_service_health("llm_manager", 1.0 if response.status == 200 else 0.5)
                _metrics.record_service_response_time("llm_manager", response_time_seconds)
                _metrics.update_service_status("llm_manager", "online" if response.status == 200 else "warning")

                if response.status == 200:
                    data = await response.json()
                    # Update LLM provider availability metrics
                    providers = data.get("providers", {})
                    for provider, status in providers.items():
                        if isinstance(status, dict):
                            _metrics.set_llm_provider_available(provider, status.get("available", False))
                    return [ServiceStatus(
                        name="LLM Manager",
                        status="online",
                        message=f"Response: {response_time}ms",
                        response_time=response_time,
                        last_check=datetime.now(),
                        icon="fas fa-brain",
                        category="ai",
                        details=data,
                    )]
                return [_service_warning_status(
                    "LLM Manager", f"HTTP {response.status}", icon="fas fa-brain", category="ai"
                )]
        except asyncio.TimeoutError:
            logger.warning("LLM service check timed out: %s", llm_url)
            _metrics.update_service_health("llm_manager", 0.0)
            _metrics.update_service_status("llm_manager", "error")
            return [_service_error_status(
                "LLM Manager", "Connection timed out", icon="fas fa-brain", category="ai"
            )]
        except aiohttp.ClientConnectorError as e:
            logger.warning("LLM service connection refused: %s - %s", llm_url, e)
            _metrics.update_service_health("llm_manager", 0.0)
            _metrics.update_service_status("llm_manager", "error")
            return [_service_error_status(
                "LLM Manager", "Connection refused", icon="fas fa-brain", category="ai"
            )]
        except aiohttp.ClientError as e:
            logger.warning("LLM service HTTP error: %s", e)
            _metrics.update_service_health("llm_manager", 0.0)
            _metrics.update_service_status("llm_manager", "error")
            return [_service_error_status(
                "LLM Manager", f"HTTP error: {str(e)[:50]}", icon="fas fa-brain", category="ai"
            )]
        except Exception as e:
            logger.error("LLM service check unexpected error: %s", e, exc_info=True)
            _metrics.update_service_health("llm_manager", 0.0)
            _metrics.update_service_status("llm_manager", "error")
            return [_service_error_status(
                "LLM Manager", str(e)[:50], icon="fas fa-brain", category="ai"
            )]

    async def check_knowledge_base(self) -> ServiceStatus:
        """Check knowledge base status (Issue #398: refactored with helpers).

        Issue #471: Now emits Prometheus metrics for knowledge base health.
        """
        import aiohttp

        start_time = time.time()
        kb_url = config.get_service_url("backend", "/api/knowledge_base/stats/basic")

        try:
            timeout = aiohttp.ClientTimeout(
                total=config.get_timeout("knowledge_base", "search"),
                connect=config.get_timeout("tcp", "connect"),
            )
            async with await self._http_client.get(kb_url, timeout=timeout) as response:
                response_time = int((time.time() - start_time) * 1000)
                response_time_seconds = response_time / 1000.0

                # Issue #471: Emit Prometheus metrics
                _metrics.update_service_health("knowledge_base", 1.0 if response.status == 200 else 0.5)
                _metrics.record_service_response_time("knowledge_base", response_time_seconds)
                _metrics.update_service_status("knowledge_base", "online" if response.status == 200 else "warning")

                if response.status == 200:
                    data = await response.json()
                    total_docs = data.get("total_documents", 0)
                    total_vectors = data.get("total_vectors", 0)

                    # Update knowledge base specific metrics
                    _metrics.set_document_count(total_docs, "default", "all")
                    _metrics.set_vector_count(total_vectors, "default")

                    return ServiceStatus(
                        name="Knowledge Base",
                        status="online",
                        message=f"{total_docs} documents indexed",
                        response_time=response_time,
                        last_check=datetime.now(),
                        icon="fas fa-database",
                        category="knowledge",
                        details=data,
                    )
                return _service_warning_status(
                    "Knowledge Base", f"HTTP {response.status}",
                    icon="fas fa-database", category="knowledge"
                )
        except asyncio.TimeoutError:
            logger.warning("Knowledge base check timed out: %s", kb_url)
            _metrics.update_service_health("knowledge_base", 0.0)
            _metrics.update_service_status("knowledge_base", "error")
            return _service_error_status(
                "Knowledge Base", "Connection timed out", icon="fas fa-database", category="knowledge"
            )
        except aiohttp.ClientConnectorError as e:
            logger.warning("Knowledge base connection refused: %s - %s", kb_url, e)
            _metrics.update_service_health("knowledge_base", 0.0)
            _metrics.update_service_status("knowledge_base", "error")
            return _service_error_status(
                "Knowledge Base", "Connection refused", icon="fas fa-database", category="knowledge"
            )
        except aiohttp.ClientError as e:
            logger.warning("Knowledge base HTTP error: %s", e)
            _metrics.update_service_health("knowledge_base", 0.0)
            _metrics.update_service_status("knowledge_base", "error")
            return _service_error_status(
                "Knowledge Base", f"HTTP error: {str(e)[:50]}", icon="fas fa-database", category="knowledge"
            )
        except Exception as e:
            logger.error("Knowledge base check unexpected error: %s", e, exc_info=True)
            _metrics.update_service_health("knowledge_base", 0.0)
            _metrics.update_service_status("knowledge_base", "error")
            return _service_error_status(
                "Knowledge Base", str(e)[:50], icon="fas fa-database", category="knowledge"
            )

    def check_system_resources(self) -> Metadata:
        """Check system resource usage"""
        try:
            import psutil

            return {
                "cpu_percent": psutil.cpu_percent(interval=0),  # Non-blocking
                "memory": psutil.virtual_memory()._asdict(),
                "disk": psutil.disk_usage("/")._asdict(),
                "network": psutil.net_io_counters()._asdict(),
                "load_avg": (
                    list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else None
                ),
            }
        except ImportError:
            # Fallback using system commands
            try:
                # Get CPU usage
                cpu_cmd = (
                    "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print"
                    "100 - $1}'"
                )

                cpu_result = subprocess.run(
                    cpu_cmd,
                    shell=True,  # nosec B602 - hardcoded command, no user input
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                cpu_percent = (
                    float(cpu_result.stdout.strip()) if cpu_result.stdout.strip() else 0
                )

                # Get memory usage
                mem_cmd = "free | grep Mem | awk '{print ($3/$2) * 100.0}'"
                mem_result = subprocess.run(
                    mem_cmd,
                    shell=True,  # nosec B602 - hardcoded command, no user input
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                mem_percent = (
                    float(mem_result.stdout.strip()) if mem_result.stdout.strip() else 0
                )

                return {
                    "cpu_percent": cpu_percent,
                    "memory_percent": mem_percent,
                    "note": "Limited system info available",
                }
            except Exception:
                return {"error": "System resource monitoring unavailable"}

    def _get_service_check_command(self, vm_name: str) -> str:
        """Get the appropriate service check command for each VM based on architecture"""
        service_checks = {
            "frontend": (
                'ps aux | grep -v grep | grep -c "vite\\|node.*vue\\|nginx" || echo "0"'
            ),
            "redis": (
                'systemctl is-active redis-server || ps aux | grep -v grep | grep -c redis-server || echo "offline"'
            ),
            "ai_stack": (
                'ps aux | grep -v grep | grep -c "python.*ai\\|ollama" || echo "0"'
            ),
            "npu_worker": (
                'ps aux | grep -v grep | grep -c "npu\\|openvino" || echo "0"'
            ),
            "browser_service": (
                'ps aux | grep -v grep | grep -c "playwright\\|chromium" || echo "0"'
            ),
        }

        # Return the specific check for this VM, or a generic process count
        return service_checks.get(vm_name, "ps aux | grep -v grep | wc -l")

    async def check_vm_ssh(self, vm_name: str, host: str) -> VMStatus:
        """Check VM connectivity via SSH and basic health (Issue #398: refactored)."""
        try:
            start_time = time.time()
            service_cmd = self._get_service_check_command(vm_name)

            ssh_cmd = [
                "ssh", "-i", str(PATH.SSH_AUTOBOT_KEY),
                "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=no",
                "-o", "BatchMode=yes",
                f"autobot@{host}",
                f"hostname && uptime && {service_cmd}",
            ]

            result = await asyncio.create_subprocess_exec(
                *ssh_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=10)
            response_time = int((time.time() - start_time) * 1000)

            if result.returncode == 0:
                output_lines = stdout.decode().strip().split("\n")
                return _build_vm_success_status(vm_name, host, output_lines, response_time)

            error_msg = stderr.decode().strip()[:100]
            return _vm_error_status(vm_name, host, f"SSH failed: {error_msg}", {"ssh_error": error_msg})

        except asyncio.TimeoutError:
            return _vm_warning_status(vm_name, host, "SSH timeout (>10s)", {"error": "timeout"})
        except Exception as e:
            return _vm_error_status(vm_name, host, str(e)[:50], {"error": str(e)})

    def _build_main_machine_status(self, vm_hosts: dict) -> VMStatus:
        """Build VMStatus for main machine (Issue #398: extracted)."""
        main_host = vm_hosts.get("backend", NetworkConstants.MAIN_MACHINE_IP)
        return VMStatus(
            name="Main Machine (WSL)",
            host=main_host,
            status="online",
            message="Backend API + VNC",
            response_time=0,
            last_check=datetime.now(),
            icon="fas fa-desktop",
            services=["backend-api", "vnc-desktop"],
            details={
                "role": f"Backend API (port {NetworkConstants.BACKEND_PORT}) + VNC Desktop (port {NetworkConstants.VNC_PORT})",
                "note": "Frontend runs on VM1, not here",
            },
        )

    async def check_all_vms(self) -> List[VMStatus]:
        """Check status of all VMs (Issue #398: refactored)."""
        try:
            vm_hosts = config.get("infrastructure.hosts", {})
            remote_vms = {
                name: host for name, host in vm_hosts.items()
                if host not in LOCAL_MACHINE_IPS
            }

            vm_results = [self._build_main_machine_status(vm_hosts)]

            if remote_vms:
                vm_tasks = [self.check_vm_ssh(vm_name, host) for vm_name, host in remote_vms.items()]
                vm_statuses = await asyncio.gather(*vm_tasks, return_exceptions=True)
                for status in vm_statuses:
                    if isinstance(status, VMStatus):
                        vm_results.append(status)
                    else:
                        logger.error("VM check failed: %s", status)

            return vm_results

        except Exception as e:
            logger.error("VM monitoring failed: %s", e)
            return [VMStatus(
                name="VM Monitor", host="unknown", status="error",
                message=f"Monitor failed: {str(e)[:50]}",
                last_check=datetime.now(), icon="fas fa-exclamation-triangle",
                services=[], details={"error": str(e)},
            )]

    def _calculate_overall_status(self, services: List[ServiceStatus]) -> str:
        """Calculate overall status from services (Issue #398: extracted)."""
        statuses = [s.status for s in services]
        if "error" in statuses:
            return "error"
        if "warning" in statuses or "offline" in statuses:
            return "warning"
        return "online"

    def _build_status_summary(self, items: list, status_attr: str = "status") -> dict:
        """Build status summary counts (Issue #398: extracted)."""
        return {
            "total_services" if status_attr == "status" else "total_vms": len(items),
            "online": len([i for i in items if getattr(i, status_attr) == "online"]),
            "warning": len([i for i in items if getattr(i, status_attr) == "warning"]),
            "error": len([i for i in items if getattr(i, status_attr) == "error"]),
            "offline": len([i for i in items if getattr(i, status_attr) == "offline"]),
        }

    def _build_category_map(self, services: List[ServiceStatus]) -> dict:
        """Build category mapping (Issue #398: extracted, #626: O(n) optimization)."""
        # Issue #626: Single pass O(n) instead of O(n*m) nested comprehension
        from collections import defaultdict
        category_map = defaultdict(list)
        for service in services:
            category_map[service.category].append(service)
        # Ensure all expected categories exist (even if empty)
        for cat in ("core", "database", "web", "ai", "automation", "monitoring", "infrastructure", "knowledge"):
            if cat not in category_map:
                category_map[cat] = []
        return dict(category_map)

    async def get_all_services(self) -> Metadata:
        """Get comprehensive service status (Issue #398: refactored)."""
        start_time = time.time()

        # Run async checks
        tasks = [self.check_backend_api(), self.check_knowledge_base()]
        async_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect services
        all_services = [r for r in async_results if isinstance(r, ServiceStatus)]
        for r in async_results:
            if not isinstance(r, ServiceStatus):
                logger.error("Service check failed: %s", r)

        # Add sync checks
        # Issue #666: Wrap blocking sync checks in asyncio.to_thread
        redis_status = await asyncio.to_thread(self.check_redis)
        all_services.append(redis_status)
        distributed_services = await asyncio.to_thread(self.check_distributed_services)
        all_services.extend(distributed_services)
        all_services.extend(await self.check_llm_services())

        vm_statuses = await self.check_all_vms()
        # Issue #666: Wrap blocking system resource check in asyncio.to_thread
        system_resources = await asyncio.to_thread(self.check_system_resources)
        total_time = int((time.time() - start_time) * 1000)

        return {
            "overall_status": self._calculate_overall_status(all_services),
            "check_duration_ms": total_time,
            "services": [s.dict() for s in all_services],
            "vms": [vm.dict() for vm in vm_statuses],
            "system_resources": system_resources,
            "categories": self._build_category_map(all_services),
            "summary": self._build_status_summary(all_services),
            "vm_summary": self._build_status_summary(vm_statuses),
        }


# Global monitor instance - initialized lazily with thread-safe access
monitor = None
_monitor_lock = threading.Lock()


def get_monitor():
    """Get or create singleton ServiceMonitor instance with thread-safe lazy initialization."""
    global monitor
    if monitor is None:
        with _monitor_lock:
            # Double-check after acquiring lock to prevent race condition
            if monitor is None:
                monitor = ServiceMonitor()
    return monitor


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_service_status",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/services/status")
async def get_service_status():
    """Get comprehensive service status for dashboard"""
    return await get_monitor().get_all_services()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="ping",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/services/ping")
async def ping():
    """Ultra simple ping endpoint"""
    return {"ping": "pong", "timestamp": datetime.now().isoformat()}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_service_health",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/services/health")
async def get_service_health():
    """Get ultra-lightweight health check - just return that backend is responding"""
    try:
        # Backend is healthy if we're responding
        # Skip Redis and other checks for speed
        return {
            "status": "online",
            "healthy": 1,
            "total": 1,
            "warnings": 0,
            "errors": 0,
        }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return {
            "status": "error",
            "message": str(e),
            "healthy": 0,
            "total": 1,
            "warnings": 0,
            "errors": 1,
        }


def _get_cpu_info(psutil) -> dict:
    """Get CPU utilization info (Issue #398: extracted)."""
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    try:
        load_avg = list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else [0, 0, 0]
    except Exception:
        load_avg = [0, 0, 0]
    return {"usage_percent": cpu_percent, "core_count": cpu_count, "load_average": load_avg}


def _get_memory_info(psutil) -> dict:
    """Get memory info in GB (Issue #398: extracted)."""
    memory = psutil.virtual_memory()
    return {
        "total": round(memory.total / (1024**3), 2),
        "available": round(memory.available / (1024**3), 2),
        "used": round(memory.used / (1024**3), 2),
        "percent": memory.percent,
    }


def _get_disk_info(psutil) -> dict:
    """Get disk info in GB (Issue #398: extracted)."""
    disk = psutil.disk_usage("/")
    return {
        "total": round(disk.total / (1024**3), 2),
        "used": round(disk.used / (1024**3), 2),
        "free": round(disk.free / (1024**3), 2),
        "percent": round((disk.used / disk.total) * 100, 2),
    }


def _get_network_info(psutil) -> dict:
    """Get network I/O info (Issue #398: extracted)."""
    try:
        net_io = psutil.net_io_counters()
        return {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
        }
    except Exception:
        return {"error": "Network info not available"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_resources",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/resources")
async def get_system_resources():
    """Get system resource utilization (Issue #398: refactored with helpers)."""
    try:
        import psutil

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cpu": _get_cpu_info(psutil),
            "memory": _get_memory_info(psutil),
            "disk": _get_disk_info(psutil),
            "network": _get_network_info(psutil),
            "status": "ok",
        }
    except ImportError:
        return {
            "error": "psutil not available",
            "message": "System resource monitoring requires psutil package",
            "status": "unavailable",
        }
    except Exception as e:
        logger.error("Failed to get system resources: %s", e)
        return {"error": str(e), "status": "error"}


async def _check_redis_quick() -> tuple:
    """Quick Redis check (Issue #398: extracted). Returns (status, health)."""
    try:
        from src.utils.redis_client import get_redis_client

        r = get_redis_client(database="main")
        if r is None:
            raise Exception("Redis client initialization returned None")
        await asyncio.to_thread(r.ping)
        return "online", "✅"
    except Exception:
        return "offline", "❌"


async def _check_ollama_quick() -> tuple:
    """Quick Ollama check (Issue #398: extracted). Returns (status, health)."""
    import aiohttp

    try:
        http_client = get_http_client()
        timeout = aiohttp.ClientTimeout(total=2)
        async with await http_client.get(
            f"{ServiceURLs.OLLAMA_LOCAL}/api/version", timeout=timeout
        ) as response:
            if response.status == 200:
                return "online", "✅"
            return "error", "⚠️"
    except Exception:
        return "offline", "❌"


async def _check_frontend_quick() -> tuple:
    """Quick Frontend VM check. Returns (status, health)."""
    import aiohttp

    try:
        http_client = get_http_client()
        timeout = aiohttp.ClientTimeout(total=2)
        async with await http_client.get(
            ServiceURLs.FRONTEND_VM, timeout=timeout
        ) as response:
            if response.status == 200:
                return "online", "✅"
            return "error", "⚠️"
    except Exception:
        return "offline", "❌"


async def _check_npu_worker_quick() -> tuple:
    """Quick NPU Worker check (Issue #640). Returns (status, health, device_info)."""
    try:
        from backend.services.npu_client import get_npu_client

        client = get_npu_client()
        if await client.is_available():
            device_info = await client.get_device_info()
            if device_info:
                device_type = "NPU" if device_info.is_npu else ("GPU" if device_info.is_gpu else "CPU")
                return "online", "✅", {
                    "device": device_info.selected_device,
                    "device_type": device_type,
                    "real_inference": device_info.real_inference,
                }
            return "online", "✅", {"device": "unknown"}
        return "offline", "❌", None
    except ImportError:
        return "unavailable", "⚠️", {"error": "NPU client not installed"}
    except Exception as e:
        logger.debug("NPU worker check failed: %s", e)
        return "offline", "❌", None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_services",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/services")
async def get_all_services():
    """Get status of all AutoBot services (Issue #398: refactored)."""
    try:
        import os

        redis_host = os.environ.get("REDIS_HOST", NetworkConstants.REDIS_VM_IP)
        redis_port = os.environ.get("REDIS_PORT", str(NetworkConstants.REDIS_PORT))

        # Issue #640: NPU worker URL from environment
        npu_host = os.environ.get("AUTOBOT_NPU_WORKER_HOST", NetworkConstants.NPU_WORKER_VM_IP)
        npu_port = os.environ.get("AUTOBOT_NPU_WORKER_PORT", "8082")

        services = {
            "backend": {"status": "online", "url": ServiceURLs.BACKEND_LOCAL, "health": "✅"},
            "redis": {"status": "checking", "url": f"redis://{redis_host}:{redis_port}", "health": "⏳"},
            "ollama": {"status": "checking", "url": ServiceURLs.OLLAMA_LOCAL, "health": "⏳"},
            "frontend": {"status": "checking", "url": ServiceURLs.FRONTEND_VM, "health": "⏳"},
            "npu_worker": {"status": "checking", "url": f"http://{npu_host}:{npu_port}", "health": "⏳"},
        }

        # Issue #619: Check services concurrently with asyncio.gather
        # Issue #640: Added NPU worker check
        (
            (redis_status, redis_health),
            (ollama_status, ollama_health),
            (frontend_status, frontend_health),
            (npu_status, npu_health, npu_details),
        ) = await asyncio.gather(
            _check_redis_quick(),
            _check_ollama_quick(),
            _check_frontend_quick(),
            _check_npu_worker_quick(),
        )
        services["redis"]["status"], services["redis"]["health"] = redis_status, redis_health
        services["ollama"]["status"], services["ollama"]["health"] = ollama_status, ollama_health
        services["frontend"]["status"], services["frontend"]["health"] = frontend_status, frontend_health
        services["npu_worker"]["status"], services["npu_worker"]["health"] = npu_status, npu_health
        if npu_details:
            services["npu_worker"]["details"] = npu_details

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "services": services,
            "total_services": len(services),
            "online_count": sum(1 for s in services.values() if s["status"] == "online"),
            "status": "ok",
        }
    except Exception as e:
        logger.error("Failed to get services status: %s", e)
        return {"error": str(e), "status": "error"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="health_redirect",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/health")
async def health_redirect():
    """Redirect common /health requests to correct /services/health endpoint"""
    return {
        "error": "Endpoint moved",
        "message": "Please use /api/monitoring/services/health instead",
        "correct_endpoint": "/api/monitoring/services/health",
        "status": "redirect",
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vm_status",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/vms/status")
async def get_vm_status():
    """Get comprehensive VM infrastructure status for dashboard"""
    vm_statuses = await get_monitor().check_all_vms()

    # Calculate VM overall status
    vm_statuses_list = [vm.status for vm in vm_statuses]
    overall_vm_status = "online"
    if "error" in vm_statuses_list:
        overall_vm_status = "error"
    elif "warning" in vm_statuses_list:
        overall_vm_status = "warning"
    elif "offline" in vm_statuses_list:
        overall_vm_status = "warning"

    return {
        "overall_status": overall_vm_status,
        "timestamp": datetime.now().isoformat(),
        "vms": [vm.dict() for vm in vm_statuses],
        "summary": {
            "total_vms": len(vm_statuses),
            "online": len([vm for vm in vm_statuses if vm.status == "online"]),
            "warning": len([vm for vm in vm_statuses if vm.status == "warning"]),
            "error": len([vm for vm in vm_statuses if vm.status == "error"]),
            "offline": len([vm for vm in vm_statuses if vm.status == "offline"]),
        },
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_single_vm_status",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/vms/{vm_name}/status")
async def get_single_vm_status(vm_name: str):
    """Get status of a specific VM"""
    # Get VM definitions from config
    vm_hosts = config.get("infrastructure.hosts", {})

    if vm_name not in vm_hosts:
        raise HTTPException(
            status_code=404, detail=f"VM '{vm_name}' not found in infrastructure"
        )

    host = vm_hosts[vm_name]

    # Special case for main machine
    if host in LOCAL_MACHINE_IPS:
        return VMStatus(
            name="Main Machine (WSL)",
            host=host,
            status="online",
            message="Backend running",
            response_time=0,
            last_check=datetime.now(),
            icon="fas fa-desktop",
            services=["autobot-backend"],
            details={"role": "Backend API + VNC Desktop"},
        ).dict()

    # Check remote VM
    vm_status = await get_monitor().check_vm_ssh(vm_name, host)
    return vm_status.dict()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="debug_vm_config",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/debug/vm-config")
async def debug_vm_config():
    """Debug endpoint to check VM configuration"""
    try:
        vm_hosts = config.get("infrastructure.hosts", {})
        return {
            "config_available": True,
            "vm_hosts": vm_hosts,
            "remote_vms": {
                name: host
                for name, host in vm_hosts.items()
                if host not in LOCAL_MACHINE_IPS
            },
        }
    except Exception as e:
        return {"config_available": False, "error": str(e)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="debug_vm_test",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/debug/vm-test")
async def debug_vm_test():
    """Debug endpoint to test VM monitoring directly"""
    try:
        monitor = get_monitor()
        vm_statuses = await monitor.check_all_vms()
        return {
            "success": True,
            "vm_count": len(vm_statuses),
            "vms": [vm.dict() for vm in vm_statuses],
        }
    except Exception as e:
        logger.error("VM test failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "traceback": str(e.__traceback__) if hasattr(e, "__traceback__") else None,
        }
