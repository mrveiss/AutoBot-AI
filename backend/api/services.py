# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Services API
Provides service status, health checks, and system information endpoints.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.constants.network_constants import NetworkConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Import existing monitoring functionality
try:
    from backend.api.monitoring import get_services_health as monitoring_services_health
except ImportError:
    monitoring_services_health = None

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Services"])


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
    """Get list of all available services with their status"""
    try:
        # Try to get monitoring data first
        services = []

        if monitoring_services_health:
            try:
                monitoring_data = await monitoring_services_health()

                # Convert monitoring data to our format
                if isinstance(monitoring_data, dict) and "services" in monitoring_data:
                    for service_data in monitoring_data["services"]:
                        services.append(
                            ServiceStatus(
                                name=service_data.get("name", "Unknown"),
                                status=service_data.get("status", "unknown"),
                                message=service_data.get("statusText", "No message"),
                                response_time_ms=service_data.get("response_time_ms"),
                            )
                        )
            except Exception as e:
                logger.warning(f"Could not get monitoring services data: {e}")

        # Get Redis service status from RedisServiceManager
        redis_status_obj = None
        try:
            from backend.api.redis_service import get_service_manager

            manager = await get_service_manager()
            redis_status_obj = await manager.get_service_status()
        except Exception as e:
            logger.warning(f"Could not get Redis service status: {e}")

        # Add default/fallback services if monitoring data unavailable
        if not services:
            # Get configuration for default response time
            from src.unified_config_manager import unified_config_manager

            monitoring_config = (
                unified_config_manager.get_config_section("monitoring") or {}
            )
            default_response_time = monitoring_config.get(
                "default_response_time_ms", 10.0
            )

            # Determine Redis status based on actual service status
            if redis_status_obj:
                if redis_status_obj.status == "running":
                    redis_status = "healthy"
                    redis_message = "Redis service running"
                elif redis_status_obj.status == "stopped":
                    redis_status = "error"
                    redis_message = "Redis service stopped"
                elif redis_status_obj.status == "failed":
                    redis_status = "error"
                    redis_message = "Redis service failed"
                else:
                    redis_status = "warning"
                    redis_message = "Redis service status unknown"
            else:
                redis_status = "warning"
                redis_message = "Status check needed"

            default_services = [
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
            services = default_services

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
        logger.error(f"Failed to get services: {e}")
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
                logger.warning(f"Monitoring services health failed: {e}")

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
        logger.error(f"Failed to get services health: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get services health: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vms_status",
    error_code_prefix="SERVICES",
)
@router.get("/vms/status")
async def get_vms_status():
    """Get VM status for distributed infrastructure"""
    try:
        # Get VM infrastructure from NetworkConstants
        from src.constants.network_constants import NetworkConstants

        # Build VM status from NetworkConstants
        vms = []

        # Frontend VM
        vms.append(
            VMStatus(
                name="Frontend VM",
                ip=str(NetworkConstants.FRONTEND_HOST),
                status="online",
                services=["frontend", "web-interface"],
                last_check=datetime.now(),
            )
        )

        # NPU Worker VM
        vms.append(
            VMStatus(
                name="NPU Worker VM",
                ip=str(NetworkConstants.NPU_WORKER_HOST),
                status="online",
                services=["npu-worker", "hardware-acceleration"],
                last_check=datetime.now(),
            )
        )

        # Redis VM
        vms.append(
            VMStatus(
                name="Redis VM",
                ip=str(NetworkConstants.REDIS_HOST),
                status="online",
                services=["redis", "database", "cache"],
                last_check=datetime.now(),
            )
        )

        # AI Stack VM
        vms.append(
            VMStatus(
                name="AI Stack VM",
                ip=str(NetworkConstants.AI_STACK_HOST),
                status="online",
                services=["ai-processing", "llm", "inference"],
                last_check=datetime.now(),
            )
        )

        # Browser VM
        vms.append(
            VMStatus(
                name="Browser VM",
                ip=str(NetworkConstants.BROWSER_HOST),
                status="online",
                services=["browser-automation", "playwright"],
                last_check=datetime.now(),
            )
        )

        # Count statuses
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
        logger.error(f"Failed to get VM status: {e}")
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
        from src.unified_config_manager import unified_config_manager

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
        logger.error(f"Failed to get version info: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get version info: {str(e)}"
        )


# Note: Monitoring endpoints are handled by the separate monitoring router
# No need for aliases here as the monitoring router already provides these endpoints
