# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Monitoring API
Comprehensive monitoring of all AutoBot services
"""

import asyncio
import logging
import os
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Import unified configuration system - NO HARDCODED VALUES
from src.unified_config_manager import UnifiedConfigManager

# Create singleton config instance
config = UnifiedConfigManager()
from src.constants.network_constants import NetworkConstants, ServiceURLs
from src.constants.path_constants import PATH

logger = logging.getLogger(__name__)
router = APIRouter()


class ServiceStatus(BaseModel):
    name: str
    status: str  # "online", "offline", "warning", "error"
    message: str
    response_time: Optional[int] = None
    last_check: datetime
    details: Optional[Dict[str, Any]] = None
    icon: str = "fas fa-server"
    category: str = "system"


class VMStatus(BaseModel):
    name: str
    host: str
    status: str  # "online", "offline", "warning", "error"
    message: str
    response_time: Optional[int] = None
    last_check: datetime
    details: Optional[Dict[str, Any]] = None
    icon: str = "fas fa-server"
    services: List[str] = []


class ServiceMonitor:
    """Monitors all AutoBot services"""

    def __init__(self):
        self.redis_client = None
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize monitoring clients using canonical Redis utility"""
        try:
            # Use canonical Redis utility following CLAUDE.md "🔴 REDIS CLIENT USAGE" policy
            from src.utils.redis_client import get_redis_client

            self.redis_client = get_redis_client(database="monitoring")
            if self.redis_client is None:
                logger.warning("Redis client initialization returned None (Redis disabled?)")
        except Exception as e:
            logger.warning(f"Could not initialize Redis client: {e}")

        # Note: Docker client initialization removed - we use VM monitoring instead
        # Services now run on VMs via systemd, not Docker containers

    async def check_backend_api(self) -> ServiceStatus:
        """Check backend API health"""
        try:
            import aiohttp

            start_time = time.time()

            timeout = aiohttp.ClientTimeout(
                total=config.get_timeout("http", "standard"),
                connect=config.get_timeout("tcp", "connect"),
            )
            async with aiohttp.ClientSession(timeout=timeout) as session:
                backend_url = config.get_service_url("backend", "/api/health")
                async with session.get(backend_url) as response:
                    response_time = int((time.time() - start_time) * 1000)

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
                    else:
                        return ServiceStatus(
                            name="Backend API",
                            status="warning",
                            message=f"HTTP {response.status}",
                            response_time=response_time,
                            last_check=datetime.now(),
                            icon="fas fa-server",
                            category="core",
                        )
        except Exception as e:
            return ServiceStatus(
                name="Backend API",
                status="error",
                message=str(e)[:100],
                last_check=datetime.now(),
                icon="fas fa-server",
                category="core",
            )

    def check_redis(self) -> ServiceStatus:
        """Check Redis database"""
        try:
            start_time = time.time()
            self.redis_client.ping()
            response_time = int((time.time() - start_time) * 1000)

            info = self.redis_client.info()
            memory_used = info.get("used_memory_human", "Unknown")
            connected_clients = info.get("connected_clients", 0)

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
            return ServiceStatus(
                name="Redis Database",
                status="error",
                message="Connection failed",
                last_check=datetime.now(),
                icon="fas fa-database",
                category="database",
            )
        except Exception as e:
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
        """Check LLM service availability"""
        services = []

        try:
            import aiohttp

            # Check LLM API status
            try:
                start_time = time.time()
                timeout = aiohttp.ClientTimeout(
                    total=config.get_timeout("http", "long"),
                    connect=config.get_timeout("tcp", "connect"),
                )
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    llm_url = config.get_service_url(
                        "backend", "/api/llm/status/comprehensive"
                    )
                    async with session.get(llm_url) as response:
                        response_time = int((time.time() - start_time) * 1000)

                        if response.status == 200:
                            data = await response.json()

                            services.append(
                                ServiceStatus(
                                    name="LLM Manager",
                                    status="online",
                                    message=f"Response: {response_time}ms",
                                    response_time=response_time,
                                    last_check=datetime.now(),
                                    icon="fas fa-brain",
                                    category="ai",
                                    details=data,
                                )
                            )
                        else:
                            services.append(
                                ServiceStatus(
                                    name="LLM Manager",
                                    status="warning",
                                    message=f"HTTP {response.status}",
                                    last_check=datetime.now(),
                                    icon="fas fa-brain",
                                    category="ai",
                                )
                            )
            except Exception as e:
                services.append(
                    ServiceStatus(
                        name="LLM Manager",
                        status="error",
                        message=str(e)[:50],
                        last_check=datetime.now(),
                        icon="fas fa-brain",
                        category="ai",
                    )
                )

        except ImportError:
            services.append(
                ServiceStatus(
                    name="LLM Services",
                    status="warning",
                    message="HTTP client unavailable",
                    last_check=datetime.now(),
                    icon="fas fa-brain",
                    category="ai",
                )
            )

        return services

    async def check_knowledge_base(self) -> ServiceStatus:
        """Check knowledge base status"""
        try:
            import aiohttp

            start_time = time.time()

            # Use configuration system for knowledge base URL
            kb_url = config.get_service_url("backend", "/api/knowledge_base/stats/basic")

            timeout = aiohttp.ClientTimeout(
                total=config.get_timeout("knowledge_base", "search"),
                connect=config.get_timeout("tcp", "connect"),
            )
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(kb_url) as response:
                    response_time = int((time.time() - start_time) * 1000)

                    if response.status == 200:
                        data = await response.json()
                        total_docs = data.get("total_documents", 0)

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
                    else:
                        return ServiceStatus(
                            name="Knowledge Base",
                            status="warning",
                            message=f"HTTP {response.status}",
                            last_check=datetime.now(),
                            icon="fas fa-database",
                            category="knowledge",
                        )
        except Exception as e:
            return ServiceStatus(
                name="Knowledge Base",
                status="error",
                message=str(e)[:50],
                last_check=datetime.now(),
                icon="fas fa-database",
                category="knowledge",
            )

    def check_system_resources(self) -> Dict[str, Any]:
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
                cpu_cmd = "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'"
                cpu_result = subprocess.run(
                    cpu_cmd, shell=True, capture_output=True, text=True, timeout=5
                )
                cpu_percent = (
                    float(cpu_result.stdout.strip()) if cpu_result.stdout.strip() else 0
                )

                # Get memory usage
                mem_cmd = "free | grep Mem | awk '{print ($3/$2) * 100.0}'"
                mem_result = subprocess.run(
                    mem_cmd, shell=True, capture_output=True, text=True, timeout=5
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
            "frontend": 'ps aux | grep -v grep | grep -c "vite\\|node.*vue\\|nginx" || echo "0"',
            "redis": 'systemctl is-active redis-server || ps aux | grep -v grep | grep -c redis-server || echo "offline"',
            "ai_stack": 'ps aux | grep -v grep | grep -c "python.*ai\\|ollama" || echo "0"',
            "npu_worker": 'ps aux | grep -v grep | grep -c "npu\\|openvino" || echo "0"',
            "browser_service": 'ps aux | grep -v grep | grep -c "playwright\\|chromium" || echo "0"',
        }

        # Return the specific check for this VM, or a generic process count
        return service_checks.get(vm_name, "ps aux | grep -v grep | wc -l")

    async def check_vm_ssh(self, vm_name: str, host: str) -> VMStatus:
        """Check VM connectivity via SSH and basic health"""
        try:
            start_time = time.time()

            # SSH command to check basic health: hostname, uptime, and service status based on VM type
            # Different VMs have different expected services
            service_cmd = self._get_service_check_command(vm_name)

            ssh_cmd = [
                "ssh",
                "-i",
                str(PATH.SSH_AUTOBOT_KEY),
                "-o",
                "ConnectTimeout=5",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "BatchMode=yes",
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
                hostname = output_lines[0] if len(output_lines) > 0 else "unknown"
                uptime_line = output_lines[1] if len(output_lines) > 1 else ""

                # Extract load average from uptime (FIXED parsing)
                load_avg = "unknown"
                uptime_display = "unknown"
                if "load average:" in uptime_line:
                    load_avg = uptime_line.split("load average:")[-1].strip()
                    # Extract just the uptime part for display (before load average)
                    uptime_part = uptime_line.split("load average:")[0].strip()
                    # Remove the current time from the beginning
                    if "up " in uptime_part:
                        uptime_display = uptime_part.split("up ", 1)[1].strip()
                        # Clean up extra info after the uptime (users, etc.)
                        if "," in uptime_display and (
                            "user" in uptime_display or "load" in uptime_display
                        ):
                            uptime_display = uptime_display.split(",")[0].strip()

                # Extract service status (FIXED for correct VM architecture)
                service_status = "unknown"
                active_services = []
                if len(output_lines) > 2:
                    service_result = output_lines[2].strip()
                    # Parse service check result based on VM type
                    if vm_name == "redis":
                        if service_result == "active":
                            active_services = ["redis-server"]
                            service_status = "Redis active"
                        else:
                            service_status = f"Redis: {service_result}"
                    elif service_result.isdigit():
                        service_count = int(service_result)
                        if service_count > 0:
                            active_services = [f"{vm_name}_services"]
                            service_status = f"{service_count} processes"
                        else:
                            service_status = "No expected services running"
                    else:
                        service_status = service_result

                vm_icons = {
                    "frontend": "fas fa-globe",
                    "redis": "fas fa-database",
                    "ai_stack": "fas fa-brain",
                    "npu_worker": "fas fa-microchip",
                    "browser_service": "fas fa-chrome",
                }

                return VMStatus(
                    name=vm_name.title().replace("_", " "),
                    host=host,
                    status="online",
                    message=f"Up: {uptime_display}",
                    response_time=response_time,
                    last_check=datetime.now(),
                    icon=vm_icons.get(vm_name, "fas fa-server"),
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
            else:
                error_msg = stderr.decode().strip()[:100]
                return VMStatus(
                    name=vm_name.title().replace("_", " "),
                    host=host,
                    status="error",
                    message=f"SSH failed: {error_msg}",
                    last_check=datetime.now(),
                    icon="fas fa-server",
                    services=[],
                    details={"ssh_error": error_msg},
                )

        except asyncio.TimeoutError:
            return VMStatus(
                name=vm_name.title().replace("_", " "),
                host=host,
                status="warning",
                message="SSH timeout (>10s)",
                last_check=datetime.now(),
                icon="fas fa-server",
                services=[],
                details={"error": "timeout"},
            )
        except Exception as e:
            return VMStatus(
                name=vm_name.title().replace("_", " "),
                host=host,
                status="error",
                message=str(e)[:50],
                last_check=datetime.now(),
                icon="fas fa-server",
                services=[],
                details={"error": str(e)},
            )

    async def check_all_vms(self) -> List[VMStatus]:
        """Check status of all VMs in the infrastructure"""
        try:
            # Get VM definitions from config
            vm_hosts = config.get("infrastructure.hosts", {})

            # Filter out localhost/main machine entries
            remote_vms = {
                name: host
                for name, host in vm_hosts.items()
                if host not in [NetworkConstants.LOCALHOST_IP, NetworkConstants.LOCALHOST_NAME, NetworkConstants.MAIN_MACHINE_IP]
            }

            # Add main machine status
            vm_results = []

            # Main machine (backend host) - FIXED: Only backend API + VNC Desktop, NO frontend
            main_host = vm_hosts.get("backend", NetworkConstants.MAIN_MACHINE_IP)
            vm_results.append(
                VMStatus(
                    name="Main Machine (WSL)",
                    host=main_host,
                    status="online",
                    message="Backend API + VNC",
                    response_time=0,
                    last_check=datetime.now(),
                    icon="fas fa-desktop",
                    services=[
                        "backend-api",
                        "vnc-desktop",
                    ],  # FIXED: Correct services only
                    details={
                        "role": "Backend API (port 8001) + VNC Desktop (port 6080)",
                        "note": "Frontend runs on VM1, not here",
                    },
                )
            )

            # Check remote VMs concurrently
            if remote_vms:
                vm_tasks = [
                    self.check_vm_ssh(vm_name, host)
                    for vm_name, host in remote_vms.items()
                ]

                vm_statuses = await asyncio.gather(*vm_tasks, return_exceptions=True)

                for status in vm_statuses:
                    if isinstance(status, VMStatus):
                        vm_results.append(status)
                    else:
                        logger.error(f"VM check failed: {status}")

            return vm_results

        except Exception as e:
            logger.error(f"VM monitoring failed: {e}")
            return [
                VMStatus(
                    name="VM Monitor",
                    host="unknown",
                    status="error",
                    message=f"Monitor failed: {str(e)[:50]}",
                    last_check=datetime.now(),
                    icon="fas fa-exclamation-triangle",
                    services=[],
                    details={"error": str(e)},
                )
            ]

    async def get_all_services(self) -> Dict[str, Any]:
        """Get comprehensive service status"""
        start_time = time.time()

        # Run all checks concurrently
        tasks = [
            self.check_backend_api(),
            self.check_knowledge_base(),
        ]

        # Add sync checks
        redis_status = self.check_redis()
        distributed_services = self.check_distributed_services()
        llm_services = await self.check_llm_services()
        system_resources = self.check_system_resources()

        # Wait for async tasks
        async_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Compile all services
        all_services = []

        # Add async results
        for result in async_results:
            if isinstance(result, ServiceStatus):
                all_services.append(result)
            else:
                logger.error(f"Service check failed: {result}")

        # Add sync results
        all_services.append(redis_status)
        all_services.extend(distributed_services)
        all_services.extend(llm_services)

        # Get VM status
        vm_statuses = await self.check_all_vms()

        # Calculate overall status
        statuses = [s.status for s in all_services]
        overall_status = "online"
        if "error" in statuses:
            overall_status = "error"
        elif "warning" in statuses:
            overall_status = "warning"
        elif "offline" in statuses:
            overall_status = "warning"

        total_time = int((time.time() - start_time) * 1000)

        return {
            "overall_status": overall_status,
            "check_duration_ms": total_time,
            "services": [s.dict() for s in all_services],
            "vms": [vm.dict() for vm in vm_statuses],
            "system_resources": system_resources,
            "categories": {
                "core": [s for s in all_services if s.category == "core"],
                "database": [s for s in all_services if s.category == "database"],
                "web": [s for s in all_services if s.category == "web"],
                "ai": [s for s in all_services if s.category == "ai"],
                "automation": [s for s in all_services if s.category == "automation"],
                "monitoring": [s for s in all_services if s.category == "monitoring"],
                "infrastructure": [
                    s for s in all_services if s.category == "infrastructure"
                ],
                "knowledge": [s for s in all_services if s.category == "knowledge"],
            },
            "summary": {
                "total_services": len(all_services),
                "online": len([s for s in all_services if s.status == "online"]),
                "warning": len([s for s in all_services if s.status == "warning"]),
                "error": len([s for s in all_services if s.status == "error"]),
                "offline": len([s for s in all_services if s.status == "offline"]),
            },
            "vm_summary": {
                "total_vms": len(vm_statuses),
                "online": len([vm for vm in vm_statuses if vm.status == "online"]),
                "warning": len([vm for vm in vm_statuses if vm.status == "warning"]),
                "error": len([vm for vm in vm_statuses if vm.status == "error"]),
                "offline": len([vm for vm in vm_statuses if vm.status == "offline"]),
            },
        }


# Global monitor instance - initialized lazily
monitor = None


def get_monitor():
    global monitor
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
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "healthy": 0,
            "total": 1,
            "warnings": 0,
            "errors": 1,
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_resources",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/resources")
async def get_system_resources():
    """Get system resource utilization (CPU, memory, disk)"""
    try:
        import psutil

        # CPU utilization
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()

        # Memory information
        memory = psutil.virtual_memory()
        memory_info = {
            "total": round(memory.total / (1024**3), 2),  # GB
            "available": round(memory.available / (1024**3), 2),  # GB
            "used": round(memory.used / (1024**3), 2),  # GB
            "percent": memory.percent,
        }

        # Disk information
        disk = psutil.disk_usage("/")
        disk_info = {
            "total": round(disk.total / (1024**3), 2),  # GB
            "used": round(disk.used / (1024**3), 2),  # GB
            "free": round(disk.free / (1024**3), 2),  # GB
            "percent": round((disk.used / disk.total) * 100, 2),
        }

        # Network information (optional)
        try:
            net_io = psutil.net_io_counters()
            network_info = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
            }
        except Exception:
            network_info = {"error": "Network info not available"}

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cpu": {"usage_percent": cpu_percent, "core_count": cpu_count},
            "memory": memory_info,
            "disk": disk_info,
            "network": network_info,
            "status": "ok",
        }
    except ImportError:
        return {
            "error": "psutil not available",
            "message": "System resource monitoring requires psutil package",
            "status": "unavailable",
        }
    except Exception as e:
        logger.error(f"Failed to get system resources: {e}")
        return {"error": str(e), "status": "error"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_services",
    error_code_prefix="SERVICE_MONITOR",
)
@router.get("/services")
async def get_all_services():
    """Get status of all AutoBot services"""
    try:
        # Get distributed service URLs from environment
        import os

        redis_host = os.environ.get("REDIS_HOST", NetworkConstants.REDIS_VM_IP)
        redis_port = os.environ.get("REDIS_PORT", str(NetworkConstants.REDIS_PORT))

        services = {
            "backend": {
                "status": "online",
                "url": ServiceURLs.BACKEND_LOCAL,
                "health": "✅",
            },
            "redis": {
                "status": "checking",
                "url": f"redis://{redis_host}:{redis_port}",
                "health": "⏳",
            },
            "ollama": {
                "status": "checking",
                "url": ServiceURLs.OLLAMA_LOCAL,
                "health": "⏳",
            },
            "frontend": {
                "status": "checking",
                "url": ServiceURLs.FRONTEND_VM,
                "health": "⏳",
            },
        }

        # Quick Redis check using canonical utility
        try:
            from src.utils.redis_client import get_redis_client

            r = get_redis_client(database="main")
            if r is None:
                raise Exception("Redis client initialization returned None")
            r.ping()
            services["redis"]["status"] = "online"
            services["redis"]["health"] = "✅"
        except Exception:
            services["redis"]["status"] = "offline"
            services["redis"]["health"] = "❌"

        # Quick Ollama check
        try:
            import aiohttp

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=2)
            ) as session:
                async with session.get(
                    f"{ServiceURLs.OLLAMA_LOCAL}/api/version"
                ) as response:
                    if response.status == 200:
                        services["ollama"]["status"] = "online"
                        services["ollama"]["health"] = "✅"
                    else:
                        services["ollama"]["status"] = "error"
                        services["ollama"]["health"] = "⚠️"
        except Exception:
            services["ollama"]["status"] = "offline"
            services["ollama"]["health"] = "❌"

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "services": services,
            "total_services": len(services),
            "online_count": sum(
                1 for s in services.values() if s["status"] == "online"
            ),
            "status": "ok",
        }
    except Exception as e:
        logger.error(f"Failed to get services status: {e}")
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
    if host in [NetworkConstants.LOCALHOST_IP, NetworkConstants.LOCALHOST_NAME, NetworkConstants.MAIN_MACHINE_IP]:
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
                if host not in [NetworkConstants.LOCALHOST_IP, NetworkConstants.LOCALHOST_NAME, NetworkConstants.MAIN_MACHINE_IP]
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
        logger.error(f"VM test failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "traceback": str(e.__traceback__) if hasattr(e, "__traceback__") else None,
        }
