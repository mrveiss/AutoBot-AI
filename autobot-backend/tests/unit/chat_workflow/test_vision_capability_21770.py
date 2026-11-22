# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vision support comes from the runtime's reported capabilities, names are the fallback (#21770)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest

from autobot_shared.ssot_constants import PATH_OLLAMA_GENERATE
from chat_workflow import vision_capability as vc
from chat_workflow.manager import ChatWorkflowManager

_ENDPOINT = f"http://ollama.test:11434{PATH_OLLAMA_GENERATE}"


@pytest.fixture(autouse=True)
def _clean_cache():
    vc.reset_vision_capability_cache()
    yield
    vc.reset_vision_capability_cache()


def _client(body=None, status=200, exc=None):
    resp = MagicMock(status=status)

    async def _json():
        return body

    resp.json = _json

    @asynccontextmanager
    async def _cm():
        yield resp

    calls = []

    async def _post(url, **kwargs):
        calls.append((url, kwargs))
        if exc:
            raise exc
        return _cm()

    client = MagicMock()
    client.post = _post
    client.calls = calls
    return client


async def _resolve(client, model):
    with patch.object(vc, "get_http_client", return_value=client):
        return await vc.resolve_model_supports_vision(model, _ENDPOINT)


async def test_reported_vision_wins_over_unmatched_name() -> None:
    client = _client({"capabilities": ["completion", "vision"]})
    assert await _resolve(client, "my-local-model:7b") is True
    assert client.calls[0][0] == "http://ollama.test:11434/api/show"
    assert client.calls[0][1]["json"] == {"model": "my-local-model:7b"}


async def test_reported_capabilities_without_vision_beat_matching_name() -> None:
    assert await _resolve(_client({"capabilities": ["completion"]}), "llava:13b") is False


@pytest.mark.parametrize(
    "client",
    [_client(status=500), _client(exc=OSError("down")), _client({"details": {}})],
)
async def test_failed_or_missing_lookup_falls_back_to_names(client) -> None:
    assert await _resolve(client, "llava:13b") is True
    vc.reset_vision_capability_cache()
    assert await _resolve(client, "phi3") is False


async def test_second_turn_makes_no_second_request() -> None:
    client = _client({"capabilities": ["vision"]})
    await _resolve(client, "m")
    await _resolve(client, "m")
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "endpoint",
    ["http://ollama.test:11434", "http://ollama.test:11434/", _ENDPOINT],
)
async def test_show_url_has_the_path_exactly_once(endpoint) -> None:
    client = _client({"capabilities": ["vision"]})
    with patch.object(vc, "get_http_client", return_value=client):
        assert await vc.resolve_model_supports_vision("m", endpoint) is True
    assert client.calls[0][0] == "http://ollama.test:11434/api/show"


async def test_empty_endpoint_uses_names_without_request() -> None:
    client = _client({"capabilities": ["vision"]})
    with patch.object(vc, "get_http_client", return_value=client):
        assert await vc.resolve_model_supports_vision("llava", "") is True
    assert client.calls == []


def test_payload_honours_resolved_capability_over_name() -> None:
    mgr = ChatWorkflowManager.__new__(ChatWorkflowManager)
    kwargs = {"image_b64": "aGVsbG8=", "ollama_endpoint": _ENDPOINT}
    with_cap = mgr._get_llm_request_payload("unmatched", "p", vision_capable=True, **kwargs)
    without = mgr._get_llm_request_payload("llava:13b", "p", vision_capable=False, **kwargs)
    assert with_cap["images"] == ["aGVsbG8="]
    assert "images" not in without
