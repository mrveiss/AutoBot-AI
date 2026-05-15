# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for NPU Worker Pool (#168)"""

import os
import tempfile

from npu_integration import CircuitState, NPUWorkerClient, WorkerState


def test_circuit_state_enum_values():
    """Circuit breaker should have three states"""
    assert CircuitState.CLOSED.value == "closed"
    assert CircuitState.OPEN.value == "open"
    assert CircuitState.HALF_OPEN.value == "half_open"


def test_worker_state_initialization():
    """WorkerState should initialize with correct defaults"""
    client = NPUWorkerClient("http://test:8081")
    state = WorkerState(worker_id="test-1", client=client)

    assert state.worker_id == "test-1"
    assert state.client == client
    assert state.active_tasks == 0
    assert state.total_requests == 0
    assert state.failures == 0
    assert state.healthy is True
    assert state.circuit_state == CircuitState.CLOSED
    assert state.circuit_open_until == 0


# =============================================================================
# Task 2: Configuration Loader Tests
# =============================================================================


def test_load_worker_config_success():
    """Configuration loader should parse valid YAML config"""
    # Import here to test after implementation
    from npu_integration import load_worker_config

    config_content = """
npu:
  workers:
    - id: "test-worker-1"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
      max_concurrent: 5
    - id: "test-worker-2"
      host: "192.168.1.11"
      port: 8082
      enabled: false
      priority: 5
      max_concurrent: 3
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(config_content)
        config_path = f.name

    try:
        workers = load_worker_config(config_path)
        assert len(workers) == 2
        assert workers[0]["id"] == "test-worker-1"
        assert workers[0]["url"] == "http://192.168.1.10:8081"
        assert workers[0]["enabled"] is True
        assert workers[0]["priority"] == 10
        assert workers[1]["id"] == "test-worker-2"
        assert workers[1]["enabled"] is False
    finally:
        os.unlink(config_path)


def test_load_worker_config_missing_file():
    """Configuration loader should return empty list for missing file"""
    from npu_integration import load_worker_config

    workers = load_worker_config("/nonexistent/path/config.yaml")
    assert workers == []


def test_load_worker_config_validation():
    """Configuration loader should validate required fields"""
    from npu_integration import load_worker_config

    # Missing required 'id' field
    config_content = """
npu:
  workers:
    - host: "192.168.1.10"
      port: 8081
      enabled: true
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(config_content)
        config_path = f.name

    try:
        workers = load_worker_config(config_path)
        # Invalid workers should be skipped
        assert len(workers) == 0
    finally:
        os.unlink(config_path)


# =============================================================================
# Task 3: NPUWorkerPool Initialization Tests
# =============================================================================


def test_worker_pool_initialization_with_config():
    """NPUWorkerPool should initialize workers from config"""

    from npu_integration import NPUWorkerPool

    config_content = """
npu:
  workers:
    - id: "pool-worker-1"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
    - id: "pool-worker-2"
      host: "192.168.1.11"
      port: 8082
      enabled: true
      priority: 5
    - id: "disabled-worker"
      host: "192.168.1.12"
      port: 8083
      enabled: false
      priority: 1
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        # Only enabled workers should be initialized
        assert len(pool.workers) == 2
        assert "pool-worker-1" in pool.workers
        assert "pool-worker-2" in pool.workers
        assert "disabled-worker" not in pool.workers
        # Check WorkerState is created correctly
        assert pool.workers["pool-worker-1"].worker_id == "pool-worker-1"
        assert pool.workers["pool-worker-1"].healthy is True
        assert pool.workers["pool-worker-1"].circuit_state == CircuitState.CLOSED
    finally:
        os.unlink(config_path)


def test_worker_pool_empty_config():
    """NPUWorkerPool should handle empty config gracefully"""
    from npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path="/nonexistent/config.yaml")
    assert len(pool.workers) == 0


# =============================================================================
# Task 4: Worker Selection Algorithm Tests
# =============================================================================

import pytest


@pytest.mark.asyncio
async def test_select_worker_priority_first():
    """Higher priority worker should be selected even if more loaded"""
    from npu_integration import NPUWorkerPool

    config_content = """
npu:
  workers:
    - id: "high-priority"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
    - id: "low-priority"
      host: "192.168.1.11"
      port: 8082
      enabled: true
      priority: 5
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        # Give high-priority more tasks
        pool.workers["high-priority"].active_tasks = 5
        pool.workers["low-priority"].active_tasks = 0

        # Should still select high-priority due to priority-first
        selected = await pool._select_worker(excluded_workers=set())
        assert selected is not None
        assert selected.worker_id == "high-priority"
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_select_worker_least_connections():
    """Within same priority, least loaded worker selected"""
    from npu_integration import NPUWorkerPool

    config_content = """
npu:
  workers:
    - id: "worker-a"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
    - id: "worker-b"
      host: "192.168.1.11"
      port: 8082
      enabled: true
      priority: 10
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        pool.workers["worker-a"].active_tasks = 5
        pool.workers["worker-b"].active_tasks = 2

        # Should select worker-b (fewer active tasks)
        selected = await pool._select_worker(excluded_workers=set())
        assert selected is not None
        assert selected.worker_id == "worker-b"
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_select_worker_excludes_workers():
    """Excluded workers should not be selected"""
    from npu_integration import NPUWorkerPool

    config_content = """
