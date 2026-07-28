# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""NPU worker integration — backend entry points (#12656).

The pool/client/queue implementation moved to ``autobot_shared.npu`` so the
backend and the npu-worker share one definition instead of two that drift
(#12645). Six of the seven symbols were byte-identical; the seventh had drifted
in a way that concealed a live defect (#12910).

Re-exported here so every existing ``from npu_integration import X`` keeps
working. The lazy singleton accessors below stay backend-side: they are this
process's instances, not shared state.
"""

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import CircuitState  # noqa: F401  (#12656: re-exported for callers)
from autobot_shared.singleton_factory import async_lazy_singleton
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


async def _init_npu_client() -> NPUWorkerClient:
    client = NPUWorkerClient()
    await client.check_health()
    return client


async def _init_npu_pool() -> NPUWorkerPool:
    pool = NPUWorkerPool()
    await pool.start_health_monitor()
    logger.info("NPU worker pool initialized (Issue #168)")
    return pool


async def _init_npu_queue() -> NPUTaskQueue:
    return NPUTaskQueue(await get_npu_client())


get_npu_client = async_lazy_singleton(_init_npu_client)
get_npu_pool = async_lazy_singleton(_init_npu_pool)
get_npu_queue = async_lazy_singleton(_init_npu_queue)


async def process_with_npu_fallback(task_type, data, fallback_func):
    """Public signature unchanged; binds this process's queue singleton (#12656)."""
    return await _shared_process_with_npu_fallback(task_type, data, fallback_func, queue_getter=get_npu_queue)
