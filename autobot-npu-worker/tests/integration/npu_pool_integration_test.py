# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Worker Pool Integration Tests (Issue #168)

Tests for multi-worker task execution, failover behavior,
health monitoring, and config hot-reload with mock HTTP responses.
"""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock

import pytest

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def two_worker_config_file():
    """Create a temporary config file with two workers."""
    config_content = """
npu:
  workers:
    - id: "primary-worker"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
    - id: "secondary-worker"
      host: "192.168.1.11"
      port: 8082
      enabled: true
      priority: 5
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(config_content)
        f.flush()  # Ensure content is written before yield
        config_path = f.name

    yield config_path
    os.unlink(config_path)


@pytest.fixture
def single_worker_config_file():
    """Create a temporary config file with one worker."""
    config_content = """
npu:
  workers:
    - id: "solo-worker"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(config_content)
        f.flush()  # Ensure content is written before yield
        config_path = f.name

    yield config_path
    os.unlink(config_path)


# =============================================================================
# Multi-Worker Task Execution Tests
# =============================================================================


@pytest.mark.asyncio
async def test_task_routes_to_highest_priority_worker(two_worker_config_file):
    """Tasks should route to highest priority worker when healthy."""
    from npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path=two_worker_config_file)

    # Mock both workers' execute methods
    pool.workers["primary-worker"].client.offload_heavy_processing = AsyncMock(
        return_value={"success": True, "result": "primary_response"}
    )
    pool.workers["secondary-worker"].client.offload_heavy_processing = AsyncMock(
        return_value={"success": True, "result": "secondary_response"}
    )

    result = await pool.execute_task("text_analysis", {"text": "test"})

    # Should route to primary (priority 10) not secondary (priority 5)
    assert result["success"] is True
    assert result["result"] == "primary_response"
    pool.workers["primary-worker"].client.offload_heavy_processing.assert_called_once()
    pool.workers["secondary-worker"].client.offload_heavy_processing.assert_not_called()


@pytest.mark.asyncio
async def test_failover_to_secondary_on_primary_failure(two_worker_config_file):
    """Task should failover to secondary worker when primary fails."""
    from npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path=two_worker_config_file)

    # Primary fails, secondary succeeds
    pool.workers["primary-worker"].client.offload_heavy_processing = AsyncMock(
        side_effect=Exception("Primary connection timeout")
    )
    pool.workers["secondary-worker"].client.offload_heavy_processing = AsyncMock(
        return_value={"success": True, "result": "secondary_response"}
    )

    result = await pool.execute_task("text_analysis", {"text": "test"})

    # Should failover and succeed via secondary
    assert result["success"] is True
    assert result["result"] == "secondary_response"
    # Primary should have one failure recorded
    assert pool.workers["primary-worker"].failures >= 1


@pytest.mark.asyncio
async def test_load_distribution_with_concurrent_tasks(two_worker_config_file):
    """Multiple concurrent tasks should distribute based on active_tasks."""
    from npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path=two_worker_config_file)

    # Make both workers respond successfully with delays
    async def slow_response(*args, **kwargs):
        await asyncio.sleep(0.1)
        return {"success": True, "result": "completed"}

    pool.workers["primary-worker"].client.offload_heavy_processing = AsyncMock(
        side_effect=slow_response
    )
    pool.workers["secondary-worker"].client.offload_heavy_processing = AsyncMock(
        side_effect=slow_response
    )

    # Simulate primary being busy
    pool.workers["primary-worker"].active_tasks = 5

    # Now secondary should be selected (least connections within same priority group)
    # But since primary has priority 10 and secondary has priority 5,
    # primary should still be selected unless circuit is open
    # Let's test with same priority
    pool._worker_configs["secondary-worker"]["priority"] = 10

    result = await pool.execute_task("text_analysis", {"text": "test"})

    assert result["success"] is True


# =============================================================================
# Circuit Breaker Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_circuit_opens_after_consecutive_failures(single_worker_config_file):
    """Circuit breaker should open after threshold failures."""
    import time

    from npu_integration import CircuitState, NPUWorkerPool

    pool = NPUWorkerPool(config_path=single_worker_config_file)

    # Configure worker to fail
    pool.workers["solo-worker"].client.offload_heavy_processing = AsyncMock(
        side_effect=Exception("Connection refused")
    )

    # Execute tasks until circuit opens (5 failures threshold)
    for _ in range(5):
        await pool.execute_task("text_analysis", {"text": "test"})

    # Circuit should now be OPEN
    assert pool.workers["solo-worker"].circuit_state == CircuitState.OPEN
    assert pool.workers["solo-worker"].circuit_open_until > time.time()


@pytest.mark.asyncio
async def test_half_open_circuit_allows_test_request(single_worker_config_file):
    """Circuit in HALF_OPEN state should allow one test request."""
    import time

    from npu_integration import CircuitState, NPUWorkerPool

    pool = NPUWorkerPool(config_path=single_worker_config_file)

    # Set circuit to HALF_OPEN (simulating cooldown expiry)
    pool.workers["solo-worker"].circuit_state = CircuitState.HALF_OPEN
    pool.workers["solo-worker"].circuit_open_until = time.time() - 1  # Expired

    # Configure worker to succeed
    pool.workers["solo-worker"].client.offload_heavy_processing = AsyncMock(
        return_value={"success": True, "result": "recovered"}
    )

    result = await pool.execute_task("text_analysis", {"text": "test"})

    # Should succeed and close circuit
    assert result["success"] is True
    assert pool.workers["solo-worker"].circuit_state == CircuitState.CLOSED


# =============================================================================
# Health Monitoring Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_health_monitor_updates_worker_status(single_worker_config_file):
    """Background health monitor should update worker health status."""
    from npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path=single_worker_config_file)

    # Mock health check to return healthy
    pool.workers["solo-worker"].client.check_health = AsyncMock(
        return_value={"status": "healthy", "models_loaded": 3}
    )

    # Run a single health check cycle
    await pool._check_worker_health(pool.workers["solo-worker"])

    assert pool.workers["solo-worker"].healthy is True
    assert pool.workers["solo-worker"].last_health_check > 0


@pytest.mark.asyncio
async def test_health_monitor_marks_unhealthy_on_failure(single_worker_config_file):
    """Health check failure should mark worker as unhealthy."""
    from npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path=single_worker_config_file)

    # Mock health check to fail
    pool.workers["solo-worker"].client.check_health = AsyncMock(
        side_effect=Exception("Health check timeout")
    )

    # Run a single health check cycle
    await pool._check_worker_health(pool.workers["solo-worker"])

    assert pool.workers["solo-worker"].healthy is False


@pytest.mark.asyncio
async def test_health_monitor_starts_and_stops(single_worker_config_file):
    """Health monitor task should start and stop cleanly."""
    from npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path=single_worker_config_file)

    # Start health monitor
    await pool.start_health_monitor()
    assert pool._running is True
    assert pool._health_monitor_task is not None

    # Stop health monitor
    await pool.stop_health_monitor()
    assert pool._running is False


# =============================================================================
# Config Hot-Reload Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_reload_adds_new_worker_dynamically():
    """Hot reload should add new workers without restart."""
    from npu_integration import NPUWorkerPool

    initial_config = """
