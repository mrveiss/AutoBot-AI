"""
Tests for Lazy Singleton Initialization Utilities

Verifies that lazy_init_singleton and related functions provide correct
lazy initialization with idempotency, error handling, and cleanup.
"""

import asyncio
from unittest.mock import Mock

import pytest

from src.utils.lazy_singleton import (
    SingletonStorage,
    _global_singleton_storage,
    global_lazy_singleton,
    lazy_init_singleton,
    lazy_init_singleton_async,
    lazy_init_singleton_with_check,
    singleton_getter,
)


# Test classes and factories
class SimpleService:
    """Simple service for testing"""

    def __init__(self, value: str = "test"):
        self.value = value
        self.initialization_count = 0


class ComplexService:
    """Service requiring initialization"""

    def __init__(self):
        self.configured = False

    def configure(self, config: dict):
        self.configured = True
        self.config = config


class FailingService:
    """Service that fails during creation"""

    def __init__(self):
        raise ValueError("Intentional failure")


class AsyncService:
    """Service with async initialization"""

    def __init__(self):
        self.initialized = False

    async def initialize(self):
        await asyncio.sleep(0.01)
        self.initialized = True


class ValidatedService:
    """Service that can be validated"""

    def __init__(self, valid: bool = True):
        self.valid = valid

    def is_healthy(self) -> bool:
        return self.valid


def simple_factory():
    """Factory function for simple service"""
    return SimpleService("factory")


def failing_factory():
    """Factory that always fails"""
    raise RuntimeError("Factory failure")


async def async_factory():
    """Async factory function"""
    service = AsyncService()
    await service.initialize()
    return service


class TestLazyInitSingleton:
    """Test suite for lazy_init_singleton"""

    def test_basic_initialization(self):
        """Test basic lazy initialization"""
        storage = SingletonStorage()

        # First call creates instance
        service = lazy_init_singleton(storage, "test_service", SimpleService)

        assert service is not None
        assert isinstance(service, SimpleService)
        assert hasattr(storage, "test_service")

    def test_idempotency(self):
        """Test that multiple calls return same instance"""
        storage = SingletonStorage()

        # Create first instance
        service1 = lazy_init_singleton(storage, "test_service", SimpleService)
        service1.value = "modified"

        # Second call returns same instance
        service2 = lazy_init_singleton(storage, "test_service", SimpleService)

        assert service1 is service2
        assert service2.value == "modified"

    def test_with_initialization_args(self):
        """Test initialization with arguments"""
        storage = SingletonStorage()

        # Pass arguments to factory
        service = lazy_init_singleton(
            storage, "test_service", SimpleService, value="custom"
        )

        assert service is not None
        assert service.value == "custom"

    def test_with_keyword_args(self):
        """Test initialization with keyword arguments"""
        storage = SingletonStorage()

        # Pass keyword arguments
        service = lazy_init_singleton(
            storage, "test_service", SimpleService, value="keyword"
        )

        assert service is not None
        assert service.value == "keyword"

    def test_with_factory_function(self):
        """Test using factory function instead of class"""
        storage = SingletonStorage()

        # Use factory function
        service = lazy_init_singleton(storage, "test_service", simple_factory)

        assert service is not None
        assert service.value == "factory"

    def test_error_handling(self):
        """Test that errors are handled gracefully"""
        storage = SingletonStorage()

        # Initialize with failing service
        service = lazy_init_singleton(storage, "test_service", FailingService)

        # Should return None on failure
        assert service is None

        # Should not create attribute on storage
        assert not hasattr(storage, "test_service")

    def test_complex_initialization(self):
        """Test complex initialization with post-creation setup"""
        storage = SingletonStorage()

        def complex_factory():
            service = ComplexService()
            service.configure({"key": "value"})
            return service

        # Initialize with complex factory
        service = lazy_init_singleton(storage, "test_service", complex_factory)

        assert service is not None
        assert service.configured is True
        assert service.config == {"key": "value"}

    def test_multiple_attributes(self):
        """Test multiple singletons on same storage"""
        storage = SingletonStorage()

        # Create multiple singletons
        service1 = lazy_init_singleton(storage, "service_1", SimpleService, "first")
        service2 = lazy_init_singleton(storage, "service_2", SimpleService, "second")

        assert service1 is not None
        assert service2 is not None
        assert service1 is not service2
        assert service1.value == "first"
        assert service2.value == "second"


