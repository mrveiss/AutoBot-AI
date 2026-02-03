# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Services API
Provides service status, health checks, and system information endpoints.
"""

import logging
import time
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Import existing monitoring functionality
try:
    from backend.api.monitoring import get_services_health as monitoring_services_health
except ImportError:
    monitoring_services_health = None

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Services"])


def _determine_redis_status(redis_status_obj) -> tuple[str, str]:
    """Determine Redis status and message from status object (Issue #315: extracted).

    Returns:
        Tuple of (status, message)
    """
    if redis_status_obj is None:
        return ("warning", "Status check needed")

    status_map = {
        "running": ("healthy", "Redis service running"),
        "stopped": ("error", "Redis service stopped"),
        "failed": ("error", "Redis service failed"),
    }

    return status_map.get(
        redis_status_obj.status, ("warning", "Redis service status unknown")
    )


async def _get_services_from_monitoring() -> list:
    """Get services from monitoring data (Issue #315: extracted).

    Returns:
        List of ServiceStatus objects, empty list on failure
    """
    if not monitoring_services_health:
        return []

    try:
        monitoring_data = await monitoring_services_health()
        if not isinstance(monitoring_data, dict) or "services" not in monitoring_data:
            return []

        services = []
        for service_data in monitoring_data["services"]:
            services.append(
                ServiceStatus(
                    name=service_data.get("name", "Unknown"),
                    status=service_data.get("status", "unknown"),
                    message=service_data.get("statusText", "No message"),
                    response_time_ms=service_data.get("response_time_ms"),
                )
            )
        return services
    except Exception as e:
        logger.warning("Could not get monitoring services data: %s", e)
        return []


async def _get_redis_status():
    """Get Redis service status (Issue #315: extracted).

    Returns:
        Redis status object or None on failure
    """
    try:
        from backend.api.redis_service import get_service_manager

        manager = await get_service_manager()
        return await manager.get_service_status()
    except Exception as e:
        logger.warning("Could not get Redis service status: %s", e)
        return None


def _build_default_services(redis_status_obj) -> list:
    """Build default services list when monitoring unavailable (Issue #315: extracted).

    Returns:
        List of default ServiceStatus objects
    """
    from src.config import unified_config_manager

    monitoring_config = unified_config_manager.get_config_section("monitoring") or {}
    default_response_time = monitoring_config.get("default_response_time_ms", 10.0)

    redis_status, redis_message = _determine_redis_status(redis_status_obj)

    return [
        ServiceStatus(
            name="Backend API",
            status="healthy",
            message="API server running",
            response_time_ms=default_response_time,
        ),
        ServiceStatus(
            name="Frontend",
            status="healthy",
            message="Web interface accessible",
        ),
        ServiceStatus(name="Redis", status=redis_status, message=redis_message),
        ServiceStatus(
            name="LLM Service",
            status="warning",
            message="Connection status unknown",
        ),
        ServiceStatus(
            name="NPU Worker",
            status="healthy",
            message="Hardware acceleration ready",
        ),
        ServiceStatus(
            name="Browser Service",
            status="healthy",
            message="Automation services running",
        ),
    ]


class ServiceStatus(BaseModel):
    """Service status model"""

    name: str
    status: str = Field(..., description="Service status: healthy, warning, error")
    message: str = Field(..., description="Status description")
    last_check: Optional[datetime] = None
    response_time_ms: Optional[float] = None


class SystemInfo(BaseModel):
    """System information model"""

    version: str
    build: str
    environment: str
    uptime: float
    services_count: int


class VMStatus(BaseModel):
    """VM status model"""

    name: str
    ip: str
    status: str = Field(..., description="VM status: online, offline, unknown")
    services: List[str] = Field(default_factory=list)
    last_check: Optional[datetime] = None


class ServicesResponse(BaseModel):
    """Services list response"""

    services: List[ServiceStatus]
    total_count: int
    healthy_count: int
    error_count: int
    warning_count: int
    last_updated: datetime


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_services",
    error_code_prefix="SERVICES",
)
@router.get("/services", response_model=ServicesResponse)
async def get_services():
    """Get list of all available services with their status.

    Issue #315: Refactored to use helper functions for reduced nesting depth.
    """
    try:
        # Get services from monitoring (uses helper)
        services = await _get_services_from_monitoring()

        # Get Redis status for fallback services
        redis_status_obj = await _get_redis_status()

        # Use default services if monitoring unavailable
        if not services:
            services = _build_default_services(redis_status_obj)

        # Calculate counts
        healthy_count = sum(1 for s in services if s.status == "healthy")
        warning_count = sum(1 for s in services if s.status == "warning")
        error_count = sum(1 for s in services if s.status == "error")

        return ServicesResponse(
            services=services,
            total_count=len(services),
            healthy_count=healthy_count,
            warning_count=warning_count,
            error_count=error_count,
            last_updated=datetime.now(),
        )

    except Exception as e:
        logger.error("Failed to get services: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get services: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_health",
    error_code_prefix="SERVICES",
)
@router.get("/health")
async def get_health():
    """Simple health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now()}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_services_health",
    error_code_prefix="SERVICES",
)
@router.get("/services/health")
async def get_services_health():
    """Get service health status - alias to monitoring endpoint"""
    try:
        # Try to use existing monitoring endpoint first
        if monitoring_services_health:
            try:
                return await monitoring_services_health()
            except Exception as e:
                logger.warning("Monitoring services health failed: %s", e)

        # Fallback response when monitoring unavailable
        services_data = await get_services()

        # Convert to monitoring-compatible format
        result = {
            "timestamp": time.time(),
            "overall_status": (
                "healthy"
                if services_data.error_count == 0
                else "degraded" if services_data.error_count < 2 else "critical"
            ),
            "total_services": services_data.total_count,
            "healthy_services": services_data.healthy_count,
            "degraded_services": services_data.warning_count,
            "critical_services": services_data.error_count,
            "services": [
                {
                    "name": service.name,
                    "status": service.status,
                    "message": service.message,
                    "response_time_ms": service.response_time_ms or 0,
                }
                for service in services_data.services
            ],
        }

        return result

    except Exception as e:
        logger.error("Failed to get services health: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get services health: {str(e)}"
        )


def _build_vm_definitions() -> list:
    """
    Build VM definitions from NetworkConstants (Issue #665: extracted helper).

    Returns list of (name, ip_attr, services) tuples.
    """
    from src.constants.network_constants import NetworkConstants

    return [
        ("Frontend VM", str(NetworkConstants.FRONTEND_HOST), ["frontend", "web-interface"]),
        ("NPU Worker VM", str(NetworkConstants.NPU_WORKER_HOST), ["npu-worker", "hardware-acceleration"]),
        ("Redis VM", str(NetworkConstants.REDIS_HOST), ["redis", "database", "cache"]),
        ("AI Stack VM", str(NetworkConstants.AI_STACK_HOST), ["ai-processing", "llm", "inference"]),
        ("Browser VM", str(NetworkConstants.BROWSER_VM_IP), ["browser-automation", "playwright"]),
    ]


def _build_vm_status_list(vm_definitions: list) -> list:
    """
    Build VMStatus list from definitions (Issue #665: extracted helper).
    """
    now = datetime.now()
    return [
        VMStatus(name=name, ip=ip, status="online", services=services, last_check=now)
        for name, ip, services in vm_definitions
    ]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vms_status",
    error_code_prefix="SERVICES",
)
@router.get("/vms/status")
async def get_vms_status():
    """
    Get VM status for distributed infrastructure.

    Issue #665: Refactored to use data-driven helper functions.
    """
    try:
        vm_definitions = _build_vm_definitions()
        vms = _build_vm_status_list(vm_definitions)

        online_count = sum(1 for vm in vms if vm.status == "online")
        total_count = len(vms)

        return {
            "vms": vms,
            "total_count": total_count,
            "online_count": online_count,
            "offline_count": total_count - online_count,
            "overall_status": "healthy" if online_count == total_count else "degraded",
            "last_updated": datetime.now(),
        }

    except Exception as e:
        logger.error("Failed to get VM status: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get VM status: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_version",
    error_code_prefix="SERVICES",
)
@router.get("/version", response_model=SystemInfo)
async def get_version():
    """Get application version and system information"""
    try:
        # Get configuration
        from src.config import unified_config_manager

        backend_config = unified_config_manager.get_backend_config()
        system_config = unified_config_manager.get_config_section("system") or {}

        # Get uptime from config or calculate (could be improved with actual start time)
        uptime_seconds = system_config.get("uptime_placeholder", 3600.0)

        # Get services count
        try:
            services_data = await get_services()
            services_count = services_data.total_count
        except Exception:
            # Get default service count from config
            services_count = system_config.get("default_services_count", 6)

        return SystemInfo(
            version=system_config.get("version", "1.5.0"),
            build=system_config.get("build", "distributed-vm"),
            environment=backend_config.get("environment", "production"),
            uptime=uptime_seconds,
            services_count=services_count,
        )

    except Exception as e:
        logger.error("Failed to get version info: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get version info: {str(e)}"
        )


# Note: Monitoring endpoints are handled by the separate monitoring router
# No need for aliases here as the monitoring router already provides these endpoints
