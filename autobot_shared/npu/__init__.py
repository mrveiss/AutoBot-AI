# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared NPU worker integration (#12656, part of #12645)."""

from autobot_shared.npu.integration import (
    USE_AUTHENTICATED_CLIENT,
    NPUInferenceRequest,
    NPUTaskQueue,
    NPUWorkerClient,
    NPUWorkerPool,
    WorkerState,
    get_service_url,
    load_worker_config,
    process_with_npu_fallback,
)

__all__ = [
    "NPUInferenceRequest",
    "NPUTaskQueue",
    "NPUWorkerClient",
    "NPUWorkerPool",
    "USE_AUTHENTICATED_CLIENT",
    "WorkerState",
    "get_service_url",
    "load_worker_config",
    "process_with_npu_fallback",
]