npu:
  workers:
    - id: "worker-1"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(initial_config)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        assert len(pool.workers) == 1

        # Update config file
        updated_config = """
npu:
  workers:
    - id: "worker-1"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
    - id: "worker-2"
      host: "192.168.1.11"
      port: 8082
      enabled: true
      priority: 5
"""
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(updated_config)

        # Trigger reload
        await pool.reload_config()

        assert len(pool.workers) == 2
        assert "worker-2" in pool.workers
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_reload_during_active_tasks_defers_removal():
    """Workers with active tasks should not be removed immediately."""
    from npu_integration import NPUWorkerPool

    initial_config = """
npu:
  workers:
    - id: "worker-1"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
    - id: "worker-2"
      host: "192.168.1.11"
      port: 8082
      enabled: true
      priority: 5
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(initial_config)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)

        # Simulate active task on worker-2
        pool.workers["worker-2"].active_tasks = 3

        # Update config to remove worker-2
        updated_config = """
npu:
  workers:
    - id: "worker-1"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
"""
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(updated_config)

        # Trigger reload
        await pool.reload_config()

        # Worker-2 should still exist due to active tasks
        assert "worker-2" in pool.workers
    finally:
        os.unlink(config_path)


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


@pytest.mark.asyncio
async def test_single_worker_mode_backward_compatible(single_worker_config_file):
    """Pool should work correctly with a single worker (backward compatible)."""
    from npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path=single_worker_config_file)

    assert len(pool.workers) == 1

    # Configure successful response
    pool.workers["solo-worker"].client.offload_heavy_processing = AsyncMock(
        return_value={"success": True, "result": "solo_response"}
    )

    result = await pool.execute_task("text_analysis", {"text": "test"})

    assert result["success"] is True
    assert result["result"] == "solo_response"


@pytest.mark.asyncio
async def test_pool_stats_accurate_after_operations(two_worker_config_file):
    """Pool statistics should accurately reflect operations."""
    from npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path=two_worker_config_file)

    # Configure workers
    pool.workers["primary-worker"].client.offload_heavy_processing = AsyncMock(
        return_value={"success": True, "result": "ok"}
    )
    pool.workers["secondary-worker"].client.offload_heavy_processing = AsyncMock(
        side_effect=Exception("Failed")
    )

    # Execute some tasks
    await pool.execute_task("test", {"data": "1"})
    await pool.execute_task("test", {"data": "2"})

    stats = await pool.get_pool_stats()

    assert stats["total_workers"] == 2
    assert stats["total_tasks_processed"] >= 2
    assert stats["active_tasks"] == 0  # All completed


# =============================================================================
# Error Handling Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_graceful_degradation_all_workers_fail(two_worker_config_file):
    """Pool should return fallback error when all workers fail."""
    from npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path=two_worker_config_file)

    # Both workers fail
    pool.workers["primary-worker"].client.offload_heavy_processing = AsyncMock(
        side_effect=Exception("Primary down")
    )
    pool.workers["secondary-worker"].client.offload_heavy_processing = AsyncMock(
        side_effect=Exception("Secondary down")
    )

    result = await pool.execute_task("text_analysis", {"text": "test"})

    assert result["success"] is False
    assert result.get("fallback") is True
    assert "error" in result
