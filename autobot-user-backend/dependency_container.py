#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dependency Injection Container for AutoBot
Manages all async services with proper lifecycle and dependency resolution
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, Optional, Type, TypeVar

import redis.asyncio as async_redis

from src.config import UnifiedConfigManager, unified_config_manager
from src.llm_interface import LLMInterface, get_llm_interface
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Issue #380: Module-level tuple for critical service names
_CRITICAL_SERVICES = ("redis", "config", "llm")


@dataclass
class ServiceDescriptor:
    """Describes a service registration"""

    service_type: Type[T]
    factory: Optional[Callable] = None
    singleton: bool = True
    initialized: bool = False
    instance: Any = None
    dependencies: list = field(default_factory=list)
    lifecycle_hooks: Dict[str, Callable] = field(default_factory=dict)


class AsyncServiceContainer:
    """
    Async dependency injection container with lifecycle management
    """

    def __init__(self):
        """Initialize container with empty service registry and core services."""
        self._services: Dict[str, ServiceDescriptor] = {}
        self._instances: Dict[str, Any] = {}
        self._initialization_lock = asyncio.Lock()
        self._shutdown_hooks: list = []
        self._initialized_services: set = set()

        # Register core services
        self._register_core_services()

    def _register_core_services(self) -> None:
        """Register core AutoBot services"""

        # Redis Manager
        self._services["redis"] = ServiceDescriptor(
            service_type=async_redis.Redis,
            factory=self._create_redis_manager,
            singleton=True,
        )

        # Config Manager
        self._services["config"] = ServiceDescriptor(
            service_type=UnifiedConfigManager,
            factory=self._create_config_manager,
            singleton=True,
        )

        # LLM Interface
        self._services["llm"] = ServiceDescriptor(
            service_type=LLMInterface,
            factory=self._create_llm_interface,
            singleton=True,
            dependencies=["config"],
        )

    async def _create_redis_manager(self) -> async_redis.Redis:
        """Factory for Redis manager"""
        return await get_redis_client(async_client=True, database="main")

    async def _create_config_manager(self) -> UnifiedConfigManager:
        """Factory for config manager"""
        return unified_config_manager

    async def _create_llm_interface(self) -> LLMInterface:
        """Factory for LLM interface"""
        return get_llm_interface()

    def register_service(
        self,
        name: str,
        service_type: Type[T],
        factory: Optional[Callable] = None,
        singleton: bool = True,
        dependencies: Optional[list] = None,
    ) -> None:
        """Register a service with the container"""
        self._services[name] = ServiceDescriptor(
            service_type=service_type,
            factory=factory,
            singleton=singleton,
            dependencies=dependencies or [],
        )

        logger.debug("Registered service: %s (%s)", name, service_type.__name__)

    def register_instance(self, name: str, instance: Any) -> None:
        """Register an existing instance"""
        service_type = type(instance)
        self._services[name] = ServiceDescriptor(
            service_type=service_type,
            instance=instance,
            singleton=True,
            initialized=True,
        )
        self._instances[name] = instance
        self._initialized_services.add(name)

        logger.debug("Registered instance: %s (%s)", name, service_type.__name__)

    async def _resolve_dependencies(
        self, descriptor: ServiceDescriptor
    ) -> Dict[str, Any]:
        """Resolve service dependencies recursively. Issue #620."""
        resolved_deps = {}
        for dep_name in descriptor.dependencies:
            resolved_deps[dep_name] = await self.get_service(dep_name)
        return resolved_deps

    async def _create_service_instance(self, descriptor: ServiceDescriptor) -> Any:
        """Create service instance from factory or direct instantiation. Issue #620."""
        if descriptor.factory:
            if asyncio.iscoroutinefunction(descriptor.factory):
                return await descriptor.factory()
            return descriptor.factory()
        if descriptor.instance:
            return descriptor.instance
        return descriptor.service_type()

    def _store_singleton_instance(
        self, name: str, descriptor: ServiceDescriptor, instance: Any
    ) -> None:
        """Store singleton instance in cache and registry. Issue #620."""
        if descriptor.singleton:
            descriptor.instance = instance
            descriptor.initialized = True
            self._instances[name] = instance
            self._initialized_services.add(name)

    async def _run_init_hook(
        self, descriptor: ServiceDescriptor, instance: Any
    ) -> None:
        """Run initialization lifecycle hook if defined. Issue #620."""
        if "on_init" in descriptor.lifecycle_hooks:
            hook = descriptor.lifecycle_hooks["on_init"]
            if asyncio.iscoroutinefunction(hook):
                await hook(instance)
            else:
                hook(instance)

    async def get_service(self, name: str) -> Any:
        """Get service instance with dependency resolution."""
        if name not in self._services:
            raise ValueError(f"Service '{name}' not registered")

        descriptor = self._services[name]

        # Return existing instance if singleton
        if descriptor.singleton and descriptor.initialized and descriptor.instance:
            return descriptor.instance

        # Check instances cache
        if name in self._instances:
            return self._instances[name]

        # Initialize with dependency resolution
        async with self._initialization_lock:
            # Double-check after acquiring lock
            if name in self._instances:
                return self._instances[name]

            await self._resolve_dependencies(descriptor)
            instance = await self._create_service_instance(descriptor)
            self._store_singleton_instance(name, descriptor, instance)
            await self._run_init_hook(descriptor, instance)

            logger.info("Initialized service: %s", name)
            return instance

    @asynccontextmanager
    async def get_scoped_service(self, name: str) -> AsyncGenerator[Any, None]:
        """Get service with automatic cleanup"""
        instance = await self.get_service(name)
        try:
            yield instance
        finally:
            # Run cleanup if service has close method
            if hasattr(instance, "close") and callable(instance.close):
                try:
                    if asyncio.iscoroutinefunction(instance.close):
                        await instance.close()
                    else:
                        instance.close()
                except Exception as e:
                    logger.warning("Error closing service %s: %s", name, e)

    async def initialize_all_services(self) -> Dict[str, bool]:
        """Initialize all registered services"""
        results = {}

        # Sort services by dependency order
        ordered_services = self._resolve_dependency_order()

        for service_name in ordered_services:
            try:
                await self.get_service(service_name)
                results[service_name] = True
                logger.info("✅ Service initialized: %s", service_name)
            except Exception as e:
                results[service_name] = False
                logger.error("❌ Failed to initialize service %s: %s", service_name, e)

        return results

    def _resolve_dependency_order(self) -> list:
        """Resolve service initialization order based on dependencies"""
        ordered = []
        visited = set()
        temp_visited = set()

        def visit(service_name: str):
            """Recursively visit service and its dependencies for ordering."""
            if service_name in temp_visited:
                raise ValueError(
                    f"Circular dependency detected involving {service_name}"
                )

            if service_name in visited:
                return

            temp_visited.add(service_name)

            # Visit dependencies first
            if service_name in self._services:
                for dep in self._services[service_name].dependencies:
                    visit(dep)

            temp_visited.remove(service_name)
            visited.add(service_name)
            ordered.append(service_name)

        for service_name in self._services:
            if service_name not in visited:
                visit(service_name)

        return ordered

    def add_shutdown_hook(self, hook: Callable) -> None:
        """Add shutdown hook"""
        self._shutdown_hooks.append(hook)

    async def shutdown_all_services(self) -> None:
        """Shutdown all services in reverse order"""
        # Run shutdown hooks first
        for hook in reversed(self._shutdown_hooks):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                logger.warning("Shutdown hook error: %s", e)

        # Shutdown services in reverse initialization order
        for service_name in reversed(list(self._initialized_services)):
            try:
                descriptor = self._services.get(service_name)
                if not descriptor or not descriptor.instance:
                    continue

                instance = descriptor.instance

                # Run shutdown hook if exists
                if "on_shutdown" in descriptor.lifecycle_hooks:
                    hook = descriptor.lifecycle_hooks["on_shutdown"]
                    if asyncio.iscoroutinefunction(hook):
                        await hook(instance)
                    else:
                        hook(instance)

                # Call close method if exists
                if hasattr(instance, "close") and callable(instance.close):
                    if asyncio.iscoroutinefunction(instance.close):
                        await instance.close()
                    else:
                        instance.close()

                logger.info("Shutdown service: %s", service_name)

            except Exception as e:
                logger.error("Error shutting down service %s: %s", service_name, e)

        # Clear all caches
        self._instances.clear()
        self._initialized_services.clear()

        # Reset service descriptors
        for descriptor in self._services.values():
            descriptor.initialized = False
            descriptor.instance = None

        logger.info("All services shutdown complete")

    async def health_check_all_services(self) -> Dict[str, Dict[str, Any]]:
        """Run health checks on all services"""
        results = {}

        for service_name in self._initialized_services:
            try:
                instance = self._instances.get(service_name)
                if instance and hasattr(instance, "health_check"):
                    if asyncio.iscoroutinefunction(instance.health_check):
                        health = await instance.health_check()
                    else:
                        health = instance.health_check()

                    results[service_name] = health
                else:
                    results[service_name] = {
                        "status": "healthy",
                        "message": "Service running (no health check method)",
                    }
            except Exception as e:
                results[service_name] = {"status": "unhealthy", "error": str(e)}

        return results

    def get_service_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all registered services"""
        info = {}

        for name, descriptor in self._services.items():
            info[name] = {
                "type": descriptor.service_type.__name__,
                "singleton": descriptor.singleton,
                "initialized": descriptor.initialized,
                "dependencies": descriptor.dependencies,
                "has_factory": descriptor.factory is not None,
                "has_instance": descriptor.instance is not None,
            }

        return info


# Global container instance
container = AsyncServiceContainer()


# Convenience functions for common services
async def get_redis() -> async_redis.Redis:
    """Get Redis manager"""
    return await container.get_service("redis")


async def get_config() -> UnifiedConfigManager:
    """Get config manager"""
    return await container.get_service("config")


async def get_llm() -> LLMInterface:
    """Get LLM interface"""
    return await container.get_service("llm")


# Context manager for service lifecycle
@asynccontextmanager
async def service_context():
    """Context manager for automatic service lifecycle management"""
    try:
        # Initialize all services
        initialization_results = await container.initialize_all_services()

        # Check if critical services failed (Issue #380: use module-level constant)
        failed_critical = [
            name
            for name in _CRITICAL_SERVICES
            if name in initialization_results and not initialization_results[name]
        ]

        if failed_critical:
            logger.warning(
                "Critical services failed to initialize: %s", failed_critical
            )

        logger.info(
            f"Service container initialized: {len(initialization_results)} services"
        )
        yield container

    finally:
        # Shutdown all services
        await container.shutdown_all_services()
        logger.info("Service container shutdown complete")


# Decorators for dependency injection
def inject_service(service_name: str):
    """Decorator to inject service into function"""

    def decorator(func):
        """Inner decorator that wraps function with service injection."""

        async def wrapper(*args, **kwargs):
            """Async wrapper that injects requested service before calling function."""
            service = await container.get_service(service_name)
            return await func(service, *args, **kwargs)

        return wrapper

    return decorator


def inject_services(**service_mapping):
    """Decorator to inject multiple services"""

    def decorator(func):
        """Inner decorator that wraps function with multiple service injections."""

        async def wrapper(*args, **kwargs):
            """Async wrapper that injects all mapped services before calling function."""
            services = {}
            for param_name, service_name in service_mapping.items():
                services[param_name] = await container.get_service(service_name)

            return await func(*args, **services, **kwargs)

        return wrapper

    return decorator
