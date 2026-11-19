# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The verifier uses its own model only when it is resident or nothing else is loaded (#21844).

Otherwise the loaded chat model answers, asked with the chat's ``num_ctx`` so Ollama keeps the runner.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared import verifier_model
from autobot_shared.ollama_urls import ollama_ps_url
from autobot_shared.ssot_config import config
from autobot_shared.ssot_constants import ModelConfig

_OWN = "verifier-test:1b"
_CHAT = "chat-test:8b"


@pytest.fixture(autouse=True)
def _fresh_state():
    verifier_model._readings.clear()
    verifier_model._residency.clear()
    with patch.object(config, "verifier_model", _OWN), patch.object(config, "default_llm_model", _CHAT):
        yield


def _provider() -> MagicMock:
    provider = MagicMock()
    provider.provider_name = "ollama"
    provider.list_models = AsyncMock(return_value=[_OWN, _CHAT])
    provider.chat_completion = AsyncMock(return_value=MagicMock(content="x", model="m"))
    return provider


async def _run(loaded):
    provider, attempt = _provider(), {}
    with (
        patch.object(verifier_model, "loaded_models", AsyncMock(return_value=loaded)),
        patch.object(verifier_model, "report_spend", AsyncMock()),
    ):
        request, _ = await verifier_model.resolve_and_chat(provider, "s", "u", "bash", 10, attempt)
    return request, attempt


@pytest.mark.asyncio
async def test_a_model_that_does_not_fit_reuses_the_loaded_chat_model_with_the_chat_num_ctx():
    request, attempt = await _run([_CHAT])
    assert request.model_name == attempt["model"] == _CHAT
    assert request.metadata["num_ctx"] == ModelConfig.CHAT_NUM_CTX
    assert "reusing loaded" in attempt["model_reason"]


@pytest.mark.asyncio
async def test_an_already_loaded_verifier_model_is_used_even_beside_the_chat_model():
    request, attempt = await _run([_CHAT, _OWN])
    assert request.model_name == _OWN and "num_ctx" not in request.metadata
    assert attempt["model_reason"] == "verifier model already loaded"


@pytest.mark.asyncio
async def test_with_nothing_loaded_the_own_model_is_used_and_the_decision_is_not_cached():
    request, _ = await _run([])
    assert request.model_name == _OWN
    assert _OWN not in verifier_model._residency  # the next chat load changes the answer


@pytest.mark.asyncio
async def test_an_unreadable_listing_keeps_the_configured_model():
    request, attempt = await _run(None)
    assert request.model_name == _OWN and "num_ctx" not in request.metadata
    assert "unreadable" in attempt["model_reason"]


@pytest.mark.asyncio
async def test_residency_is_read_on_every_pass_never_reused_stale():
    provider = _provider()
    ps = AsyncMock(side_effect=[[_CHAT], [_CHAT, _OWN], [_CHAT]])
    with patch.object(verifier_model, "loaded_models", ps):
        assert await verifier_model.resolve_verifier_model(provider) == _CHAT
        assert await verifier_model.resolve_verifier_model(provider) == _OWN  # the verifier became resident
        assert await verifier_model.resolve_verifier_model(provider) == _CHAT  # and was evicted again
    assert ps.await_count == 3 and not verifier_model._residency


@pytest.mark.asyncio
async def test_only_an_unreadable_listing_is_remembered_and_a_failed_call_forgets_it():
    provider = _provider()
    ps = AsyncMock(return_value=None)
    with patch.object(verifier_model, "loaded_models", ps):
        await verifier_model.resolve_verifier_model(provider)
        await verifier_model.resolve_verifier_model(provider)
        assert ps.await_count == 1 and _OWN in verifier_model._residency
        provider.chat_completion = AsyncMock(side_effect=OSError("down"))
        with patch.object(verifier_model, "report_spend", AsyncMock()), pytest.raises(OSError):
            await verifier_model.resolve_and_chat(provider, "s", "u", "bash", 10, {})
        assert _OWN not in verifier_model._residency


@pytest.mark.asyncio
async def test_the_chat_model_is_picked_by_name_not_by_position_and_never_an_embedding_model():
    embed = config.embedding_model
    with patch.object(config, "default_llm_model", _CHAT):
        request, _ = await _run([embed, _CHAT])
        assert request.model_name == _CHAT
        request, attempt = await _run([embed, "other:7b"])  # the chat model is not resident
        assert request.model_name == _OWN and "num_ctx" not in request.metadata
        assert "not the chat model" in attempt["model_reason"]


@pytest.mark.asyncio
async def test_an_embedding_model_configured_as_chat_is_never_reused():
    embed = config.embedding_model
    with patch.object(config, "default_llm_model", embed):
        request, _ = await _run([embed])
    assert request.model_name == _OWN


@pytest.mark.asyncio
async def test_other_providers_never_read_the_loaded_models():
    provider = _provider()
    provider.provider_name = "anthropic"
    ps = AsyncMock()
    with patch.object(verifier_model, "loaded_models", ps):
        assert await verifier_model.resolve_verifier_model(provider) is None
    ps.assert_not_awaited()


@pytest.mark.asyncio
async def test_loaded_models_reads_api_ps_and_an_unreachable_ollama_is_none():
    provider = _provider()
    provider.resolved_base_url.return_value = "http://ollama.example:11434"
    resp = MagicMock(status=200)
    resp.json = AsyncMock(return_value={"models": [{"name": _CHAT, "size": 6, "size_vram": 6}]})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    with patch.object(verifier_model, "get_http_client", return_value=client):
        assert await verifier_model.loaded_models(provider) == [_CHAT]
        assert client.get.await_args.args[0] == ollama_ps_url("http://ollama.example:11434")
        client.get = AsyncMock(side_effect=OSError("down"))
        assert await verifier_model.loaded_models(provider) is None


@pytest.mark.asyncio
async def test_shutdown_drains_in_flight_spend_recordings():
    done = []

    async def slow(response, **kwargs):
        await asyncio.sleep(0.01)
        done.append(response)

    provider = _provider()
    with (
        patch.object(verifier_model, "report_spend", slow),
        patch.object(verifier_model, "loaded_models", AsyncMock(return_value=[])),
    ):
        await verifier_model.resolve_and_chat(provider, "s", "u", "bash", 10, {})
        assert not done
        await verifier_model.drain_spend_tasks()
    assert len(done) == 1 and not verifier_model._spend_tasks
