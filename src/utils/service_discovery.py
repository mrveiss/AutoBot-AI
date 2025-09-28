#!/usr/bin/env python3
"""
Service Discovery System for AutoBot Distributed Architecture
Provides dynamic service resolution and health monitoring across 6 VMs
"""

import asyncio
import aiohttp
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

from src.constants.network_constants import NetworkConstants, ServiceURLs

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    STARTING = "starting"


@dataclass
class ServiceEndpoint:
    """Represents a service endpoint with discovery and health information"""
    name: str
    host: str
    port: int
    protocol: str = "http"
    health_endpoint: str = "/health"
    required: bool = True
    timeout: float = 5.0
    retry_count: int = 3
    
    # Health status tracking
    status: ServiceStatus = ServiceStatus.UNKNOWN
    last_check: Optional[datetime] = None
    last_healthy: Optional[datetime] = None
    consecutive_failures: int = 0
    response_time: Optional[float] = None
    error_message: Optional[str] = None
    
    # Service metadata
    version: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    
    @property
    def url(self) -> str:
        """Get the complete service URL"""
        return f"{self.protocol}://{self.host}:{self.port}"
    
    @property
    def health_url(self) -> str:
        """Get the complete health check URL"""
        return f"{self.url}{self.health_endpoint}"
    
    @property
    def is_available(self) -> bool:
        """Check if service is currently available"""
        return self.status in [ServiceStatus.HEALTHY, ServiceStatus.DEGRADED]


