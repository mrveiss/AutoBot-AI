"""
Service Monitoring API
Comprehensive monitoring of all AutoBot services
"""
import asyncio
import logging
import os
import subprocess
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

import docker
import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Import unified configuration system - NO HARDCODED VALUES
from src.config_helper import cfg

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


class ServiceMonitor:
    """Monitors all AutoBot services"""
    
    def __init__(self):
        self.docker_client = None
        self.redis_client = None
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize monitoring clients"""
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Could not initialize Docker client: {e}")
        
        try:
            self.redis_client = redis.Redis(
                host=cfg.get_host('redis'),
                port=cfg.get_port('redis'),
                password=cfg.get('redis.password'),
                decode_responses=True,
                socket_timeout=cfg.get('redis.connection.socket_timeout', 2)
            )
        except Exception as e:
            logger.warning(f"Could not initialize Redis client: {e}")
    
    async def check_backend_api(self) -> ServiceStatus:
        """Check backend API health"""
        try:
            import aiohttp
            start_time = time.time()
            
            timeout = aiohttp.ClientTimeout(
                total=cfg.get_timeout('http', 'standard'), 
                connect=cfg.get_timeout('tcp', 'connect')
            )
            async with aiohttp.ClientSession(timeout=timeout) as session:
                backend_url = cfg.get_service_url('backend', '/api/health')
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
                            details=data
                        )
                    else:
                        return ServiceStatus(
                            name="Backend API",
                            status="warning",
                            message=f"HTTP {response.status}",
                            response_time=response_time,
                            last_check=datetime.now(),
                            icon="fas fa-server",
                            category="core"
                        )
        except Exception as e:
            return ServiceStatus(
                name="Backend API",
                status="error",
                message=str(e)[:100],
                last_check=datetime.now(),
                icon="fas fa-server",
                category="core"
            )
    
    def check_redis(self) -> ServiceStatus:
        """Check Redis database"""
        try:
            start_time = time.time()
            self.redis_client.ping()
            response_time = int((time.time() - start_time) * 1000)
            
            info = self.redis_client.info()
            memory_used = info.get('used_memory_human', 'Unknown')
            connected_clients = info.get('connected_clients', 0)
            
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
                    "redis_version": info.get('redis_version', 'unknown')
                }
            )
        except redis.ConnectionError:
            return ServiceStatus(
                name="Redis Database",
                status="error",
                message="Connection failed",
                last_check=datetime.now(),
                icon="fas fa-database",
                category="database"
            )
        except Exception as e:
            return ServiceStatus(
                name="Redis Database",
                status="warning",
                message=str(e)[:100],
                last_check=datetime.now(),
                icon="fas fa-database",
                category="database"
            )
    
    def check_docker_services(self) -> List[ServiceStatus]:
        """Check Docker container services"""
        services = []
        
        if not self.docker_client:
            return [ServiceStatus(
                name="Docker",
                status="error",
                message="Docker client unavailable",
                last_check=datetime.now(),
                icon="fas fa-whale",
                category="infrastructure"
            )]
        
        try:
            # Define expected containers
            expected_containers = {
                'autobot-frontend': {'name': 'Frontend', 'icon': 'fas fa-globe', 'category': 'web'},
                'autobot-browser': {'name': 'Browser Service', 'icon': 'fas fa-chrome', 'category': 'automation'},
                'autobot-redis': {'name': 'Redis Stack', 'icon': 'fas fa-database', 'category': 'database'},
                'autobot-ai-stack': {'name': 'AI Stack', 'icon': 'fas fa-brain', 'category': 'ai'},
                'autobot-npu-worker': {'name': 'NPU Worker', 'icon': 'fas fa-microchip', 'category': 'ai'},
                'autobot-seq': {'name': 'Seq Logging', 'icon': 'fas fa-file-alt', 'category': 'monitoring'}
            }
            
            # Get running containers
            containers = self.docker_client.containers.list(all=True)
            container_status = {c.name: c for c in containers if c.name in expected_containers}
            
            for container_name, config in expected_containers.items():
                if container_name in container_status:
                    container = container_status[container_name]
                    status_map = {
                        'running': 'online',
                        'exited': 'offline',
                        'restarting': 'warning',
                        'paused': 'warning'
                    }
                    
                    status = status_map.get(container.status, 'warning')
                    message = f"Status: {container.status}"
                    
                    # Add health info if available
                    if hasattr(container.attrs.get('State', {}), 'Health'):
                        health = container.attrs['State'].get('Health', {})
                        if health.get('Status'):
                            message += f", Health: {health['Status']}"
                    
                    services.append(ServiceStatus(
                        name=config['name'],
                        status=status,
                        message=message,
                        last_check=datetime.now(),
                        icon=config['icon'],
                        category=config['category'],
                        details={
                            'container_name': container_name,
                            'status': container.status,
                            'image': container.image.tags[0] if container.image.tags else 'unknown'
                        }
                    ))
                else:
                    services.append(ServiceStatus(
                        name=config['name'],
                        status="offline",
                        message="Container not found",
                        last_check=datetime.now(),
                        icon=config['icon'],
                        category=config['category']
                    ))
                    
        except Exception as e:
            services.append(ServiceStatus(
                name="Docker Services",
                status="error",
                message=f"Docker check failed: {str(e)[:50]}",
                last_check=datetime.now(),
                icon="fas fa-whale",
                category="infrastructure"
            ))
        
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
                    total=cfg.get_timeout('http', 'long'), 
                    connect=cfg.get_timeout('tcp', 'connect')
                )
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    llm_url = cfg.get_service_url('backend', '/api/llm/status/comprehensive')
                    async with session.get(llm_url) as response:
                        response_time = int((time.time() - start_time) * 1000)
                        
                        if response.status == 200:
                            data = await response.json()
                            
                            services.append(ServiceStatus(
                                name="LLM Manager",
                                status="online",
                                message=f"Response: {response_time}ms",
                                response_time=response_time,
                                last_check=datetime.now(),
                                icon="fas fa-brain",
                                category="ai",
                                details=data
                            ))
                        else:
                            services.append(ServiceStatus(
                                name="LLM Manager",
                                status="warning",
                                message=f"HTTP {response.status}",
                                last_check=datetime.now(),
                                icon="fas fa-brain",
                                category="ai"
                            ))
            except Exception as e:
                services.append(ServiceStatus(
                    name="LLM Manager",
                    status="error",
                    message=str(e)[:50],
                    last_check=datetime.now(),
                    icon="fas fa-brain",
                    category="ai"
                ))
            
        except ImportError:
            services.append(ServiceStatus(
                name="LLM Services",
                status="warning",
                message="HTTP client unavailable",
                last_check=datetime.now(),
                icon="fas fa-brain",
                category="ai"
            ))
        
        return services
    
    async def check_knowledge_base(self) -> ServiceStatus:
        """Check knowledge base status"""
        try:
            import aiohttp
            start_time = time.time()
            
            # Use configuration system for knowledge base URL
            kb_url = cfg.get_service_url('backend', '/api/knowledge_base/stats')
            
            timeout = aiohttp.ClientTimeout(
                total=cfg.get_timeout('knowledge_base', 'search'), 
                connect=cfg.get_timeout('tcp', 'connect')
            )
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(kb_url) as response:
                    response_time = int((time.time() - start_time) * 1000)
                    
                    if response.status == 200:
                        data = await response.json()
                        total_docs = data.get('total_documents', 0)
                        
                        return ServiceStatus(
                            name="Knowledge Base",
                            status="online",
                            message=f"{total_docs} documents indexed",
                            response_time=response_time,
                            last_check=datetime.now(),
                            icon="fas fa-database",
                            category="knowledge",
                            details=data
                        )
                    else:
                        return ServiceStatus(
                            name="Knowledge Base",
                            status="warning",
                            message=f"HTTP {response.status}",
                            last_check=datetime.now(),
                            icon="fas fa-database",
                            category="knowledge"
                        )
        except Exception as e:
            return ServiceStatus(
                name="Knowledge Base",
                status="error",
                message=str(e)[:50],
                last_check=datetime.now(),
                icon="fas fa-database",
                category="knowledge"
            )
    
    def check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage"""
        try:
            import psutil
            
            return {
                'cpu_percent': psutil.cpu_percent(interval=0),  # Non-blocking
                'memory': psutil.virtual_memory()._asdict(),
                'disk': psutil.disk_usage('/')._asdict(),
                'network': psutil.net_io_counters()._asdict(),
                'load_avg': list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else None
            }
        except ImportError:
            # Fallback using system commands
            try:
                # Get CPU usage
                cpu_cmd = "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'"
                cpu_result = subprocess.run(cpu_cmd, shell=True, capture_output=True, text=True, timeout=5)
                cpu_percent = float(cpu_result.stdout.strip()) if cpu_result.stdout.strip() else 0
                
                # Get memory usage
                mem_cmd = "free | grep Mem | awk '{print ($3/$2) * 100.0}'"
                mem_result = subprocess.run(mem_cmd, shell=True, capture_output=True, text=True, timeout=5)
                mem_percent = float(mem_result.stdout.strip()) if mem_result.stdout.strip() else 0
                
                return {
                    'cpu_percent': cpu_percent,
                    'memory_percent': mem_percent,
                    'note': 'Limited system info available'
                }
            except Exception:
                return {'error': 'System resource monitoring unavailable'}
    
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
        docker_services = self.check_docker_services()
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
        all_services.extend(docker_services)
        all_services.extend(llm_services)
        
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
            'overall_status': overall_status,
            'check_duration_ms': total_time,
            'services': [s.dict() for s in all_services],
            'system_resources': system_resources,
            'categories': {
                'core': [s for s in all_services if s.category == 'core'],
                'database': [s for s in all_services if s.category == 'database'], 
                'web': [s for s in all_services if s.category == 'web'],
                'ai': [s for s in all_services if s.category == 'ai'],
                'automation': [s for s in all_services if s.category == 'automation'],
                'monitoring': [s for s in all_services if s.category == 'monitoring'],
                'infrastructure': [s for s in all_services if s.category == 'infrastructure'],
                'knowledge': [s for s in all_services if s.category == 'knowledge']
            },
            'summary': {
                'total_services': len(all_services),
                'online': len([s for s in all_services if s.status == 'online']),
                'warning': len([s for s in all_services if s.status == 'warning']),
                'error': len([s for s in all_services if s.status == 'error']),
                'offline': len([s for s in all_services if s.status == 'offline'])
            }
        }


