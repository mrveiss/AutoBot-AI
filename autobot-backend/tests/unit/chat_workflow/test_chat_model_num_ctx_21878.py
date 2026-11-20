# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every caller of the chat model sends the chat's ``num_ctx``, so Ollama never reloads it between calls (#21878)."""

from __future__ import annotations

import importlib
import sys

import httpx
import pytest

from autobot_shared.chat_model_context import num_ctx_for_model
from autobot_shared.ssot_constants import ModelConfig
from chat_workflow.llm_handler import LLMHandlerMixin

CHAT = "chat-model:9b"
OTHER = "tiny-model:1b"


@pytest.fixture
def llm_shared_real(monkeypatch):
    """The real ``llm_shared`` package: the backend conftest registers a MagicMock stub for it."""
    for name in [n for n in sys.modules if n == "llm_shared" or n.startswith("llm_shared.")]:
        monkeypatch.delitem(sys.modules, name)
    return importlib.import_module("llm_shared")


@pytest.fixture(autouse=True)
def chat_model(monkeypatch):
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(type(config), "default_llm_model", property(lambda _self: CHAT), raising=False)


def test_the_chat_model_gets_the_chat_context_and_another_model_keeps_its_own():
    assert num_ctx_for_model(CHAT, 1234) == ModelConfig.CHAT_NUM_CTX
    assert num_ctx_for_model(OTHER, 1234) == 1234
    assert num_ctx_for_model(None, 1234) == 1234


@pytest.mark.asyncio
@pytest.mark.parametrize("model, expected", [(CHAT, ModelConfig.CHAT_NUM_CTX), (OTHER, None)])
async def test_call_ollama_generate_sends_the_chat_context_to_the_chat_model(
    monkeypatch, llm_shared_real, model, expected
):
    """The RLM evaluator, rag_refiner, agentic search and think tool all send through this one call."""
    ollama_helpers = importlib.import_module("llm_shared.ollama_helpers")
    sent = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            sent.update(json)
            return httpx.Response(200, json={"response": "ok"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(ollama_helpers.httpx, "AsyncClient", _Client)
    await ollama_helpers.call_ollama_generate("p", model, "http://ollama.invalid")
    assert sent["options"].get("num_ctx") == expected


def test_interpretation_asks_the_chat_model_with_the_chat_context():
    handler = LLMHandlerMixin.__new__(LLMHandlerMixin)
    assert handler._get_interpretation_llm_options(CHAT)["num_ctx"] == ModelConfig.CHAT_NUM_CTX
    assert handler._get_interpretation_llm_options(OTHER)["num_ctx"] == ModelConfig.DEFAULT_NUM_CTX


def test_the_ollama_provider_sends_the_chat_context_for_the_chat_model(llm_shared_real):
    LLMRequest = importlib.import_module("llm_shared.models").LLMRequest
    LLMSettings = importlib.import_module("llm_shared.models").LLMSettings
    StreamingManager = importlib.import_module("llm_shared.streaming").StreamingManager
    OllamaRequestExecutor = importlib.import_module("llm_shared.providers.ollama").OllamaRequestExecutor
    provider = OllamaRequestExecutor(LLMSettings(), StreamingManager())
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}], model_name=CHAT)
    chat = provider.build_request_data(request, CHAT, False)
    other = provider.build_request_data(request, OTHER, False)
    assert chat["options"]["num_ctx"] == ModelConfig.CHAT_NUM_CTX
    assert other["options"]["num_ctx"] == LLMSettings().num_ctx