class ServiceDiscovery:
    """
    Centralized service discovery and health monitoring system
    Eliminates hardcoded IP addresses and provides dynamic service resolution
    """
    
    def __init__(self, config_file: Optional[str] = None):
        self.services: Dict[str, ServiceEndpoint] = {}
        self.config_file = config_file or "/home/kali/Desktop/AutoBot/config/services.json"
        self.health_check_interval = 30  # seconds
        self.circuit_breaker_threshold = 5  # consecutive failures
        self._health_check_task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Service definitions for AutoBot's 6-VM architecture
        self._init_default_services()
    
    def _init_default_services(self):
        """Initialize default service definitions for AutoBot infrastructure"""
        
        # Get environment-based configuration
        import os
        
        # VM1: Frontend (Web Interface)
        self.services["frontend"] = ServiceEndpoint(
            name="frontend",
            host=os.getenv("AUTOBOT_FRONTEND_HOST", NetworkConstants.FRONTEND_VM_IP),
            port=int(os.getenv("AUTOBOT_FRONTEND_PORT", NetworkConstants.FRONTEND_PORT)),
            protocol="http",
            health_endpoint="/",  # Vue.js app health check
            timeout=10.0,
            required=True
        )

        # VM2: NPU Worker (AI Hardware Acceleration)
        self.services["npu_worker"] = ServiceEndpoint(
            name="npu_worker",
            host=os.getenv("AUTOBOT_NPU_WORKER_HOST", NetworkConstants.NPU_WORKER_VM_IP),
            port=int(os.getenv("AUTOBOT_NPU_WORKER_PORT", NetworkConstants.NPU_WORKER_PORT)),
            protocol="http",
            health_endpoint="/health",
            timeout=15.0,
            required=False  # Optional AI acceleration
        )

        # VM3: Redis (Data Layer)
        self.services["redis"] = ServiceEndpoint(
            name="redis",
            host=os.getenv("AUTOBOT_REDIS_HOST", NetworkConstants.REDIS_VM_IP),
            port=int(os.getenv("AUTOBOT_REDIS_PORT", NetworkConstants.REDIS_PORT)),
            protocol="tcp",  # Redis uses TCP, not HTTP
            health_endpoint="",  # Redis PING command
            timeout=5.0,
            required=True
        )

        # VM4: AI Stack (AI Processing)
        self.services["ai_stack"] = ServiceEndpoint(
            name="ai_stack",
            host=os.getenv("AUTOBOT_AI_STACK_HOST", NetworkConstants.AI_STACK_VM_IP),
            port=int(os.getenv("AUTOBOT_AI_STACK_PORT", NetworkConstants.AI_STACK_PORT)),
            protocol="http",
            health_endpoint="/health",
            timeout=20.0,
            required=False  # Optional AI processing
        )

        # VM5: Browser Service (Playwright Automation)
        self.services["browser_service"] = ServiceEndpoint(
            name="browser_service",
            host=os.getenv("AUTOBOT_BROWSER_SERVICE_HOST", NetworkConstants.BROWSER_VM_IP),
            port=int(os.getenv("AUTOBOT_BROWSER_SERVICE_PORT", NetworkConstants.BROWSER_SERVICE_PORT)),
            protocol="http",
            health_endpoint="/health",
            timeout=10.0,
            required=False  # Optional browser automation
        )

        # Main Machine (WSL): Backend API
        self.services["backend"] = ServiceEndpoint(
            name="backend",
            host=os.getenv("AUTOBOT_BACKEND_HOST", NetworkConstants.MAIN_MACHINE_IP),
            port=int(os.getenv("AUTOBOT_BACKEND_PORT", NetworkConstants.BACKEND_PORT)),
            protocol="http",
            health_endpoint="/api/health",
            timeout=5.0,
            required=True
        )

        # Main Machine (WSL): Ollama LLM
        self.services["ollama"] = ServiceEndpoint(
            name="ollama",
            host=os.getenv("AUTOBOT_OLLAMA_HOST", NetworkConstants.LOCALHOST_IP),
            port=int(os.getenv("AUTOBOT_OLLAMA_PORT", NetworkConstants.OLLAMA_PORT)),
            protocol="http",
            health_endpoint="/api/tags",  # Ollama health check
            timeout=10.0,
            required=True
        )
    
    async def start_health_monitoring(self):
        """Start continuous health monitoring of all services"""
        if self._health_check_task and not self._health_check_task.done():
            return  # Already running
        
        # Create persistent HTTP session
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        )
        
        self._health_check_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Started continuous health monitoring for all services")
    
    async def stop_health_monitoring(self):
        """Stop health monitoring and clean up resources"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        if self._session:
            await self._session.close()
            self._session = None
        
        logger.info("Stopped health monitoring")
    
    async def _health_monitor_loop(self):
        """Continuous health monitoring loop"""
        while True:
            try:
                await self.check_all_services()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}")
                await asyncio.sleep(5)  # Brief pause on error
    
    async def check_all_services(self) -> Dict[str, ServiceStatus]:
        """Check health of all registered services concurrently"""
        tasks = []
        
        for service_name in self.services:
            task = asyncio.create_task(
                self.check_service_health(service_name),
                name=f"health_check_{service_name}"
            )
            tasks.append((service_name, task))
        
        results = {}
        completed_tasks = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
        
        for i, (service_name, _) in enumerate(tasks):
            result = completed_tasks[i]
            if isinstance(result, Exception):
                logger.error(f"Health check failed for {service_name}: {result}")
                self.services[service_name].status = ServiceStatus.UNHEALTHY
                self.services[service_name].error_message = str(result)
                results[service_name] = ServiceStatus.UNHEALTHY
            else:
                results[service_name] = result
        
        return results
    
    async def check_service_health(self, service_name: str) -> ServiceStatus:
        """Check health of a specific service with circuit breaker logic"""
        if service_name not in self.services:
            logger.warning(f"Unknown service: {service_name}")
            return ServiceStatus.UNKNOWN
        
        service = self.services[service_name]
        start_time = time.time()
        
        try:
            # Circuit breaker logic
            if service.consecutive_failures >= self.circuit_breaker_threshold:
                # Service is in circuit breaker mode - reduce check frequency
                if service.last_check:
                    time_since_check = (datetime.now() - service.last_check).seconds
                    if time_since_check < (self.health_check_interval * 2):
                        return service.status  # Skip check, too recent
            
            # Perform health check based on service type
            if service.protocol == "tcp":
                status = await self._check_tcp_service(service)
            else:
                status = await self._check_http_service(service)
            
            # Update service status
            service.status = status
            service.last_check = datetime.now()
            service.response_time = time.time() - start_time
            
            if status == ServiceStatus.HEALTHY:
                service.consecutive_failures = 0
                service.last_healthy = datetime.now()
                service.error_message = None
            else:
                service.consecutive_failures += 1
            
            return status
            
        except Exception as e:
            service.status = ServiceStatus.UNHEALTHY
            service.last_check = datetime.now()
            service.consecutive_failures += 1
            service.error_message = str(e)
            service.response_time = time.time() - start_time
            
            logger.error(f"Health check error for {service_name}: {e}")
            return ServiceStatus.UNHEALTHY
    
    async def _check_http_service(self, service: ServiceEndpoint) -> ServiceStatus:
        """Check HTTP-based service health"""
        if not self._session:
            raise Exception("HTTP session not initialized")
        
        try:
            async with self._session.get(
                service.health_url,
                timeout=aiohttp.ClientTimeout(total=service.timeout)
            ) as response:
                
                # Check response status
                if response.status == 200:
                    # Try to parse response for additional health info
                    try:
                        data = await response.json()
                        if isinstance(data, dict):
                            # Extract service metadata if available
                            service.version = data.get("version")
                            service.capabilities = data.get("capabilities", [])
                            
                            # Check if response indicates degraded state
                            status_field = data.get("status", "healthy").lower()
                            if status_field in ["degraded", "warning"]:
                                return ServiceStatus.DEGRADED
                    except:
                        pass  # Ignore JSON parsing errors for simple endpoints
                    
                    return ServiceStatus.HEALTHY
                
                elif response.status in [503, 502, 504]:
                    return ServiceStatus.DEGRADED  # Temporary issues
                else:
                    return ServiceStatus.UNHEALTHY
                    
        except asyncio.TimeoutError:
            return ServiceStatus.UNHEALTHY
        except aiohttp.ClientError:
            return ServiceStatus.UNHEALTHY
    
    async def _check_tcp_service(self, service: ServiceEndpoint) -> ServiceStatus:
        """Check TCP-based service health (e.g., Redis)"""
        try:
            # For Redis specifically
            if service.name == "redis":
                import redis.asyncio as redis
                client = redis.Redis(
                    host=service.host,
                    port=service.port,
                    socket_timeout=service.timeout,
                    socket_connect_timeout=service.timeout
                )
                
                # Send PING command
                pong = await client.ping()
                await client.close()
                
                return ServiceStatus.HEALTHY if pong else ServiceStatus.UNHEALTHY
            
            else:
                # Generic TCP connection test
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(service.host, service.port),
                    timeout=service.timeout
                )
                writer.close()
                await writer.wait_closed()
                return ServiceStatus.HEALTHY
                
        except Exception:
            return ServiceStatus.UNHEALTHY
    
    def get_service_url(self, service_name: str) -> Optional[str]:
        """Get service URL with automatic failover"""
        if service_name not in self.services:
            return None
        
        service = self.services[service_name]
        
        # Check if service is available
        if not service.is_available and service.required:
            logger.warning(f"Required service {service_name} is not available")
        
        return service.url
    
    def get_healthy_services(self) -> List[str]:
        """Get list of currently healthy services"""
        return [
            name for name, service in self.services.items()
            if service.status == ServiceStatus.HEALTHY
        ]
    
    def get_service_status_summary(self) -> Dict:
        """Get comprehensive status summary of all services"""
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_services": len(self.services),
            "healthy": 0,
            "degraded": 0,
            "unhealthy": 0,
            "unknown": 0,
            "services": {}
        }
        
        for name, service in self.services.items():
            status_str = service.status.value
            summary["services"][name] = {
                "status": status_str,
                "url": service.url,
                "required": service.required,
                "last_check": service.last_check.isoformat() if service.last_check else None,
                "response_time": service.response_time,
                "consecutive_failures": service.consecutive_failures,
                "error": service.error_message
            }
            
            # Update counters
            if service.status == ServiceStatus.HEALTHY:
                summary["healthy"] += 1
            elif service.status == ServiceStatus.DEGRADED:
                summary["degraded"] += 1
            elif service.status == ServiceStatus.UNHEALTHY:
                summary["unhealthy"] += 1
            else:
                summary["unknown"] += 1
        
        return summary
    
    async def wait_for_service(self, service_name: str, timeout: float = 60.0) -> bool:
        """Wait for a service to become healthy with timeout"""
        if service_name not in self.services:
            return False
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = await self.check_service_health(service_name)
            if status == ServiceStatus.HEALTHY:
                return True
            
            await asyncio.sleep(2)  # Check every 2 seconds
        
        return False
    
    async def wait_for_core_services(self, timeout: float = 120.0) -> Tuple[bool, List[str]]:
        """Wait for all required services to become healthy"""
        required_services = [
            name for name, service in self.services.items()
            if service.required
        ]
        
        start_time = time.time()
        ready_services = []
        
        while time.time() - start_time < timeout:
            await self.check_all_services()
            
            ready_services = [
                name for name in required_services
                if self.services[name].status == ServiceStatus.HEALTHY
            ]
            
            if len(ready_services) == len(required_services):
                return True, ready_services
            
            missing = set(required_services) - set(ready_services)
            logger.info(f"Waiting for services: {list(missing)}")
            
            await asyncio.sleep(5)  # Check every 5 seconds
        
        return False, ready_services


# Global service discovery instance
service_discovery = ServiceDiscovery()


# Convenience functions for backward compatibility
async def get_service_url(service_name: str) -> Optional[str]:
    """Get service URL - backward compatible function"""
    return service_discovery.get_service_url(service_name)


async def check_service_health(service_name: str) -> ServiceStatus:
    """Check specific service health - backward compatible function"""
    return await service_discovery.check_service_health(service_name)


async def get_all_service_health() -> Dict[str, ServiceStatus]:
    """Get health status of all services - backward compatible function"""
    return await service_discovery.check_all_services()


# Auto-start health monitoring when module is imported
async def _auto_start_monitoring():
    """Auto-start health monitoring in background"""
    try:
        await service_discovery.start_health_monitoring()
    except Exception as e:
        logger.error(f"Failed to auto-start service discovery: {e}")


# Schedule auto-start (will run when event loop is available)
def _schedule_auto_start():
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_auto_start_monitoring())
    except RuntimeError:
        # No running loop, will start manually later
        pass


_schedule_auto_start()