# Global monitor instance - initialized lazily
monitor = None

def get_monitor():
    global monitor
    if monitor is None:
        monitor = ServiceMonitor()
    return monitor


@router.get("/services/status")
async def get_service_status():
    """Get comprehensive service status for dashboard"""
    try:
        return await get_monitor().get_all_services()
    except Exception as e:
        logger.error(f"Service monitoring failed: {e}")
        raise HTTPException(status_code=500, detail=f"Service monitoring error: {str(e)}")


@router.get("/services/ping")
async def ping():
    """Ultra simple ping endpoint"""
    return {"ping": "pong", "timestamp": datetime.now().isoformat()}

@router.get("/services/health")
async def get_service_health():
    """Get ultra-lightweight health check - just return that backend is responding"""
    try:
        # Backend is healthy if we're responding
        # Skip Redis and other checks for speed
        return {
            'status': 'online',
            'healthy': 1,
            'total': 1,
            'warnings': 0,
            'errors': 0
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'error',
            'message': str(e),
            'healthy': 0,
            'total': 1,
            'warnings': 0,
            'errors': 1
        }


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
            "percent": memory.percent
        }
        
        # Disk information
        disk = psutil.disk_usage('/')
        disk_info = {
            "total": round(disk.total / (1024**3), 2),  # GB
            "used": round(disk.used / (1024**3), 2),  # GB
            "free": round(disk.free / (1024**3), 2),  # GB
            "percent": round((disk.used / disk.total) * 100, 2)
        }
        
        # Network information (optional)
        try:
            net_io = psutil.net_io_counters()
            network_info = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv
            }
        except Exception:
            network_info = {"error": "Network info not available"}
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cpu": {
                "usage_percent": cpu_percent,
                "core_count": cpu_count
            },
            "memory": memory_info,
            "disk": disk_info,
            "network": network_info,
            "status": "ok"
        }
    except ImportError:
        return {
            "error": "psutil not available",
            "message": "System resource monitoring requires psutil package",
            "status": "unavailable"
        }
    except Exception as e:
        logger.error(f"Failed to get system resources: {e}")
        return {
            "error": str(e),
            "status": "error"
        }


