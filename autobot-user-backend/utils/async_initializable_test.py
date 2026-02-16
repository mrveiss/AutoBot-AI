"""
Tests for AsyncInitializable Base Class

Verifies that the base class provides correct initialization patterns with
idempotency, locking, error handling, cleanup, metrics, and retry logic.
"""

import asyncio

import pytest

from backend.utils.async_initializable import AsyncInitializable, SyncInitializable


# Test implementations
class SimpleAsyncService(AsyncInitializable):
    """Simple test service"""

    def __init__(self):
        super().__init__(component_name="simple_service")
        self.initialization_count = 0

    async def _initialize_impl(self) -> bool:
        """Simple initialization"""
        self.initialization_count += 1
        await asyncio.sleep(0.01)  # Simulate async work
        return True


class FailingAsyncService(AsyncInitializable):
    """Service that always fails initialization"""

    def __init__(self):
        super().__init__(component_name="failing_service", max_retries=2)
        self.attempt_count = 0

    async def _initialize_impl(self) -> bool:
        """Always fails"""
        self.attempt_count += 1
        raise ValueError(f"Initialization attempt {self.attempt_count} failed")


class CleanupAsyncService(AsyncInitializable):
    """Service that tracks cleanup"""

    def __init__(self):
        super().__init__(component_name="cleanup_service")
        self.cleanup_called = False

    async def _initialize_impl(self) -> bool:
        """Always fails to test cleanup"""
        raise RuntimeError("Intentional failure")

    async def _cleanup_impl(self):
        """Track cleanup"""
        self.cleanup_called = True


class RetryAsyncService(AsyncInitializable):
    """Service that succeeds after retries"""

    def __init__(self):
        super().__init__(
            component_name="retry_service",
            max_retries=3,
            retry_delay=0.01,  # Fast for testing
            retry_backoff=2.0,
        )
        self.attempt_count = 0

    async def _initialize_impl(self) -> bool:
        """Succeeds on 3rd attempt"""
        self.attempt_count += 1
        if self.attempt_count < 3:
            raise ValueError(f"Attempt {self.attempt_count} failed")
        return True


class SimpleSyncService(SyncInitializable):
    """Simple synchronous test service"""

    def __init__(self):
        super().__init__(component_name="simple_sync_service")
        self.initialization_count = 0

    def _initialize_impl(self) -> bool:
        """Simple sync initialization"""
        self.initialization_count += 1
        return True


