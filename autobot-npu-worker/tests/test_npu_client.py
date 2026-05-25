# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for NPUClient.partial_forward (MVA-1098)."""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

import pytest

_repo_root = Path(__file__).resolve().parent.parent.parent
_npu_pipeline_path = _repo_root / "autobot-backend" / "services" / "npu_pipeline"
sys.path.insert(0, str(_npu_pipeline_path))
from npu_client import NPUClient, NPUWorkerError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(status: int, body: Dict[str, Any]) -> MagicMock:
    """Return a mock aiohttp response with __aenter__/__aexit__ support."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=body)
    resp.text = AsyncMock(return_value=json.dumps(body))
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_mock_session(response: MagicMock) -> MagicMock:
    session = MagicMock()
    session.post = MagicMock(return_value=response)
    session.get = MagicMock(return_value=response)
    session.close = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# NPUClient.partial_forward
# ---------------------------------------------------------------------------


class TestNPUClientPartialForward:
    @pytest.mark.asyncio
    async def test_posts_to_correct_endpoint(self):
        body = {"hidden_state_out": {"layers_run": [0, 1]}}
        resp = _make_mock_response(200, body)
        session = _make_mock_session(resp)

        client = NPUClient("http://worker:8080", session=session)
        result = await client.partial_forward(
            model_id="llama-7b",
            layer_range=(0, 1),
            hidden_state_in={"tokens": [1, 2, 3]},
        )

        session.post.assert_called_once()
        call_args = session.post.call_args
        assert call_args[0][0] == "http://worker:8080/partial_forward"
        payload = call_args[1]["json"]
        assert payload["model_id"] == "llama-7b"
        assert payload["layer_start"] == 0
        assert payload["layer_end"] == 1
        assert result == body

    @pytest.mark.asyncio
    async def test_returns_token_ids_from_last_worker(self):
        body = {"token_ids": [42]}
        resp = _make_mock_response(200, body)
        session = _make_mock_session(resp)

        client = NPUClient("http://worker:8080", session=session)
        result = await client.partial_forward(
            model_id="llama-7b",
            layer_range=(16, 31),
            hidden_state_in={"act": [0.5]},
        )
        assert result["token_ids"] == [42]

    @pytest.mark.asyncio
    async def test_raises_on_non_200(self):
        resp = _make_mock_response(500, {"error": "internal"})
        session = _make_mock_session(resp)

        client = NPUClient("http://worker:8080", session=session)
        with pytest.raises(NPUWorkerError, match="HTTP 500"):
            await client.partial_forward(
                model_id="llama-7b",
                layer_range=(0, 7),
                hidden_state_in={},
            )

    @pytest.mark.asyncio
    async def test_raises_on_network_error(self):
        import aiohttp

        session = MagicMock()
        err_resp = MagicMock()
        err_resp.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectorError(
            MagicMock(), OSError("refused")
        ))
        err_resp.__aexit__ = AsyncMock(return_value=False)
        session.post = MagicMock(return_value=err_resp)

        client = NPUClient("http://worker:8080", session=session)
        with pytest.raises(NPUWorkerError, match="Network error"):
            await client.partial_forward(
                model_id="llama-7b",
                layer_range=(0, 7),
                hidden_state_in={},
            )


# ---------------------------------------------------------------------------
# NPUClient.get_capabilities
# ---------------------------------------------------------------------------


class TestNPUClientGetCapabilities:
    @pytest.mark.asyncio
    async def test_fetches_capabilities(self):
        caps = {"max_layers": 32, "vram_bytes_per_layer": 268435456, "device": "NPU"}
        resp = _make_mock_response(200, caps)
        session = _make_mock_session(resp)

        client = NPUClient("http://worker:8080", session=session)
        result = await client.get_capabilities()

        session.get.assert_called_once()
        url = session.get.call_args[0][0]
        assert url == "http://worker:8080/capabilities"
        assert result == caps

    @pytest.mark.asyncio
    async def test_raises_on_non_200_capabilities(self):
        resp = _make_mock_response(503, {"error": "unavailable"})
        session = _make_mock_session(resp)

        client = NPUClient("http://worker:8080", session=session)
        with pytest.raises(NPUWorkerError, match="HTTP 503"):
            await client.get_capabilities()


# ---------------------------------------------------------------------------
# Context manager guard
# ---------------------------------------------------------------------------


class TestNPUClientContextGuard:
    @pytest.mark.asyncio
    async def test_raises_when_used_outside_context(self):
        client = NPUClient("http://worker:8080")
        with pytest.raises(RuntimeError, match="async context manager"):
            await client.partial_forward("m", (0, 0), {})
