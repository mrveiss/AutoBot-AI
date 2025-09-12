"""
Distributed Service Discovery - Eliminates DNS Resolution Timeouts

This module provides instant service resolution for the distributed VM architecture
by maintaining a local cache of service endpoints and implementing health-based routing.

ROOT CAUSE FIX: Replaces DNS resolution delays with cached service endpoints
"""

import asyncio
import logging
import time
import aiohttp
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

@dataclass
class ServiceEndpoint:
    """Service endpoint with health status"""
    host: str
    port: int
    protocol: str = "http"
    last_check: float = 0
    is_healthy: bool = False
    response_time: float = 0.0
    
    @property
    def url(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"
    
    def is_stale(self, max_age: float = 30.0) -> bool:
        """Check if health status is stale"""
        return time.time() - self.last_check > max_age

class DistributedServiceDiscovery:
    """
    Service discovery for distributed VM architecture
    
    ELIMINATES DNS TIMEOUTS BY:
    - Maintaining cached service endpoints
    - Async health checking without blocking
    - Instant service resolution
    - Automatic failover to backup endpoints
    """
    
    def __init__(self):
        self.services: Dict[str, ServiceEndpoint] = {}
        self.backup_endpoints: Dict[str, list] = {}
        self._health_check_task = None
        self._initialize_service_registry()
    
    def _initialize_service_registry(self):
        """Initialize service registry with distributed VM endpoints"""
        
        # Primary service endpoints (distributed architecture)
        primary_services = {
            "redis": ServiceEndpoint("172.16.168.23", 6379, "redis"),
            "backend": ServiceEndpoint("172.16.168.20", 8001, "http"),
            "frontend": ServiceEndpoint("172.16.168.21", 5173, "http"),
            "npu_worker": ServiceEndpoint("172.16.168.22", 8081, "http"),
            "ai_stack": ServiceEndpoint("172.16.168.24", 8080, "http"),
            "browser": ServiceEndpoint("172.16.168.25", 3000, "http"),
            "ollama": ServiceEndpoint("127.0.0.1", 11434, "http"),  # Local service
        }
        
        # Backup endpoints for failover
        backup_endpoints = {
            "redis": [
                ServiceEndpoint("127.0.0.1", 6379, "redis"),  # Local Redis fallback
                ServiceEndpoint("172.16.168.20", 6379, "redis"),  # Backend host Redis
            ],
            "backend": [
                ServiceEndpoint("127.0.0.1", 8001, "http"),  # Local backend
            ],
            "ollama": [
                ServiceEndpoint("172.16.168.24", 11434, "http"),  # AI Stack host
                ServiceEndpoint("172.16.168.22", 11434, "http"),  # NPU Worker host
            ]
        }
        
        self.services.update(primary_services)
        self.backup_endpoints.update(backup_endpoints)
        
        logger.info(f"🌐 Service registry initialized with {len(self.services)} services")
    
    async def get_service_endpoint(self, service_name: str) -> Optional[ServiceEndpoint]:
        """
        Get healthy service endpoint instantly (no DNS resolution delays)
        
        ELIMINATES TIMEOUTS BY:
        - Returning cached healthy endpoints immediately
        - No DNS resolution required
        - Automatic failover to backup endpoints
        """
        
        # Check primary endpoint
        if service_name in self.services:
            endpoint = self.services[service_name]
            
            # Return immediately if recently checked and healthy
            if not endpoint.is_stale() and endpoint.is_healthy:
                return endpoint
            
            # Quick async health check (non-blocking)
            if await self._quick_health_check(endpoint):
                return endpoint
        
        # Try backup endpoints if primary failed
        if service_name in self.backup_endpoints:
            for backup in self.backup_endpoints[service_name]:
                if await self._quick_health_check(backup):
                    logger.warning(f"🔄 Using backup endpoint for {service_name}: {backup.url}")
                    return backup
        
        # Return primary even if unhealthy (let caller handle)
        return self.services.get(service_name)
    
    async def _quick_health_check(self, endpoint: ServiceEndpoint) -> bool:
        """
        Non-blocking health check with immediate return
        
        ELIMINATES BLOCKING BY:
        - Using asyncio.timeout with very short duration
        - Returns immediately on success/failure
        - No waiting or retry logic
        """
        try:
            if endpoint.protocol == "redis":
                return await self._check_redis_health(endpoint)
            else:
                return await self._check_http_health(endpoint)
        except Exception as e:
            logger.debug(f"Health check failed for {endpoint.url}: {e}")
            endpoint.is_healthy = False
            endpoint.last_check = time.time()
            return False
    
    async def _check_redis_health(self, endpoint: ServiceEndpoint) -> bool:
        """Quick Redis connection test"""
        try:
            import redis.asyncio as redis
            
            # Immediate connection test (no retries)
            client = redis.Redis(
                host=endpoint.host,
                port=endpoint.port,
                socket_connect_timeout=0.1,  # 100ms max
                socket_timeout=0.1,
                retry_on_timeout=False,
                health_check_interval=0
            )
            
            start_time = time.time()
            await client.ping()
            response_time = time.time() - start_time
            await client.aclose()
            
            endpoint.is_healthy = True
            endpoint.response_time = response_time
            endpoint.last_check = time.time()
            
            return True
            
        except Exception:
            endpoint.is_healthy = False
            endpoint.last_check = time.time()
            return False
    
    async def _check_http_health(self, endpoint: ServiceEndpoint) -> bool:
        """Quick HTTP health check"""
        try:
            timeout = aiohttp.ClientTimeout(total=0.2, connect=0.1)  # 200ms max
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                start_time = time.time()
                
                # Try health endpoint first, then root
                health_urls = [f"{endpoint.url}/health", f"{endpoint.url}/", endpoint.url]
                
                for url in health_urls:
                    try:
                        async with session.get(url) as response:
                            if response.status < 500:  # Accept 2xx, 3xx, 4xx
                                response_time = time.time() - start_time
                                endpoint.is_healthy = True
                                endpoint.response_time = response_time
                                endpoint.last_check = time.time()
                                return True
                    except:
                        continue
                
                endpoint.is_healthy = False
                endpoint.last_check = time.time()
                return False
                
        except Exception:
            endpoint.is_healthy = False
            endpoint.last_check = time.time()
            return False
    
    async def get_redis_connection_params(self) -> Dict:
        """
        Get Redis connection parameters with instant resolution
        
        ELIMINATES DNS TIMEOUT BY:
        - Using cached IP addresses
        - Immediate parameter return
        - Built-in failover logic
        """
        endpoint = await self.get_service_endpoint("redis")
        if not endpoint:
            raise ConnectionError("No Redis endpoint available")
        
        return {
            'host': endpoint.host,
            'port': endpoint.port,
            'decode_responses': True,
            'socket_connect_timeout': 0.1,  # Very short, non-blocking
            'socket_timeout': 0.5,
            'retry_on_timeout': False,
            'health_check_interval': 0,
            'max_connections': 5,
        }
    
    def start_background_health_monitoring(self):
        """Start background health monitoring (optional)"""
        if not self._health_check_task:
            self._health_check_task = asyncio.create_task(self._background_health_monitor())
    
    async def _background_health_monitor(self):
        """Background task to keep service health updated"""
        while True:
            try:
                # Check all services in parallel
                tasks = []
                for service_name, endpoint in self.services.items():
                    if endpoint.is_stale(60.0):  # Check stale services
                        task = asyncio.create_task(self._quick_health_check(endpoint))
                        tasks.append((service_name, task))
                
                if tasks:
                    await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Background health monitoring error: {e}")
                await asyncio.sleep(60)  # Back off on errors

# Global instance for easy access
_service_discovery = None

async def get_service_discovery() -> DistributedServiceDiscovery:
    """Get global service discovery instance"""
    global _service_discovery
    if not _service_discovery:
        _service_discovery = DistributedServiceDiscovery()
        _service_discovery.start_background_health_monitoring()
    return _service_discovery

async def get_service_url(service_name: str) -> str:
    """Quick service URL resolution without DNS delays"""
    discovery = await get_service_discovery()
    endpoint = await discovery.get_service_endpoint(service_name)
    return endpoint.url if endpoint else f"http://localhost:8000"  # Safe fallback