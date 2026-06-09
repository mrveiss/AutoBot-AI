# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
PipelineDispatcher — cross-worker forward-pass coordinator.

Streams a prompt through the shard pipeline:
  1. POST hidden state to worker[0] with its layer range
  2. Stream the response hidden state to worker[1], and so on
  3. Last worker produces a token stream which is yielded to the caller

Worker-drop handling: if a worker fails mid-pass, the dispatcher looks for a
peer that has a cached shard covering the same layer range and retries there.
If no peer exists, raises WorkerDropError with a clear message.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional

import aiohttp

from autobot_shared.logging_manager import get_logger
from services.npu_pipeline.shard_planner import ShardAssignment

logger = get_logger(__name__)

WORKER_TIMEOUT_S = 30
FORWARD_PASS_PATH = "/forward"
TOKEN_STREAM_PATH = "/generate"


class WorkerDropError(Exception):
    """Raised when a worker drops mid-pass and no failover peer exists."""


@dataclass
class PipelinePlan:
    """Ordered list of shard assignments that describe one pipeline pass."""

    assignments: List[ShardAssignment]
    # Optional map of worker_id → peer worker_ids that hold the same shard
    peer_map: Dict[str, List[str]] = field(default_factory=dict)


class PipelineDispatcher:
    """Coordinate a forward pass across NPU workers.

    Usage::

        async with PipelineDispatcher(worker_urls) as d:
            async for token in d.run_pipeline(plan, prompt_tokens):
                print(token)
    """

    def __init__(
        self,
        worker_urls: Dict[str, str],
        timeout: float = WORKER_TIMEOUT_S,
    ) -> None:
        self._worker_urls = worker_urls  # worker_id → base URL
        self._timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "PipelineDispatcher":
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self._timeout))
        logger.debug("PipelineDispatcher: session opened")
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._session:
            await self._session.close()
            self._session = None
        logger.debug("PipelineDispatcher: session closed")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_pipeline(
        self,
        plan: PipelinePlan,
        prompt_tokens: List[int],
    ) -> AsyncIterator[str]:
        """Execute a full forward pass and yield tokens from the last worker.

        Args:
            plan: Ordered shard assignments with optional peer map.
            prompt_tokens: Tokenised prompt as a list of ints.

        Yields:
            Decoded tokens as strings from the final worker's token stream.

        Raises:
            WorkerDropError: When a worker fails and no failover peer exists.
            RuntimeError: When called outside an async context manager.
        """
        if self._session is None:
            raise RuntimeError("PipelineDispatcher must be used as an async context manager")

        assignments = plan.assignments
        if not assignments:
            raise ValueError("PipelinePlan.assignments must not be empty")

        hidden_state: object = {"tokens": prompt_tokens}

        for idx, assignment in enumerate(assignments):
            is_last = idx == len(assignments) - 1

            if is_last:
                # Last worker streams tokens
                async for token in self._stream_tokens(plan, assignment, hidden_state):
                    yield token
                return
            else:
                hidden_state = await self._forward_pass(plan, assignment, hidden_state)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _forward_pass(
        self,
        plan: PipelinePlan,
        assignment: ShardAssignment,
        hidden_state: object,
    ) -> object:
        """POST hidden state to a worker; return the resulting hidden state.

        Retries on peer workers from plan.peer_map on connection/timeout error.
        """
        candidates = [assignment.worker_id] + plan.peer_map.get(assignment.worker_id, [])

        last_exc: Optional[Exception] = None
        for worker_id in candidates:
            url = self._worker_url(worker_id, FORWARD_PASS_PATH)
            try:
                payload = {
                    "worker_id": worker_id,
                    "layer_start": assignment.layer_range.start,
                    "layer_end": assignment.layer_range.end,
                    "hidden_state": hidden_state,
                }
                async with self._session.post(url, json=payload) as resp:
                    resp.raise_for_status()
                    result = await resp.json()
                    logger.debug(
                        "forward_pass: worker=%s layers=%r ok",
                        worker_id,
                        assignment.layer_range,
                    )
                    return result["hidden_state"]
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                logger.warning(
                    "forward_pass: worker=%s failed (%s); trying next peer",
                    worker_id,
                    exc,
                )
                last_exc = exc

        raise WorkerDropError(
            f"Worker '{assignment.worker_id}' dropped mid-pass for layers "
            f"{assignment.layer_range!r} and no failover peer succeeded. "
            f"Last error: {last_exc}"
        )

    async def _stream_tokens(
        self,
        plan: PipelinePlan,
        assignment: ShardAssignment,
        hidden_state: object,
    ) -> AsyncIterator[str]:
        """POST to the last worker's /generate endpoint and stream tokens."""
        candidates = [assignment.worker_id] + plan.peer_map.get(assignment.worker_id, [])

        last_exc: Optional[Exception] = None
        for worker_id in candidates:
            url = self._worker_url(worker_id, TOKEN_STREAM_PATH)
            try:
                payload = {
                    "worker_id": worker_id,
                    "layer_start": assignment.layer_range.start,
                    "layer_end": assignment.layer_range.end,
                    "hidden_state": hidden_state,
                }
                async with self._session.post(url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.content:
                        token = line.decode().strip()
                        if token:
                            yield token
                return
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                logger.warning(
                    "stream_tokens: worker=%s failed (%s); trying next peer",
                    worker_id,
                    exc,
                )
                last_exc = exc

        raise WorkerDropError(
            f"Last worker '{assignment.worker_id}' dropped during token streaming "
            f"and no failover peer succeeded. Last error: {last_exc}"
        )

    def _worker_url(self, worker_id: str, path: str) -> str:
        base = self._worker_urls.get(worker_id)
        if not base:
            raise WorkerDropError(f"No URL registered for worker '{worker_id}'")
        return base.rstrip("/") + path
