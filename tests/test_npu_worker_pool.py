# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for NPU Worker Pool (#168)"""

import os
import tempfile

from src.npu_integration import CircuitState, NPUWorkerClient, WorkerState


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
    from src.npu_integration import load_worker_config

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
    from src.npu_integration import load_worker_config

    workers = load_worker_config("/nonexistent/path/config.yaml")
    assert workers == []


def test_load_worker_config_validation():
    """Configuration loader should validate required fields"""
    from src.npu_integration import load_worker_config

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

    from src.npu_integration import NPUWorkerPool

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
    from src.npu_integration import NPUWorkerPool

    pool = NPUWorkerPool(config_path="/nonexistent/config.yaml")
    assert len(pool.workers) == 0
