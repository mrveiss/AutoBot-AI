#!/usr/bin/env python3
"""
Network Constants for AutoBot
=============================

Centralized network configuration constants to eliminate hardcoded URLs and IP addresses
throughout the codebase. This addresses the 73+ duplicate IP/URL pattern identified
in the code duplication analysis.

Usage:
    from src.constants.network_constants import NetworkConstants, ServiceURLs

    # Use VM IP addresses
    redis_url = f"redis://{NetworkConstants.REDIS_VM_IP}:6379"

    # Use service URLs
    backend_url = ServiceURLs.BACKEND_API
"""

import os
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class NetworkConstants:
    """Core network constants for AutoBot distributed infrastructure"""

    # Main machine (WSL)
    MAIN_MACHINE_IP: str = "172.16.168.20"

    # VM Infrastructure IPs
    FRONTEND_VM_IP: str = "172.16.168.21"
    NPU_WORKER_VM_IP: str = "172.16.168.22"
    REDIS_VM_IP: str = "172.16.168.23"
    AI_STACK_VM_IP: str = "172.16.168.24"
    BROWSER_VM_IP: str = "172.16.168.25"

    # Local/Localhost addresses
    LOCALHOST_IP: str = "127.0.0.1"
    LOCALHOST_NAME: str = "localhost"

    # Standard ports
    BACKEND_PORT: int = 8001
    FRONTEND_PORT: int = 5173
    REDIS_PORT: int = 6379
    OLLAMA_PORT: int = 11434
    VNC_PORT: int = 6080
    BROWSER_SERVICE_PORT: int = 3000
    AI_STACK_PORT: int = 8080
    NPU_WORKER_PORT: int = 8081

    # Development ports
    DEV_FRONTEND_PORT: int = 5173
    DEV_BACKEND_PORT: int = 8001


@dataclass(frozen=True)
class ServiceURLs:
    """Pre-built service URLs for common AutoBot services"""

    # Backend API URLs
    BACKEND_API: str = (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
    )
    BACKEND_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.BACKEND_PORT}"
    )

    # Frontend URLs
    FRONTEND_VM: str = (
        f"http://{NetworkConstants.FRONTEND_VM_IP}:{NetworkConstants.FRONTEND_PORT}"
    )
    FRONTEND_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.FRONTEND_PORT}"
    )

    # Redis URLs
    REDIS_VM: str = (
        f"redis://{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.REDIS_PORT}"
    )
    REDIS_LOCAL: str = (
        f"redis://{NetworkConstants.LOCALHOST_IP}:{NetworkConstants.REDIS_PORT}"
    )

    # Ollama LLM URLs
    OLLAMA_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.OLLAMA_PORT}"
    )
    OLLAMA_MAIN: str = (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.OLLAMA_PORT}"
    )

    # VNC Desktop URLs
    VNC_DESKTOP: str = (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.VNC_PORT}/vnc.html"
    )
    VNC_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.VNC_PORT}/vnc.html"
    )

    # Browser automation service
    BROWSER_SERVICE: str = (
        f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}"
    )

    # AI Stack service
    AI_STACK_SERVICE: str = (
        f"http://{NetworkConstants.AI_STACK_VM_IP}:{NetworkConstants.AI_STACK_PORT}"
    )

    # NPU Worker service
    NPU_WORKER_SERVICE: str = (
        f"http://{NetworkConstants.NPU_WORKER_VM_IP}:{NetworkConstants.NPU_WORKER_PORT}"
    )


