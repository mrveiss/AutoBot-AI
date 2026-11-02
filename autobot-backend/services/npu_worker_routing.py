# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which NPU workers a request may go to, and in what order (#19706).

The worker registry (``NPUWorkerManager``) knows every paired worker and its health. Requests
used to go to one configured URL whatever the registry said, so a second worker got no traffic.
"""

from itertools import count, takewhile
from typing import Any, Dict, List

import aiohttp

from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_request_counter = count()


def _spread(workers: List[Any]) -> List[Any]:
    """Take turns among the workers tied for first place, so equal workers share the traffic."""
    if not workers:
        return workers

    def rank(worker: Any) -> tuple:
        return (worker.status.status, worker.config.priority, worker.status.current_load)

    tied = list(takewhile(lambda w: rank(w) == rank(workers[0]), workers))
    start = next(_request_counter) % len(tied)
    return tied[start:] + tied[:start] + workers[len(tied) :]


async def npu_worker_urls(configured_url: str) -> List[str]:
    """Healthy paired workers in dispatch order, then the configured URL.

    Only the registry this process already runs is read. Starting one here would start its
    health monitors in every process that embeds text, so such a process keeps using the
    configured URL. A registry failure must not stop a request the configured URL could serve.
    """
    from services import npu_worker_manager

    manager = npu_worker_manager._worker_manager
    if manager is None:
        return [configured_url]
    try:
        workers = await manager.get_healthy_workers_sorted()
    except Exception as exc:
        logger.warning("NPU worker registry unreadable, using the configured URL: %s", exc)
        return [configured_url]
    urls = [w.config.url.rstrip("/") for w in _spread(workers)]
    return urls if configured_url in urls else [*urls, configured_url]


async def _post_inference(url: str, request_data: Dict[str, Any], timeout_seconds: float) -> Dict[str, Any]:
    """Run one inference on one worker."""
    http_client = get_http_client()
    async with await http_client.post(
        f"{url}/inference",
        json=request_data,
        timeout=aiohttp.ClientTimeout(total=timeout_seconds),
    ) as response:
        if response.status != 200:
            raise RuntimeError(f"NPU Worker HTTP error: {response.status}")
        result_data = await response.json()
    if result_data.get("status") != "completed":
        raise RuntimeError(f"NPU processing failed: {result_data.get('error')}")
    return result_data.get("result", {})


async def post_inference_with_failover(
    configured_url: str, request_data: Dict[str, Any], timeout_seconds: float
) -> Dict[str, Any]:
    """Run an inference on the first worker that completes it; raise the last error if none does."""
    urls = await npu_worker_urls(configured_url)
    for url in urls[:-1]:
        try:
            return await _post_inference(url, request_data, timeout_seconds)
        except Exception as exc:
            logger.warning("NPU worker %s failed, trying the next one: %s", url, exc)
    return await _post_inference(urls[-1], request_data, timeout_seconds)
