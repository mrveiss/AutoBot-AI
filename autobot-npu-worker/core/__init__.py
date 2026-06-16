# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot NPU Worker Core Module

Extracted NPU integration code from autobot-backend in Phase 2+ refactoring (Issue #4311).
Provides high-performance processing using NPU workers for heavy computational tasks.
"""

from npu_integration import (  # noqa: F401
    CircuitState,
    NPUInferenceRequest,
    NPUTaskQueue,
    NPUWorkerClient,
    NPUWorkerPool,
    WorkerState,
    get_npu_client,
    get_npu_pool,
    get_npu_queue,
    load_worker_config,
    process_with_npu_fallback,
)

__all__ = [
    "CircuitState",
    "NPUInferenceRequest",
    "NPUTaskQueue",
    "NPUWorkerClient",
    "NPUWorkerPool",
    "WorkerState",
    "get_npu_client",
    "get_npu_pool",
    "get_npu_queue",
    "load_worker_config",
    "process_with_npu_fallback",
]