class NetworkConfig:
    """
    Dynamic network configuration based on environment.
    Provides context-aware URL generation.
    """

    def __init__(self):
        self._deployment_mode = os.getenv("AUTOBOT_DEPLOYMENT_MODE", "distributed")
        self._is_development = os.getenv("AUTOBOT_ENV", "production") == "development"

    @property
    def backend_url(self) -> str:
        """Get backend URL based on deployment context"""
        if self._deployment_mode == "local":
            return ServiceURLs.BACKEND_LOCAL
        return ServiceURLs.BACKEND_API

    @property
    def frontend_url(self) -> str:
        """Get frontend URL based on deployment context"""
        if self._deployment_mode == "local":
            return ServiceURLs.FRONTEND_LOCAL
        return ServiceURLs.FRONTEND_VM

    @property
    def redis_url(self) -> str:
        """Get Redis URL based on deployment context"""
        if self._deployment_mode == "local":
            return ServiceURLs.REDIS_LOCAL
        return ServiceURLs.REDIS_VM

    @property
    def ollama_url(self) -> str:
        """Get Ollama URL based on deployment context"""
        return ServiceURLs.OLLAMA_LOCAL  # Always local for now

    def get_service_url(self, service_name: str) -> Optional[str]:
        """
        Get service URL by name.

        Args:
            service_name: Name of the service (backend, frontend, redis, etc.)

        Returns:
            Service URL or None if not found
        """
        service_map = {
            "backend": self.backend_url,
            "frontend": self.frontend_url,
            "redis": self.redis_url,
            "ollama": self.ollama_url,
            "browser": ServiceURLs.BROWSER_SERVICE,
            "ai_stack": ServiceURLs.AI_STACK_SERVICE,
            "npu_worker": ServiceURLs.NPU_WORKER_SERVICE,
            "vnc": ServiceURLs.VNC_DESKTOP,
        }
        return service_map.get(service_name)

    def get_vm_ip(self, vm_name: str) -> Optional[str]:
        """
        Get VM IP address by name.

        Args:
            vm_name: Name of the VM (frontend, redis, ai_stack, etc.)

        Returns:
            IP address or None if not found
        """
        vm_map = {
            "main": NetworkConstants.MAIN_MACHINE_IP,
            "frontend": NetworkConstants.FRONTEND_VM_IP,
            "npu_worker": NetworkConstants.NPU_WORKER_VM_IP,
            "redis": NetworkConstants.REDIS_VM_IP,
            "ai_stack": NetworkConstants.AI_STACK_VM_IP,
            "browser": NetworkConstants.BROWSER_VM_IP,
        }
        return vm_map.get(vm_name)


# Global network configuration instance
_network_config = NetworkConfig()


def get_network_config() -> NetworkConfig:
    """Get the global network configuration instance"""
    return _network_config


class DatabaseConstants:
    """Redis database assignments to eliminate hardcoded database numbers"""

    # Core databases
    MAIN_DB = 0
    KNOWLEDGE_DB = 1
    CACHE_DB = 2
    VECTORS_DB = 8

    # Specialized databases
    SESSIONS_DB = 3
    METRICS_DB = 4
    LOGS_DB = 5
    CONFIG_DB = 6
    WORKFLOWS_DB = 7
    TEMP_DB = 9
    MONITORING_DB = 10
    RATE_LIMITING_DB = 11

    @classmethod
    def get_db_description(cls, db_number: int) -> str:
        """Get description for database number"""
        descriptions = {
            cls.MAIN_DB: "Main application data",
            cls.KNOWLEDGE_DB: "Knowledge base and documents",
            cls.CACHE_DB: "Application cache",
            cls.SESSIONS_DB: "User sessions",
            cls.METRICS_DB: "Performance metrics",
            cls.LOGS_DB: "Application logs",
            cls.CONFIG_DB: "Configuration data",
            cls.WORKFLOWS_DB: "Workflow definitions",
            cls.VECTORS_DB: "Vector embeddings",
            cls.TEMP_DB: "Temporary data",
            cls.MONITORING_DB: "System monitoring",
            cls.RATE_LIMITING_DB: "Rate limiting data",
        }
        return descriptions.get(db_number, f"Database {db_number}")


# Legacy compatibility - keep these for backward compatibility during refactoring
BACKEND_URL = ServiceURLs.BACKEND_API
FRONTEND_URL = ServiceURLs.FRONTEND_VM
REDIS_HOST = NetworkConstants.REDIS_VM_IP
REDIS_VM_IP = NetworkConstants.REDIS_VM_IP
MAIN_MACHINE_IP = NetworkConstants.MAIN_MACHINE_IP
LOCALHOST_IP = NetworkConstants.LOCALHOST_IP
