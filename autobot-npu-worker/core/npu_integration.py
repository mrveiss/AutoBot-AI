# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""NPU worker integration — worker entry points (#12656).

The pool/client/queue implementation moved to ``autobot_shared.npu``. This file
and ``autobot-backend/npu_integration.py`` were forked copies of the same ~1000
lines; six of the seven shared symbols were byte-identical, and the seventh had
drifted in a way that hid a live defect (#12910 — this copy awaited a sync
``get_http_client``). One definition now, so a fix lands once.

``autobot_shared`` is a declared dependency of this worker (``-e ../autobot_shared``
in requirements.txt), so the import is expected to succeed here. Re-exported so
every existing ``from core.npu_integration import X`` keeps working; the lazy
singletons below stay worker-side, since they are this process's instances.
"""

import asyncio

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import CircuitState  # noqa: F401  (#12656: re-exported for callers)
from autobot_shared.npu import (  # noqa: F401
    USE_AUTHENTICATED_CLIENT,
    NPUInferenceRequest,
    NPUTaskQueue,
    NPUWorkerClient,
    NPUWorkerPool,
    WorkerState,
    get_service_url,
    load_worker_config,
    process_with_npu_fallback as _shared_process_with_npu_fallback,
)

logger = get_logger(__name__)

_npu_client = None
_npu_queue = None
_npu_pool = None
_npu_client_lock = asyncio.Lock()
_npu_queue_lock = asyncio.Lock()
_npu_pool_lock = asyncio.Lock()


async def get_npu_client() -> NPUWorkerClient:
    """Get or create global NPU client instance (thread-safe)"""
    global _npu_client
    if _npu_client is None:
        async with _npu_client_lock:
            # Double-check after acquiring lock
            if _npu_client is None:
                _npu_client = NPUWorkerClient()
                await _npu_client.check_health()
    return _npu_client


async def get_npu_pool() -> NPUWorkerPool:
    """
    Get or create global NPU worker pool instance (thread-safe).

    Issue #168: The pool provides load-balanced access to multiple NPU workers
    with automatic failover, health monitoring, and circuit breaker protection.

    Returns:
        NPUWorkerPool singleton instance
    """
    global _npu_pool
    if _npu_pool is None:
        async with _npu_pool_lock:
            # Double-check after acquiring lock
            if _npu_pool is None:
                _npu_pool = NPUWorkerPool()
                await _npu_pool.start_health_monitor()
                logger.info("NPU worker pool initialized (Issue #168)")
    return _npu_pool


async def get_npu_queue() -> NPUTaskQueue:
    """Get or create global NPU task queue (thread-safe)"""
    global _npu_queue
    if _npu_queue is None:
        async with _npu_queue_lock:
            # Double-check after acquiring lock
            if _npu_queue is None:
                client = await get_npu_client()
                _npu_queue = NPUTaskQueue(client)
    return _npu_queue


async def process_with_npu_fallback(task_type, data, fallback_func):
    """Public signature unchanged; binds this process's queue singleton (#12656)."""
    return await _shared_process_with_npu_fallback(task_type, data, fallback_func, queue_getter=get_npu_queue)
