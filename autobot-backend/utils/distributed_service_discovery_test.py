# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for DistributedServiceDiscovery AsyncInitializable migration (#3947).

Verifies:
- __init__ contains no I/O or blocking calls
- _initialize_service_registry() is called from _initialize_impl()
- get_service_discovery() singleton calls await instance.initialize()
- ConfigManager is NOT imported
- AsyncInitializable pattern: idempotency, lazy-init, concurrency safety
"""

import asyncio

import pytest


class TestDistributedServiceDiscoveryLazyInit:
    """DistributedServiceDiscovery must not perform I/O at construction time."""

    def setup_method(self):
        import utils.distributed_service_discovery as mod

        mod._service_discovery = None

    def teardown_method(self):
        import utils.distributed_service_discovery as mod

        mod._service_discovery = None

    def test_no_config_manager_import(self):
        """ConfigManager must NOT be imported by this module (#3947)."""
        import utils.distributed_service_discovery as mod

        assert not hasattr(
            mod, "unified_config_manager"
        ), "unified_config_manager was imported — ConfigManager dependency not removed"
        assert not hasattr(mod, "ConfigManager"), "ConfigManager was imported — dependency not removed"

    def test_not_initialized_at_construction(self):
        """__init__ must be I/O-free; is_initialized must be False after construction."""
        from utils.distributed_service_discovery import DistributedServiceDiscovery

        instance = DistributedServiceDiscovery()

        assert not instance.is_initialized
        # Services dict should be empty until initialize() is called
        assert instance.services == {}

    @pytest.mark.asyncio
    async def test_initializes_on_first_call(self):
        """initialize() must populate service registry and return True."""
        from utils.distributed_service_discovery import DistributedServiceDiscovery

        instance = DistributedServiceDiscovery()

        result = await instance.initialize()

        assert result is True
        assert instance.is_initialized
        # After init, services dict must be populated
        assert len(instance.services) > 0

    @pytest.mark.asyncio
    async def test_initialize_impl_calls_registry(self):
        """_initialize_impl must delegate to _initialize_service_registry."""
        from utils.distributed_service_discovery import DistributedServiceDiscovery

        instance = DistributedServiceDiscovery()
        registry_called = []

        original_registry = instance._initialize_service_registry

        def _tracked_registry():
            registry_called.append(True)
            original_registry()

        instance._initialize_service_registry = _tracked_registry

        await instance.initialize()

        assert (
            len(registry_called) == 1
        ), "_initialize_service_registry must be called exactly once from _initialize_impl"

    @pytest.mark.asyncio
    async def test_idempotent_initialize(self):
        """initialize() called multiple times must only run _initialize_impl once."""
        from utils.distributed_service_discovery import DistributedServiceDiscovery

        instance = DistributedServiceDiscovery()
        call_count = []

        original_impl = instance._initialize_impl

        async def _counted_impl():
            call_count.append(1)
            return await original_impl()

        instance._initialize_impl = _counted_impl

        r1 = await instance.initialize()
        r2 = await instance.initialize()
        r3 = await instance.initialize()

        assert r1 is r2 is r3 is True
        assert len(call_count) == 1, "_initialize_impl must only execute once"

    @pytest.mark.asyncio
    async def test_concurrent_initialize_safe(self):
        """Concurrent calls to initialize() must not run _initialize_impl multiple times."""
        from utils.distributed_service_discovery import DistributedServiceDiscovery

        instance = DistributedServiceDiscovery()
        call_count = []

        original_impl = instance._initialize_impl

        async def _slow_impl():
            call_count.append(1)
            await asyncio.sleep(0.05)  # Simulate I/O
            return await original_impl()

        instance._initialize_impl = _slow_impl

        results = await asyncio.gather(
            instance.initialize(),
            instance.initialize(),
            instance.initialize(),
        )

        assert all(r is True for r in results)
        assert len(call_count) == 1, "Concurrent init must use locking — only one execution"


class TestGetServiceDiscoverySingleton:
    """get_service_discovery() must return an initialized singleton."""

    def setup_method(self):
        import utils.distributed_service_discovery as mod

        mod._service_discovery = None

    def teardown_method(self):
        import utils.distributed_service_discovery as mod

        mod._service_discovery = None

    @pytest.mark.asyncio
    async def test_returns_initialized_instance(self):
        """get_service_discovery() must return an already-initialized instance."""
        from utils.distributed_service_discovery import get_service_discovery

        instance = await get_service_discovery()

        assert instance is not None
        assert instance.is_initialized

    @pytest.mark.asyncio
    async def test_returns_same_singleton(self):
        """Repeated calls to get_service_discovery() must return the same object."""
        from utils.distributed_service_discovery import get_service_discovery

        a = await get_service_discovery()
        b = await get_service_discovery()
        c = await get_service_discovery()

        assert a is b is c

    @pytest.mark.asyncio
    async def test_concurrent_singleton_creation_safe(self):
        """Concurrent calls must not create multiple instances."""
        from utils.distributed_service_discovery import get_service_discovery

        instances = await asyncio.gather(
            get_service_discovery(),
            get_service_discovery(),
            get_service_discovery(),
        )

        first = instances[0]
        assert all(inst is first for inst in instances), "All concurrent calls must receive the same singleton instance"


class TestServiceRegistryContents:
    """Service registry must be populated correctly after initialization."""

    def setup_method(self):
        import utils.distributed_service_discovery as mod

        mod._service_discovery = None

    def teardown_method(self):
        import utils.distributed_service_discovery as mod

        mod._service_discovery = None

    @pytest.mark.asyncio
    async def test_all_expected_services_registered(self):
        """After init, all expected services must be in the registry."""
        from utils.distributed_service_discovery import DistributedServiceDiscovery

        instance = DistributedServiceDiscovery()
        await instance.initialize()

        expected_services = {"redis", "backend", "frontend", "npu_worker", "ai_stack", "browser", "ollama"}
        registered = set(instance.services.keys())

        assert expected_services == registered, f"Expected services {expected_services}, got {registered}"

    @pytest.mark.asyncio
    async def test_service_endpoints_have_host_and_port(self):
        """Each registered ServiceEndpoint must have non-empty host and valid port."""
        from utils.distributed_service_discovery import DistributedServiceDiscovery

        instance = DistributedServiceDiscovery()
        await instance.initialize()

        for name, endpoint in instance.services.items():
            assert endpoint.host, f"Service '{name}' has empty host"
            assert isinstance(endpoint.port, int), f"Service '{name}' port is not int"
            assert endpoint.port > 0, f"Service '{name}' port must be positive"

    @pytest.mark.asyncio
    async def test_backup_endpoints_registered(self):
        """Backup endpoints for redis, backend, and ollama must be registered."""
        from utils.distributed_service_discovery import DistributedServiceDiscovery

        instance = DistributedServiceDiscovery()
        await instance.initialize()

        expected_backups = {"redis", "backend", "ollama"}
        assert expected_backups.issubset(set(instance.backup_endpoints.keys()))

    @pytest.mark.asyncio
    async def test_component_name(self):
        """component_name must identify the service correctly."""
        from utils.distributed_service_discovery import DistributedServiceDiscovery

        instance = DistributedServiceDiscovery()

        assert instance.component_name == "distributed_service_discovery"


class TestGetServiceUrl:
    """get_service_url() must return a valid URL without DNS delays."""

    def setup_method(self):
        import utils.distributed_service_discovery as mod

        mod._service_discovery = None

    def teardown_method(self):
        import utils.distributed_service_discovery as mod

        mod._service_discovery = None

    @pytest.mark.asyncio
    async def test_returns_url_for_known_service(self):
        """get_service_url() must return a non-empty URL for a registered service."""
        from utils.distributed_service_discovery import get_service_url

        url = await get_service_url("backend")

        assert url, "get_service_url must return a non-empty string"
        assert url.startswith("http://") or url.startswith(
            "https://"
        ), f"URL must start with http:// or https://, got: {url}"

    @pytest.mark.asyncio
    async def test_returns_fallback_for_unknown_service(self):
        """get_service_url() must return fallback URL for unknown service names."""
        from utils.distributed_service_discovery import get_service_url

        url = await get_service_url("__nonexistent_service__")

        assert url, "Fallback URL must not be empty"
        assert url.startswith("http://"), f"Fallback must be an http URL, got: {url}"
