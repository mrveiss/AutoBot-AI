# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests that generate_image's pooled HTTP calls carry a provider-sized timeout (#12979)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

_PATH = Path(__file__).resolve().parent / "generate_image.py"
# Not registered in sys.modules: nothing in the module needs it, and an entry
# nobody restores leaks into every later test in the session.
_spec = importlib.util.spec_from_file_location("gi_under_test", _PATH)
gi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gi)

from autobot_shared import generation_http_timeouts as gt  # noqa: E402


class _Resp:
    def __init__(self, payload: dict):
        self.status = 200
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Client:
    def __init__(self, payloads: list):
        self.calls: list = []
        self._payloads = list(payloads)

    def tracked_request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _Resp(self._payloads.pop(0))


@pytest.mark.asyncio
async def test_stability_generation_call_carries_long_timeout():
    client = _Client([{"artifacts": []}])
    with patch.dict("os.environ", {"STABILITY_API_KEY": "k"}), patch.object(gi, "get_http_client", lambda: client):
        await gi.GenerateImageTool()._generate_sd("a cat", "1024x1024", "", 1)
    ((_, _, kwargs),) = client.calls
    timeout = kwargs["timeout"]
    assert isinstance(timeout, aiohttp.ClientTimeout)
    assert timeout.total == gt.GENERATION_TIMEOUT_S
    assert timeout.sock_read == gt.GENERATION_TIMEOUT_S
    assert timeout.connect == gt.CONNECT_TIMEOUT_S


@pytest.mark.asyncio
async def test_flux_submit_and_poll_calls_carry_timeout():
    client = _Client([{"id": "t"}, {"status": "Ready", "result": {"sample": "u"}}])
    with (
        patch.dict("os.environ", {"FLUX_API_KEY": "k"}),
        patch.object(gi, "get_http_client", lambda: client),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = await gi.GenerateImageTool()._generate_flux("a cat", "1024x1024", "")
    assert result.success
    assert len(client.calls) == 2
    for _, _, kwargs in client.calls:
        assert isinstance(kwargs.get("timeout"), aiohttp.ClientTimeout)
        assert kwargs["timeout"].total == gt.POLL_TIMEOUT_S
        assert kwargs["timeout"].sock_read == gt.POLL_TIMEOUT_S
        assert kwargs["timeout"].connect == gt.CONNECT_TIMEOUT_S