class TestLazyInitSingletonAsync:
    """Test suite for lazy_init_singleton_async"""

    @pytest.mark.asyncio
    async def test_async_basic_initialization(self):
        """Test basic async lazy initialization"""
        storage = SingletonStorage()

        # First call creates instance
        service = await lazy_init_singleton_async(storage, "test_service", AsyncService)

        assert service is not None
        assert isinstance(service, AsyncService)

    @pytest.mark.asyncio
    async def test_async_idempotency(self):
        """Test async idempotency"""
        storage = SingletonStorage()

        # Create first instance
        service1 = await lazy_init_singleton_async(
            storage, "test_service", AsyncService
        )
        service1.custom_attr = "modified"

        # Second call returns same instance
        service2 = await lazy_init_singleton_async(
            storage, "test_service", AsyncService
        )

        assert service1 is service2
        assert hasattr(service2, "custom_attr")
        assert service2.custom_attr == "modified"

    @pytest.mark.asyncio
    async def test_async_factory(self):
        """Test async factory function"""
        storage = SingletonStorage()

        # Use async factory
        service = await lazy_init_singleton_async(
            storage, "test_service", async_factory
        )

        assert service is not None
        assert isinstance(service, AsyncService)
        assert service.initialized is True

    @pytest.mark.asyncio
    async def test_async_error_handling(self):
        """Test async error handling"""
        storage = SingletonStorage()

        async def failing_async_factory():
            raise RuntimeError("Async failure")

        # Initialize with failing factory
        service = await lazy_init_singleton_async(
            storage, "test_service", failing_async_factory
        )

        # Should return None on failure
        assert service is None

    @pytest.mark.asyncio
    async def test_async_concurrent_initialization(self):
        """Test concurrent async initialization"""
        storage = SingletonStorage()

        # Start multiple initializations concurrently
        results = await asyncio.gather(
            lazy_init_singleton_async(storage, "test_service", AsyncService),
            lazy_init_singleton_async(storage, "test_service", AsyncService),
            lazy_init_singleton_async(storage, "test_service", AsyncService),
        )

        # All should return instances
        assert all(r is not None for r in results)

        # But they should all be the same instance (first one created)
        assert results[0] is results[1]
        assert results[1] is results[2]


class TestLazyInitSingletonWithCheck:
    """Test suite for lazy_init_singleton_with_check"""

    def test_with_validation_success(self):
        """Test initialization with successful validation"""
        storage = SingletonStorage()

        def validator(service: ValidatedService) -> bool:
            return service.is_healthy()

        # Initialize with valid service
        service = lazy_init_singleton_with_check(
            storage, "test_service", ValidatedService, validator, valid=True
        )

        assert service is not None
        assert service.is_healthy() is True

    def test_with_validation_failure(self):
        """Test initialization with failed validation"""
        storage = SingletonStorage()

        def validator(service: ValidatedService) -> bool:
            return service.is_healthy()

        # Initialize with invalid service
        service = lazy_init_singleton_with_check(
            storage, "test_service", ValidatedService, validator, valid=False
        )

        # Should return None when validation fails
        assert service is None

    def test_revalidation_on_access(self):
        """Test that existing instance is revalidated"""
        storage = SingletonStorage()

        validation_count = {"count": 0}

        def validator(service: ValidatedService) -> bool:
            validation_count["count"] += 1
            return service.is_healthy()

        # First initialization
        service1 = lazy_init_singleton_with_check(
            storage, "test_service", ValidatedService, validator, valid=True
        )

        assert service1 is not None
        assert validation_count["count"] == 1

        # Second call revalidates existing instance
        service2 = lazy_init_singleton_with_check(
            storage, "test_service", ValidatedService, validator, valid=True
        )

        assert service2 is service1
        assert validation_count["count"] == 2

    def test_reinitialize_on_validation_failure(self):
        """Test that instance is recreated when validation fails"""
        storage = SingletonStorage()

        # Create initial valid service
        service1 = lazy_init_singleton_with_check(
            storage,
            "test_service",
            ValidatedService,
            lambda s: s.is_healthy(),
            valid=True,
        )

        assert service1 is not None

        # Invalidate the service
        service1.valid = False

        # Next call should recreate (but will still be invalid)
        service2 = lazy_init_singleton_with_check(
            storage,
            "test_service",
            ValidatedService,
            lambda s: s.is_healthy(),
            valid=False,
        )

        # Should fail validation and return None
        assert service2 is None


