# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Message Queue with Per-Platform Rate Limiting

Queues messages and respects platform-specific rate limits (Slack 1/sec, Discord 10/sec, etc).
Provides async processing with burst support.

Delegates to the shared ``autobot_shared.rate_limiter.RateLimiter`` — its
in-process token-bucket mode (``acquire_token``) provides the per-platform
burst/throughput control (Issue #4460, folded onto the canonical limiter in
Issue #12646; previously a local token-bucket ``RateLimiter`` dataclass).
"""

import asyncio
from asyncio import Queue
from typing import Callable, Dict, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.rate_limiter import RateLimiter as _SharedRateLimiter

logger = get_logger(__name__)

# Shared delegate scoped to gateway operations (Issue #4460 / #12646).
# acquire_token() provides the per-platform token-bucket burst/throughput
# control; register_platform() below stores each platform's (rps, burst)
# and passes them through on every acquire.
gateway_rate_limiter = _SharedRateLimiter(
    scope_prefix="gateway",
    default_tier="privileged",
)


class MessageQueue:
    """
    Async message queue with per-platform rate limiting.

    Normalizes and routes messages through platform adapters while respecting
    platform-specific rate limits.
    """

    def __init__(self, max_queue_size: int = 10000) -> None:
        """Initialize message queue."""
        self.queue: Queue = Queue(maxsize=max_queue_size)
        self.platform_limits: Dict[str, Tuple[float, float]] = {}
        self.processing = False
        self.logger = get_logger(__name__)

    def register_platform(self, platform: str, rps: int, burst_size: int) -> None:
        """Register platform rate limit (requests/sec, burst size)."""
        self.platform_limits[platform] = (rps, burst_size)
        self.logger.info(f"Registered platform {platform}: {rps} req/s, burst {burst_size}")

    async def enqueue(self, message: Dict) -> None:
        """
        Enqueue a message for processing.

        Args:
            message: Message dict with platform info
        """
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            self.logger.error("Message queue full, dropping message")

    async def process_queue(self, handler: Callable[[Dict], None], workers: int = 5) -> None:
        """
        Process queued messages with multiple workers and rate limiting.

        Args:
            handler: Async handler function to call for each message
            workers: Number of concurrent workers
        """
        self.processing = True
        worker_tasks = [asyncio.create_task(self._worker(handler, i)) for i in range(workers)]

        try:
            await asyncio.gather(*worker_tasks)
        finally:
            self.processing = False

    async def _worker(self, handler: Callable, worker_id: int) -> None:
        """Worker coroutine for processing messages."""
        while self.processing:
            try:
                message = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                platform = message.get("platform", "unknown")

                limits = self.platform_limits.get(platform)
                if limits:
                    rps, burst_size = limits
                    await gateway_rate_limiter.acquire_token(platform, requests_per_second=rps, burst_size=burst_size)

                await handler(message)
                self.queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(
                    f"Worker {worker_id} error processing message: {e}",
                    exc_info=True,
                )

    async def drain(self) -> None:
        """Wait for queue to be fully processed."""
        await self.queue.join()

    async def shutdown(self) -> None:
        """Shutdown the queue."""
        self.processing = False
        await self.drain()
