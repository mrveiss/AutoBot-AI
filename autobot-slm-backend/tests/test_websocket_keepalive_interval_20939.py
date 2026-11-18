# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stream keepalive waits on the configured interval, not a literal (#20939)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from api import websocket as ws_mod


@pytest.mark.asyncio
async def test_keepalive_uses_configured_interval_and_pings_when_idle(monkeypatch):
    monkeypatch.setattr(ws_mod.settings, "ws_keepalive_seconds", 0.01)

    async def _idle() -> str:
        await asyncio.sleep(5)
        return ""

    sock = MagicMock()
    sock.receive_text = _idle
    sock.send_json = AsyncMock(side_effect=RuntimeError("closed"))
    await asyncio.wait_for(ws_mod._keepalive_loop(sock), timeout=2)
    sock.send_json.assert_awaited_once_with({"type": "ping"})