npu:
  workers:
    - id: "worker-a"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
    - id: "worker-b"
      host: "192.168.1.11"
      port: 8082
      enabled: true
      priority: 5
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)

        # Exclude high-priority worker
        selected = await pool._select_worker(excluded_workers={"worker-a"})
        assert selected is not None
        assert selected.worker_id == "worker-b"
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_select_worker_skips_open_circuit():
    """Workers with open circuit should not be selected"""
    from npu_integration import NPUWorkerPool

    config_content = """
npu:
  workers:
    - id: "worker-a"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
    - id: "worker-b"
      host: "192.168.1.11"
      port: 8082
      enabled: true
      priority: 5
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)

        # Open circuit on high-priority worker
        pool.workers["worker-a"].circuit_state = CircuitState.OPEN

        selected = await pool._select_worker(excluded_workers=set())
        assert selected is not None
        assert selected.worker_id == "worker-b"
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_select_worker_returns_none_when_all_excluded():
    """Should return None when all workers are excluded/unavailable"""
    from npu_integration import NPUWorkerPool

    config_content = """
npu:
  workers:
    - id: "worker-a"
      host: "192.168.1.10"
      port: 8081
      enabled: true
      priority: 10
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        selected = await pool._select_worker(excluded_workers={"worker-a"})
        assert selected is None
    finally:
        os.unlink(config_path)


# =============================================================================
# Task 5: Health Check Tests
# =============================================================================

import time
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_check_worker_health_updates_timestamp():
    """Health check should update last_health_check timestamp"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        worker = pool.workers["worker-1"]

        # Mock the client's check_health to return healthy
        worker.client.check_health = AsyncMock(return_value={"status": "healthy"})

        before = time.time()
        await pool._check_worker_health(worker)
        after = time.time()

        assert before <= worker.last_health_check <= after
        assert worker.healthy is True
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_check_worker_health_marks_unhealthy():
    """Health check should mark worker unhealthy on failure"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        worker = pool.workers["worker-1"]

        # Mock the client's check_health to return unhealthy
        worker.client.check_health = AsyncMock(
            return_value={"status": "unhealthy", "error": "Connection refused"}
        )

        await pool._check_worker_health(worker)

        assert worker.healthy is False
    finally:
        os.unlink(config_path)


# =============================================================================
# Task 6: Circuit Breaker Tests
# =============================================================================


def test_record_failure_increments_count():
    """Recording failure should increment failure count"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        worker = pool.workers["worker-1"]

        assert worker.failures == 0
        pool._record_failure(worker)
        assert worker.failures == 1
        pool._record_failure(worker)
        assert worker.failures == 2
    finally:
        os.unlink(config_path)


def test_record_failure_opens_circuit_after_threshold():
    """Circuit should open after 5 failures"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        worker = pool.workers["worker-1"]

        # 4 failures - circuit still closed
        for _ in range(4):
            pool._record_failure(worker)
        assert worker.circuit_state == CircuitState.CLOSED

        # 5th failure - circuit opens
        pool._record_failure(worker)
        assert worker.circuit_state == CircuitState.OPEN
        assert worker.circuit_open_until > time.time()
    finally:
        os.unlink(config_path)


def test_record_success_resets_failures():
    """Recording success should reset failure count"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        worker = pool.workers["worker-1"]

        worker.failures = 3
        pool._record_success(worker)
        assert worker.failures == 0
    finally:
        os.unlink(config_path)


def test_record_success_closes_circuit_from_half_open():
    """Success in half-open state should close circuit"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        worker = pool.workers["worker-1"]

        worker.circuit_state = CircuitState.HALF_OPEN
        pool._record_success(worker)
        assert worker.circuit_state == CircuitState.CLOSED
    finally:
        os.unlink(config_path)


