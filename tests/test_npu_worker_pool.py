# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for NPU Worker Pool (#168)"""


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
