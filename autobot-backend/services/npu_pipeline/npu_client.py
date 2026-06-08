# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU pipeline client — async interface for dispatching requests to NPU workers.

Wraps the HTTP layer so callers can invoke partial_forward without dealing
with serialisation or transport details.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 30


class NPUWorkerError(Exception):
    """Raised when an NPU worker returns an error or is unreachable."""


class NPUClient:
    """Async HTTP client for a single NPU worker node.

    Usage::

        async with NPUClient("http://worker-0:8080") as client:
            result = await client.partial_forward(
                model_id="llama-7b",
                layer_range=(0, 15),
                hidden_state_in={"tokens": [1, 2, 3]},
            )
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = _DEFAULT_TIMEOUT_S,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> "NPUClient":
        if self._owns_session:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def partial_forward(
        self,
        model_id: str,
        layer_range: Tuple[int, int],
        hidden_state_in: Any,
    ) -> Dict[str, Any]:
        """Send a partial-forward request to this worker.

        Sends ``{model_id, layer_start, layer_end, hidden_state}`` to
        ``POST /partial_forward`` and returns the JSON response body.

        For the last worker in the pipeline the response contains
        ``token_ids``; intermediate workers return ``hidden_state_out``.

        Args:
            model_id: The model identifier the worker should use.
            layer_range: (start, end) inclusive layer range to execute.
            hidden_state_in: Activations from the previous pipeline stage.

        Returns:
            Dict with ``hidden_state_out`` (intermediate) or
            ``token_ids`` (last worker).

        Raises:
            NPUWorkerError: On HTTP error or unexpected response.
        """
        layer_start, layer_end = layer_range
        payload = {
            "model_id": model_id,
            "layer_start": layer_start,
            "layer_end": layer_end,
            "hidden_state": hidden_state_in,
        }

        url = f"{self._base_url}/partial_forward"
        logger.debug(
            "NPUClient: POST %s model=%s layers=[%d-%d]",
            url,
            model_id,
            layer_start,
            layer_end,
        )

        session = self._get_session()
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise NPUWorkerError(f"Worker at {self._base_url} returned HTTP {resp.status}: {body}")
                data: Dict[str, Any] = await resp.json()
        except aiohttp.ClientError as exc:
            raise NPUWorkerError(f"Network error reaching {self._base_url}: {exc}") from exc

        return data

    async def get_capabilities(self) -> Dict[str, Any]:
        """Fetch this worker's reported hardware capabilities.

        Returns:
            Dict with ``max_layers``, ``vram_bytes_per_layer``, ``device``.

        Raises:
            NPUWorkerError: On HTTP error or unreachable worker.
        """
        url = f"{self._base_url}/capabilities"
        logger.debug("NPUClient: GET %s", url)

        session = self._get_session()
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise NPUWorkerError(f"Worker at {self._base_url} returned HTTP {resp.status}: {body}")
                return await resp.json()
        except aiohttp.ClientError as exc:
            raise NPUWorkerError(f"Network error reaching {self._base_url}: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError(
                "NPUClient used outside of an async context manager. " "Use `async with NPUClient(...) as client:`."
            )
        return self._session


async def batch_partial_forward(
    worker_url: str,
    requests: List[Dict[str, Any]],
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> List[Dict[str, Any]]:
    """Fire multiple partial_forward calls to the same worker concurrently.

    Each element of ``requests`` must have keys ``model_id``,
    ``layer_range`` (tuple), and ``hidden_state_in``.

    Returns results in the same order as the input.
    """
    import asyncio

    async with NPUClient(worker_url, timeout=timeout) as client:
        tasks = [
            client.partial_forward(
                r["model_id"],
                r["layer_range"],
                r["hidden_state_in"],
            )
            for r in requests
        ]
        return list(await asyncio.gather(*tasks))