class TestSingletonGetter:
    """Test suite for singleton_getter decorator"""

    def test_decorator_basic_usage(self):
        """Test basic decorator usage"""

        @singleton_getter("test_service", SimpleService)
        def get_test_service(request):
            return SimpleService

        # Create mock request
        request = Mock()
        request.app.state = SingletonStorage()

        # First call creates instance
        service1 = get_test_service(request)
        assert service1 is not None

        # Second call returns same instance
        service2 = get_test_service(request)
        assert service1 is service2

    def test_decorator_with_factory_return(self):
        """Test decorator where function returns factory"""

        @singleton_getter("test_service", SimpleService)
        def get_test_service(request):
            # Function can return factory class
            return SimpleService

        request = Mock()
        request.app.state = SingletonStorage()

        service = get_test_service(request)
        assert service is not None
        assert isinstance(service, SimpleService)

    def test_decorator_with_callable_return(self):
        """Test decorator where function returns callable"""

        @singleton_getter("test_service", simple_factory)
        def get_test_service(request):
            # Function can return callable factory
            return simple_factory

        request = Mock()
        request.app.state = SingletonStorage()

        service = get_test_service(request)
        assert service is not None
        assert service.value == "factory"


class TestGlobalLazySingleton:
    """Test suite for global_lazy_singleton"""

    def test_global_singleton_basic(self):
        """Test basic global singleton creation"""
        # Clean up any existing global state
        if hasattr(_global_singleton_storage, "test_global"):
            delattr(_global_singleton_storage, "test_global")

        # Create global singleton
        service1 = global_lazy_singleton("test_global", SimpleService, "global")

        assert service1 is not None
        assert service1.value == "global"

        # Second call returns same instance
        service2 = global_lazy_singleton("test_global", SimpleService, "different")

        assert service1 is service2
        assert service2.value == "global"  # Still original value

    def test_global_singleton_isolation(self):
        """Test that global singletons are isolated by name"""
        # Clean up
        for attr in ["global_1", "global_2"]:
            if hasattr(_global_singleton_storage, attr):
                delattr(_global_singleton_storage, attr)

        # Create two different global singletons
        service1 = global_lazy_singleton("global_1", SimpleService, "first")
        service2 = global_lazy_singleton("global_2", SimpleService, "second")

        assert service1 is not service2
        assert service1.value == "first"
        assert service2.value == "second"


class TestSingletonStorage:
    """Test suite for SingletonStorage class"""

    def test_storage_creation(self):
        """Test that storage can be created"""
        storage = SingletonStorage()
        assert storage is not None

    def test_storage_attribute_access(self):
        """Test setting and getting attributes on storage"""
        storage = SingletonStorage()

        # Set attribute
        storage.test_attr = "value"

        # Get attribute
        assert hasattr(storage, "test_attr")
        assert storage.test_attr == "value"

    def test_storage_independence(self):
        """Test that different storage instances are independent"""
        storage1 = SingletonStorage()
        storage2 = SingletonStorage()

        storage1.attr = "value1"
        storage2.attr = "value2"

        assert storage1.attr == "value1"
        assert storage2.attr == "value2"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
