# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vision support comes from Ollama /api/show capabilities (#21770)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_workflow import vision_capability as vc


class _Resp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    async def json(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _client(status=200, body=None, exc=None):
    client = MagicMock()
    client.post = AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=_Resp(status, body))
    return client


@pytest.fixture(autouse=True)
def _clear():
    vc._capability_cache.clear()
    yield
    vc._capability_cache.clear()


@pytest.mark.asyncio
async def test_capability_list_enables_vision_for_unlisted_model():
    assert not vc.model_supports_vision("mystery-model:7b")
    await vc.refresh_vision_capability(
        _client(body={"capabilities": ["completion", "vision"]}), "http://o", "mystery-model:7b"
    )
    assert vc.model_supports_vision("mystery-model:7b")


@pytest.mark.asyncio
async def test_capability_list_overrides_name_pattern():
    await vc.refresh_vision_capability(_client(body={"capabilities": ["completion"]}), "http://o", "llava-text-only")
    assert not vc.model_supports_vision("llava-text-only")


@pytest.mark.asyncio
async def test_lookup_is_cached():
    client = _client(body={"capabilities": ["vision"]})
    for _ in range(3):
        await vc.refresh_vision_capability(client, "http://o", "m")
    assert client.post.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("client", [_client(status=404), _client(exc=OSError("down"))])
async def test_failed_lookup_falls_back_to_name_patterns(client):
    await vc.refresh_vision_capability(client, "http://o", "llava:13b")
    assert vc.model_supports_vision("llava:13b")
    assert not vc.model_supports_vision("plain:8b")