def test_circuit_transitions_to_half_open_after_cooldown():
    """Open circuit should transition to half-open after cooldown"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        worker = pool.workers["worker-1"]

        # Set circuit to open with expired cooldown
        worker.circuit_state = CircuitState.OPEN
        worker.circuit_open_until = time.time() - 1  # Already expired

        # Check availability should transition to half-open
        is_available = pool._is_circuit_available(worker)
        assert is_available is True
        assert worker.circuit_state == CircuitState.HALF_OPEN
    finally:
        os.unlink(config_path)


# =============================================================================
# Task 7: Background Health Monitor Tests
# =============================================================================


@pytest.mark.asyncio
async def test_start_health_monitor():
    """Health monitor should start as background task"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        assert pool._health_monitor_task is None
        assert pool._running is False

        await pool.start_health_monitor()

        assert pool._health_monitor_task is not None
        assert pool._running is True

        await pool.stop_health_monitor()
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_stop_health_monitor():
    """Health monitor should stop gracefully"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        await pool.start_health_monitor()
        assert pool._running is True

        await pool.stop_health_monitor()

        assert pool._running is False
        assert pool._health_monitor_task is None
    finally:
        os.unlink(config_path)


# =============================================================================
# Task 8: Task Execution with Retry Tests
# =============================================================================


@pytest.mark.asyncio
async def test_execute_task_success():
    """execute_task should successfully execute task on selected worker"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)
        worker = pool.workers["worker-1"]

        # Mock successful task execution
        worker.client.offload_heavy_processing = AsyncMock(
            return_value={"success": True, "result": "test_data"}
        )

        result = await pool.execute_task("text_analysis", {"text": "hello"})

        assert result["success"] is True
        assert result["result"] == "test_data"
        assert worker.failures == 0
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_execute_task_retries_on_failure():
    """execute_task should retry on different worker after failure"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)

        # Worker 1 fails, Worker 2 succeeds
        pool.workers["worker-1"].client.offload_heavy_processing = AsyncMock(
            side_effect=Exception("Connection error")
        )
        pool.workers["worker-2"].client.offload_heavy_processing = AsyncMock(
            return_value={"success": True, "result": "fallback"}
        )

        result = await pool.execute_task("text_analysis", {"text": "hello"})

        assert result["success"] is True
        # Worker-1 should have a failure recorded
        assert pool.workers["worker-1"].failures == 1
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_execute_task_returns_error_when_all_fail():
    """execute_task should return error when all workers fail"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)

        # Worker fails on all attempts
        pool.workers["worker-1"].client.offload_heavy_processing = AsyncMock(
            side_effect=Exception("Connection error")
        )

        result = await pool.execute_task("text_analysis", {"text": "hello"})

        assert result["success"] is False
        assert "error" in result
        assert result.get("fallback") is True
    finally:
        os.unlink(config_path)


# =============================================================================
# Task 9: Global Singleton Functions Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_npu_pool_returns_singleton():
    """get_npu_pool should return the same instance"""
    import npu_integration as npu_module

    # Reset global state
    npu_module._npu_pool = None

    pool1 = await npu_module.get_npu_pool()
    pool2 = await npu_module.get_npu_pool()

    assert pool1 is pool2
    assert isinstance(pool1, npu_module.NPUWorkerPool)

    # Cleanup
    npu_module._npu_pool = None


# =============================================================================
# Task 10: Pool Management Methods Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_pool_stats_returns_metrics():
    """get_pool_stats should return pool metrics"""
    from npu_integration import NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)

        # Simulate some activity
        pool.workers["worker-1"].total_requests = 100
        pool.workers["worker-1"].failures = 5
        pool.workers["worker-2"].total_requests = 50
        pool.workers["worker-2"].failures = 2
        pool.workers["worker-1"].active_tasks = 3

        stats = await pool.get_pool_stats()

        assert stats["total_workers"] == 2
        assert stats["healthy_workers"] == 2
        assert stats["total_tasks_processed"] == 150
        assert stats["active_tasks"] == 3
        assert stats["success_rate"] > 0
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_get_pool_stats_with_unhealthy_workers():
    """get_pool_stats should count healthy workers correctly"""
    import time

    from npu_integration import CircuitState, NPUWorkerPool

    config_content = """
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
        f.write(config_content)
        config_path = f.name

    try:
        pool = NPUWorkerPool(config_path=config_path)

        # Mark one worker as unhealthy via circuit breaker
        # Set circuit_open_until to future time so it stays OPEN
        pool.workers["worker-1"].circuit_state = CircuitState.OPEN
        pool.workers["worker-1"].circuit_open_until = time.time() + 3600  # 1 hour

        stats = await pool.get_pool_stats()

        assert stats["total_workers"] == 2
        assert stats["healthy_workers"] == 1  # Only worker-2 is healthy
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_reload_config_adds_new_worker():
    """reload_config should add new workers from config"""
    from npu_integration import NPUWorkerPool

    # Initial config with one worker
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

        # Update config file with additional worker
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

        await pool.reload_config()

        assert len(pool.workers) == 2
        assert "worker-2" in pool.workers
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_reload_config_removes_worker():
    """reload_config should remove workers no longer in config"""
    from npu_integration import NPUWorkerPool

    # Initial config with two workers
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
        assert len(pool.workers) == 2

        # Update config file with only one worker
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

        await pool.reload_config()

        assert len(pool.workers) == 1
        assert "worker-2" not in pool.workers
    finally:
        os.unlink(config_path)


@pytest.mark.asyncio
async def test_reload_config_updates_existing_worker():
    """reload_config should update existing workers"""
    from npu_integration import NPUWorkerPool

    # Initial config with priority 5
    initial_config = """
npu:
  workers:
    - id: "worker-1"
      host: "192.168.1.10"
      port: 8081
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
        # Priority is stored in _worker_configs, not on WorkerState
        assert pool._worker_configs["worker-1"]["priority"] == 5

        # Update config file with higher priority
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

        await pool.reload_config()

        # Priority should be updated in _worker_configs
        assert pool._worker_configs["worker-1"]["priority"] == 10
    finally:
        os.unlink(config_path)
