# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cloud Request Batcher - Aggregates multiple requests for efficient API calls.

Unlike GPU continuous batching, cloud batching aggregates multiple user requests
within a time window, then sends batch API calls where supported.

Issue #717: Efficient Inference Design implementation.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class BatchedRequest:
    """A request waiting to be batched."""

    request_id: str
    payload: Dict[str, Any]
    future: asyncio.Future
    created_at: float = field(default_factory=time.time)


@dataclass
class BatchResult:
    """Result of a batched request."""

    request_id: str
    response: Optional[Dict[str, Any]] = None
    error: Optional[Exception] = None
    batch_id: str = ""
    batch_size: int = 0
    wait_time_ms: float = 0.0


class CloudRequestBatcher:
    """
    Batch multiple requests to cloud providers for efficiency.

    Aggregates requests within a time window, then sends batch API calls
    where supported (OpenAI Batch API, etc.). For providers without batch
    support, sends concurrent requests.

    Typical usage:
        batcher = CloudRequestBatcher(batch_window_ms=50, max_batch_size=10)
        response = await batcher.add_request(request_payload)
    """

    def __init__(
        self,
        batch_window_ms: int = 50,
        max_batch_size: int = 10,
        executor: Optional[Callable[[List[Dict]], Coroutine[Any, Any, List]]] = None,
    ):
        """
        Initialize the cloud request batcher.

        Args:
            batch_window_ms: Time to wait for additional requests before sending
            max_batch_size: Maximum requests per batch
            executor: Async function to execute batch (receives list of payloads)
        """
        self.batch_window_ms = batch_window_ms
        self.max_batch_size = max_batch_size
        self._executor = executor

        self._pending_requests: List[BatchedRequest] = []
        self._lock = asyncio.Lock()
        self._batch_task: Optional[asyncio.Task] = None
        self._shutdown = False

        # Metrics
        self._metrics = {
            "batches_sent": 0,
            "requests_batched": 0,
            "avg_batch_size": 0.0,
            "avg_wait_time_ms": 0.0,
        }

        logger.info(
            "CloudRequestBatcher initialized: window=%dms, max_size=%d",
            batch_window_ms,
            max_batch_size,
        )

    def set_executor(
        self, executor: Callable[[List[Dict]], Coroutine[Any, Any, List]]
    ) -> None:
        """
        Set the batch executor function.

        Args:
            executor: Async function that takes list of payloads and returns responses
        """
        self._executor = executor

    async def add_request(self, payload: Dict[str, Any]) -> BatchResult:
        """
        Add a request to the batch queue.

        The request will be batched with others and executed when either:
        1. batch_window_ms expires, OR
        2. max_batch_size is reached

        Args:
            payload: The request payload to batch

        Returns:
            BatchResult with response or error
        """
        if self._shutdown:
            raise RuntimeError("Batcher is shutting down")

        request_id = str(uuid4())
        future = asyncio.get_event_loop().create_future()
        batched_request = BatchedRequest(
            request_id=request_id, payload=payload, future=future
        )

        async with self._lock:
            self._pending_requests.append(batched_request)

            # Check if we should trigger immediate batch
            if len(self._pending_requests) >= self.max_batch_size:
                asyncio.create_task(self._execute_batch())
            elif self._batch_task is None or self._batch_task.done():
                # Schedule batch execution after window
                self._batch_task = asyncio.create_task(self._wait_and_execute())

        # Wait for result
        return await future

    async def _wait_and_execute(self) -> None:
        """Wait for batch window then execute."""
        await asyncio.sleep(self.batch_window_ms / 1000.0)
        await self._execute_batch()

    async def _execute_batch(self) -> None:
        """Execute pending batch of requests."""
        async with self._lock:
            if not self._pending_requests:
                return

            # Take all pending requests
            requests = self._pending_requests.copy()
            self._pending_requests.clear()

        if not requests:
            return

        batch_id = str(uuid4())[:8]
        batch_size = len(requests)
        start_time = time.time()

        logger.debug("Executing batch %s with %d requests", batch_id, batch_size)

        try:
            if self._executor:
                # Execute batch using provided executor
                payloads = [r.payload for r in requests]
                responses = await self._executor(payloads)

                # Match responses to requests
                for i, request in enumerate(requests):
                    wait_time = (time.time() - request.created_at) * 1000
                    result = BatchResult(
                        request_id=request.request_id,
                        response=responses[i] if i < len(responses) else None,
                        batch_id=batch_id,
                        batch_size=batch_size,
                        wait_time_ms=wait_time,
                    )
                    if not request.future.done():
                        request.future.set_result(result)
            else:
                # No executor - fail all requests
                error = RuntimeError("No batch executor configured")
                for request in requests:
                    result = BatchResult(
                        request_id=request.request_id,
                        error=error,
                        batch_id=batch_id,
                        batch_size=batch_size,
                    )
                    if not request.future.done():
                        request.future.set_result(result)

        except Exception as e:
            logger.error("Batch %s execution failed: %s", batch_id, e)
            # Fail all requests in batch
            for request in requests:
                result = BatchResult(
                    request_id=request.request_id,
                    error=e,
                    batch_id=batch_id,
                    batch_size=batch_size,
                )
                if not request.future.done():
                    request.future.set_result(result)

        # Update metrics
        execution_time = (time.time() - start_time) * 1000
        self._update_metrics(batch_size, execution_time)

    def _update_metrics(self, batch_size: int, wait_time_ms: float) -> None:
        """Update batching metrics."""
        self._metrics["batches_sent"] += 1
        self._metrics["requests_batched"] += batch_size

        # Rolling average for batch size
        total_batches = self._metrics["batches_sent"]
        self._metrics["avg_batch_size"] = (
            self._metrics["avg_batch_size"] * (total_batches - 1) + batch_size
        ) / total_batches

        self._metrics["avg_wait_time_ms"] = (
            self._metrics["avg_wait_time_ms"] * (total_batches - 1) + wait_time_ms
        ) / total_batches

    def get_metrics(self) -> Dict[str, Any]:
        """Get batching performance metrics."""
        return {
            **self._metrics,
            "pending_requests": len(self._pending_requests),
            "batch_window_ms": self.batch_window_ms,
            "max_batch_size": self.max_batch_size,
        }

    async def flush(self) -> None:
        """Force execution of all pending requests."""
        await self._execute_batch()

    async def shutdown(self) -> None:
        """Shutdown the batcher gracefully."""
        self._shutdown = True
        await self.flush()

        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass

        logger.info("CloudRequestBatcher shutdown complete")


__all__ = [
    "CloudRequestBatcher",
    "BatchedRequest",
    "BatchResult",
]