class TestAsyncInitializable:
    """Test suite for AsyncInitializable"""

    @pytest.mark.asyncio
    async def test_basic_initialization(self):
        """Test basic initialization works"""
        service = SimpleAsyncService()

        assert not service.is_initialized
        assert service.initialization_count == 0

        # Initialize
        result = await service.initialize()

        assert result is True
        assert service.is_initialized
        assert service.initialization_count == 1

    @pytest.mark.asyncio
    async def test_idempotency(self):
        """Test that initialize() can be called multiple times safely"""
        service = SimpleAsyncService()

        # Call initialize multiple times
        result1 = await service.initialize()
        result2 = await service.initialize()
        result3 = await service.initialize()

        # All should succeed
        assert result1 is True
        assert result2 is True
        assert result3 is True

        # But implementation should only run once
        assert service.initialization_count == 1
        assert service.is_initialized

    @pytest.mark.asyncio
    async def test_concurrent_initialization(self):
        """Test that concurrent calls are handled correctly"""
        service = SimpleAsyncService()

        # Start multiple initializations concurrently
        results = await asyncio.gather(
            service.initialize(),
            service.initialize(),
            service.initialize(),
            service.initialize(),
            service.initialize(),
        )

        # All should succeed
        assert all(r is True for r in results)

        # But implementation should only run once (lock prevents race)
        assert service.initialization_count == 1
        assert service.is_initialized

    @pytest.mark.asyncio
    async def test_initialization_failure(self):
        """Test that failed initialization is handled correctly"""
        service = FailingAsyncService()

        # Initialize should fail
        result = await service.initialize()

        assert result is False
        assert not service.is_initialized
        assert service.attempt_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_cleanup_on_failure(self):
        """Test that cleanup is called on initialization failure"""
        service = CleanupAsyncService()

        # Initialize should fail
        result = await service.initialize()

        assert result is False
        assert not service.is_initialized
        assert service.cleanup_called is True

    @pytest.mark.asyncio
    async def test_retry_logic(self):
        """Test retry logic with exponential backoff"""
        service = RetryAsyncService()

        # Initialize should succeed after retries
        result = await service.initialize()

        assert result is True
        assert service.is_initialized
        assert service.attempt_count == 3  # Succeeds on 3rd attempt

    @pytest.mark.asyncio
    async def test_initialization_metrics(self):
        """Test that metrics are tracked correctly"""
        service = SimpleAsyncService()

        await service.initialize()

        metrics = service.initialization_metrics

        # Check metrics exist
        assert metrics.component_name == "simple_service"
        assert metrics.success is True
        assert metrics.retry_count == 0
        assert metrics.start_time is not None
        assert metrics.end_time is not None
        assert metrics.duration_seconds is not None
        assert metrics.duration_seconds > 0
        assert metrics.last_error is None

    @pytest.mark.asyncio
    async def test_failure_metrics(self):
        """Test that failure metrics are tracked"""
        service = FailingAsyncService()

        await service.initialize()

        metrics = service.initialization_metrics

        # Check failure metrics
        assert metrics.component_name == "failing_service"
        assert metrics.success is False
        assert metrics.retry_count == 2  # 2 retries after initial attempt
        assert metrics.last_error is not None
        assert "Initialization attempt" in metrics.last_error

    @pytest.mark.asyncio
    async def test_ensure_initialized_success(self):
        """Test ensure_initialized when initialization succeeds"""
        service = SimpleAsyncService()

        # Should not raise
        await service.ensure_initialized()

        assert service.is_initialized

    @pytest.mark.asyncio
    async def test_ensure_initialized_failure(self):
        """Test ensure_initialized raises on failure"""
        service = FailingAsyncService()

        # Should raise RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            await service.ensure_initialized()

        assert "initialization failed" in str(exc_info.value).lower()
        assert not service.is_initialized

    @pytest.mark.asyncio
    async def test_component_name_property(self):
        """Test component_name property"""
        service = SimpleAsyncService()

        assert service.component_name == "simple_service"

    @pytest.mark.asyncio
    async def test_retry_with_backoff_timing(self):
        """Test that retry delays follow exponential backoff"""
        import time

        service = RetryAsyncService()

        start_time = time.time()
        await service.initialize()
        duration = time.time() - start_time

        # With retry_delay=0.01 and backoff=2.0:
        # Attempt 1: immediate (fails)
        # Attempt 2: after 0.01s delay (fails)
        # Attempt 3: after 0.02s delay (succeeds)
        # Total minimum: 0.03s
        assert duration >= 0.03

        # Metrics show retry count = last failed attempt index
        # Attempt 1 (index 0) fails, retry_count=0
        # Attempt 2 (index 1) fails, retry_count=1
        # Attempt 3 (index 2) succeeds
        # So retry_count=1 (from last failure)
        assert service.initialization_metrics.retry_count == 1


class TestSyncInitializable:
    """Test suite for SyncInitializable (synchronous version)"""

    def test_sync_basic_initialization(self):
        """Test basic synchronous initialization"""
        service = SimpleSyncService()

        assert not service.is_initialized
        assert service.initialization_count == 0

        # Initialize (no await)
        result = service.initialize()

        assert result is True
        assert service.is_initialized
        assert service.initialization_count == 1

    def test_sync_idempotency(self):
        """Test synchronous idempotency"""
        service = SimpleSyncService()

        # Call initialize multiple times
        result1 = service.initialize()
        result2 = service.initialize()
        result3 = service.initialize()

        # All should succeed
        assert result1 is True
        assert result2 is True
        assert result3 is True

        # But implementation should only run once
        assert service.initialization_count == 1
        assert service.is_initialized

    def test_sync_metrics(self):
        """Test synchronous metrics tracking"""
        service = SimpleSyncService()

        service.initialize()

        metrics = service.initialization_metrics

        # Check metrics
        assert metrics.component_name == "simple_sync_service"
        assert metrics.success is True
        assert metrics.duration_seconds is not None
        assert metrics.duration_seconds >= 0

    def test_sync_ensure_initialized(self):
        """Test synchronous ensure_initialized"""
        service = SimpleSyncService()

        # Should not raise
        service.ensure_initialized()

        assert service.is_initialized


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
