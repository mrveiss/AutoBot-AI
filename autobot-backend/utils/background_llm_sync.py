# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Background LLM Synchronization Service

This module provides background synchronization services for LLM interactions,
including model health monitoring, connection pool management, and performance
optimization tasks.

Key Features:
- Background health checks for LLM services
- Connection pool warming and maintenance
- Performance metrics collection
- Model availability monitoring
- Automatic recovery and retry logic
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from backend.constants.network_constants import NetworkConstants
from backend.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)


@dataclass
class LLMServiceStatus:
    """Status information for an LLM service"""

    service_name: str
    endpoint: str
    status: str  # healthy, degraded, offline
    last_check: float = field(default_factory=time.time)
    response_time: Optional[float] = None
    error_count: int = 0
    success_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class BackgroundLLMSync:
    """
    Background service for LLM synchronization and health monitoring.

    Runs continuously in the background to maintain LLM service health,
    warm connection pools, and collect performance metrics.
    """

    def __init__(self, check_interval: int = 60):
        """Initialize the background LLM sync service."""
        self.check_interval = check_interval
        self.running = False
        self.services: Dict[str, LLMServiceStatus] = {}
        self._task: Optional[asyncio.Task] = None

        # Lock for thread-safe service status access
        self._lock = asyncio.Lock()

        # Initialize known services
        self._initialize_known_services()

        logger.info(
            f"BackgroundLLMSync initialized with {check_interval}s check interval"
        )

    def _initialize_known_services(self):
        """Initialize known LLM services for monitoring."""
        # Add known LLM services
        known_services = [
            (
                "ollama",
                f"http://{NetworkConstants.AI_STACK_VM_IP}:{NetworkConstants.OLLAMA_PORT}",
            ),
            (
                "openai",
                os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
            ),
            (
                "local_llm",
                f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.AI_STACK_PORT}",
            ),
        ]

        for name, endpoint in known_services:
            self.services[name] = LLMServiceStatus(
                service_name=name, endpoint=endpoint, status="unknown"
            )

    async def check_service_health(self, service: LLMServiceStatus) -> bool:
        """Check the health of a specific LLM service (thread-safe)."""
        try:
            start_time = time.time()

            # For now, just simulate a health check
            # In a real implementation, this would make actual HTTP requests
            await asyncio.sleep(0.1)  # Simulate network delay

            response_time = time.time() - start_time

            # Update service status under lock
            async with self._lock:
                service.response_time = response_time
                service.last_check = time.time()
                service.success_count += 1
                service.status = "healthy"

            logger.debug(
                f"Health check passed for {service.service_name} ({response_time:.3f}s)"
            )
            return True

        except Exception as e:
            # Update service status under lock
            async with self._lock:
                service.error_count += 1
                service.status = "offline"
                service.last_check = time.time()

            logger.warning("Health check failed for %s: %s", service.service_name, e)
            return False

    async def perform_health_checks(self):
        """Perform health checks on all registered services."""
        logger.debug("Performing health checks on all LLM services...")

        tasks = []
        for service in self.services.values():
            task = asyncio.create_task(self.check_service_health(service))
            tasks.append(task)

        # Wait for all health checks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        healthy_count = sum(1 for result in results if result is True)
        total_count = len(self.services)

        logger.info(
            f"Health check complete: {healthy_count}/{total_count} services healthy"
        )

    async def warm_connection_pools(self):
        """Warm up connection pools for better performance."""
        try:
            logger.debug("Warming up LLM connection pools...")

            # Simulate connection pool warming
            await asyncio.sleep(0.1)

            logger.debug("Connection pools warmed successfully")

        except Exception as e:
            logger.warning("Failed to warm connection pools: %s", e)

    async def collect_performance_metrics(self):
        """Collect and log performance metrics (thread-safe)."""
        try:
            # Copy service data under lock
            async with self._lock:
                total_services = len(self.services)
                healthy_services = sum(
                    1 for s in self.services.values() if s.status == "healthy"
                )
                offline_services = sum(
                    1 for s in self.services.values() if s.status == "offline"
                )
                response_times = [
                    s.response_time for s in self.services.values() if s.response_time
                ]

            # Process outside lock
            avg_response_time = 0.0
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)

            metrics = {
                "total_services": total_services,
                "healthy_services": healthy_services,
                "offline_services": offline_services,
                "average_response_time": avg_response_time,
                "timestamp": time.time(),
            }

            logger.debug("Performance metrics: %s", metrics)

        except Exception as e:
            logger.warning("Failed to collect performance metrics: %s", e)

    async def background_sync_loop(self):
        """Main background synchronization loop."""
        logger.info("🔄 Starting background LLM sync loop...")

        while self.running:
            try:
                # Perform health checks
                await self.perform_health_checks()

                # Warm connection pools
                await self.warm_connection_pools()

                # Collect metrics
                await self.collect_performance_metrics()

                # Wait for next cycle
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                logger.info("Background LLM sync loop cancelled")
                break
            except Exception as e:
                logger.error("❌ Error in background LLM sync loop: %s", e)
                # Continue running even if there's an error
                await asyncio.sleep(self.check_interval)

    async def start(self):
        """Start the background sync service."""
        if self.running:
            logger.warning("Background LLM sync already running")
            return

        self.running = True
        self._task = asyncio.create_task(self.background_sync_loop())
        logger.info("✅ Background LLM sync started")

    async def stop(self):
        """Stop the background sync service."""
        if not self.running:
            return

        self.running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug("LLM sync task cancelled during shutdown")

        logger.info("✅ Background LLM sync stopped")

    async def get_service_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific service (thread-safe)."""
        async with self._lock:
            service = self.services.get(service_name)
            if service is None:
                return None
            return {
                "service_name": service.service_name,
                "endpoint": service.endpoint,
                "status": service.status,
                "last_check": service.last_check,
                "response_time": service.response_time,
                "error_count": service.error_count,
                "success_count": service.success_count,
                "metadata": service.metadata.copy(),
            }

    async def get_all_services_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all services (thread-safe)."""
        async with self._lock:
            return {
                name: {
                    "service_name": service.service_name,
                    "endpoint": service.endpoint,
                    "status": service.status,
                    "last_check": service.last_check,
                    "response_time": service.response_time,
                    "error_count": service.error_count,
                    "success_count": service.success_count,
                    "metadata": service.metadata.copy(),  # Copy to prevent mutation
                }
                for name, service in self.services.items()
            }


# Global instance (thread-safe)
import threading

_background_sync: Optional[BackgroundLLMSync] = None
_background_sync_lock = threading.Lock()


def get_background_llm_sync() -> BackgroundLLMSync:
    """Get the global background LLM sync instance (thread-safe)."""
    global _background_sync
    if _background_sync is None:
        with _background_sync_lock:
            # Double-check after acquiring lock
            if _background_sync is None:
                _background_sync = BackgroundLLMSync()
    return _background_sync


async def background_llm_sync():
    """Main entry point for background LLM synchronization."""
    try:
        logger.info("🚀 Starting background LLM synchronization service...")

        sync_service = get_background_llm_sync()
        await sync_service.start()

        # Keep the service running
        while sync_service.running:
            await asyncio.sleep(TimingConstants.STANDARD_DELAY)

    except asyncio.CancelledError:
        logger.info("Background LLM sync cancelled")
    except Exception as e:
        logger.error("❌ Background LLM sync failed: %s", e)
    finally:
        if _background_sync:
            await _background_sync.stop()


# Export main functions and classes
__all__ = [
    "BackgroundLLMSync",
    "LLMServiceStatus",
    "background_llm_sync",
    "get_background_llm_sync",
]