@router.get("/services")
async def get_all_services():
    """Get status of all AutoBot services"""
    try:
        # Get distributed service URLs from environment
        import os
        redis_host = os.environ.get('REDIS_HOST', '172.16.168.23')
        redis_port = os.environ.get('REDIS_PORT', '6379')
        
        services = {
            "backend": {"status": "online", "url": "http://localhost:8001", "health": "✅"},
            "redis": {"status": "checking", "url": f"redis://{redis_host}:{redis_port}", "health": "⏳"},
            "ollama": {"status": "checking", "url": "http://localhost:11434", "health": "⏳"},
            "frontend": {"status": "checking", "url": "http://localhost:5173", "health": "⏳"}
        }
        
        # Quick Redis check
        try:
            import redis
            r = redis.Redis(host=redis_host, port=int(redis_port), decode_responses=True, socket_timeout=2)
            r.ping()
            services["redis"]["status"] = "online"
            services["redis"]["health"] = "✅"
        except Exception:
            services["redis"]["status"] = "offline"
            services["redis"]["health"] = "❌"
        
        # Quick Ollama check
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                async with session.get('http://localhost:11434/api/version') as response:
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
            "online_count": sum(1 for s in services.values() if s["status"] == "online"),
            "status": "ok"
        }
    except Exception as e:
        logger.error(f"Failed to get services status: {e}")
        return {
            "error": str(e),
            "status": "error"
        }


@router.get("/health")
async def health_redirect():
    """Redirect common /health requests to correct /services/health endpoint"""
    return {
        'error': 'Endpoint moved',
        'message': 'Please use /api/monitoring/services/health instead',
        'correct_endpoint': '/api/monitoring/services/health',
        'status': 'redirect'
    }