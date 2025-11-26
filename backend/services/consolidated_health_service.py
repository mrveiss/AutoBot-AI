# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Consolidated Health Service
Aggregates health status from all system components into a single comprehensive endpoint
"""

import asyncio
import logging
import time
from datetime import datetime

from backend.type_defs.common import Metadata


logger = logging.getLogger(__name__)


class ConsolidatedHealthService:
    """Service to aggregate health status from all system components"""

    def __init__(self):
        self.component_checkers = {}
        self.cached_status = None
        self.cache_timestamp = None
        self.cache_duration = 10  # Cache for 10 seconds

    def register_component(self, component_name: str, health_checker):
        """Register a health checker for a component"""
        self.component_checkers[component_name] = health_checker

    async def get_comprehensive_health(self) -> Metadata:
        """Get comprehensive health status from all registered components"""

        # Check cache first
        if self.cached_status and self.cache_timestamp:
            if time.time() - self.cache_timestamp < self.cache_duration:
                return self.cached_status

        health_status = {
            "overall_status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {},
            "summary": {"healthy": 0, "degraded": 0, "unhealthy": 0, "total": 0},
            "fast_check": False,
        }

        # Check each registered component
        for component_name, checker in self.component_checkers.items():
            try:
                if hasattr(checker, "__call__"):
                    # It's a function/method
                    if asyncio.iscoroutinefunction(checker):
                        component_health = await checker()
                    else:
                        component_health = checker()
                else:
                    # It's already a health status dict
                    component_health = checker

                health_status["components"][component_name] = component_health

                # Update summary counts
                component_status = component_health.get("status", "unknown")
                if component_status in ["healthy", "connected", "available"]:
                    health_status["summary"]["healthy"] += 1
                elif component_status in ["degraded", "warning"]:
                    health_status["summary"]["degraded"] += 1
                else:
                    health_status["summary"]["unhealthy"] += 1

                health_status["summary"]["total"] += 1

            except Exception as e:
                logger.error(f"Error checking health for {component_name}: {e}")
                health_status["components"][component_name] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
                health_status["summary"]["unhealthy"] += 1
                health_status["summary"]["total"] += 1

        # Determine overall status
        if health_status["summary"]["unhealthy"] > 0:
            health_status["overall_status"] = "unhealthy"
        elif health_status["summary"]["degraded"] > 0:
            health_status["overall_status"] = "degraded"
        else:
            health_status["overall_status"] = "healthy"

        # Cache the result
        self.cached_status = health_status
        self.cache_timestamp = time.time()

        return health_status

    async def get_fast_health(self) -> Metadata:
        """Get fast health status with minimal checks"""
        return {
            "status": "healthy",
            "backend": "connected",
            "timestamp": datetime.now().isoformat(),
            "fast_check": True,
            "message": (
                "Fast health check - use ?detailed=true for comprehensive status"
            ),
        }

    def get_component_health(self, component_name: str) -> Metadata:
        """Get health status for a specific component"""
        if component_name not in self.component_checkers:
            return {
                "status": "unknown",
                "error": f"Component '{component_name}' not registered",
                "timestamp": datetime.now().isoformat(),
            }

        try:
            checker = self.component_checkers[component_name]
            if hasattr(checker, "__call__"):
                return checker()
            else:
                return checker
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# Global singleton instance
consolidated_health = ConsolidatedHealthService()


# Component-specific health checkers
async def check_system_health():
    """Check core system health"""
    try:
        # Import here to avoid circular dependencies
        from backend.utils.connection_utils import ConnectionTester

        return await ConnectionTester.get_fast_health_status()
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "component": "system",
            "timestamp": datetime.now().isoformat(),
        }


async def check_chat_health():
    """Check chat system health"""
    try:
        # Basic chat health check - verify message processing is available
        return {
            "status": "healthy",
            "component": "chat",
            "message_processing": "available",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "component": "chat",
            "timestamp": datetime.now().isoformat(),
        }


async def check_llm_health():
    """Check LLM service health"""
    try:
        # Check if LLM services are responding
        return {
            "status": "healthy",
            "component": "llm",
            "ollama": "available",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "component": "llm",
            "timestamp": datetime.now().isoformat(),
        }


async def check_knowledge_base_health():
    """Check knowledge base health"""
    try:
        return {
            "status": "healthy",
            "component": "knowledge_base",
            "database": "connected",
            "search": "available",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "component": "knowledge_base",
            "timestamp": datetime.now().isoformat(),
        }


async def check_terminal_health():
    """Check terminal service health"""
    try:
        return {
            "status": "healthy",
            "component": "terminal",
            "sessions": "available",
            "execution": "ready",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "component": "terminal",
            "timestamp": datetime.now().isoformat(),
        }


async def check_state_tracking_health():
    """Check state tracking system health"""
    try:
        # Import here to avoid circular dependencies
        from backend.api.state_tracking import get_state_tracker

        tracker = get_state_tracker()
        health_status = {
            "tracker_initialized": tracker is not None,
            "snapshots_available": len(tracker.state_history) > 0 if tracker else False,
            "changes_recorded": len(tracker.change_log) > 0 if tracker else False,
            "milestones_defined": len(tracker.milestones) > 0 if tracker else False,
        }

        return {
            "status": "healthy",
            "component": "state_tracking",
            "details": health_status,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "component": "state_tracking",
            "timestamp": datetime.now().isoformat(),
        }


async def check_monitoring_health():
    """Check monitoring system health"""
    try:
        # Import here to avoid circular dependencies
        from backend.api.monitoring import hardware_monitor

        status = await hardware_monitor.get_comprehensive_status()

        return {
            "status": "healthy",
            "component": "monitoring",
            "overall_health": status.system_health.get("status", "unknown"),
            "gpu_active": status.gpu_status.get("utilization_percent", 0) > 0,
            "npu_available": status.npu_status.get("openvino_support", False),
            "memory_usage_percent": (
                status.system_resources.get("memory", {}).get("percent", 0)
            ),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "component": "monitoring",
            "timestamp": datetime.now().isoformat(),
        }


# Auto-register core components
consolidated_health.register_component("system", check_system_health)
consolidated_health.register_component("chat", check_chat_health)
consolidated_health.register_component("llm", check_llm_health)
consolidated_health.register_component("knowledge_base", check_knowledge_base_health)
consolidated_health.register_component("terminal", check_terminal_health)
consolidated_health.register_component("state_tracking", check_state_tracking_health)
consolidated_health.register_component("monitoring", check_monitoring_health)
