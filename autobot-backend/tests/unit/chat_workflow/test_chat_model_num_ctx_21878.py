# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every caller of the chat model sends the chat's ``num_ctx``, so Ollama never reloads it between calls (#21878)."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

import httpx
import pytest

from autobot_shared import chat_model_context
from autobot_shared.chat_model_context import chat_context_options, note_chat_turn_model, num_ctx_for_model
from autobot_shared.ssot_constants import ModelConfig
from chat_workflow.llm_handler import LLMHandlerMixin

CHAT = "chat-model:9b"
OTHER = "tiny-model:1b"


@pytest.fixture
def llm_shared_real():
    """The real ``llm_shared`` package: the backend conftest registers a MagicMock stub for it.

    ``patch.dict`` restores ``sys.modules`` whole on exit, removing every module imported inside as well, so no
    half-real module graph is left for later tests.
    """
    with patch.dict(sys.modules):
        for name in [n for n in sys.modules if n == "llm_shared" or n.startswith("llm_shared.")]:
            del sys.modules[name]
        yield importlib.import_module("llm_shared")


@pytest.fixture(autouse=True)
def chat_model(monkeypatch):
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(chat_model_context, "_last_turn_model", None)
    monkeypatch.delenv(chat_model_context.CHAT_NUM_GPU_ENV, raising=False)
    monkeypatch.setattr(chat_model_context, "_host_has_nvidia_gpu", lambda: False)  # the host's GPU never leaks in
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


def test_the_provider_keeps_the_callers_context_and_only_the_caller_asks_for_the_chats(llm_shared_real):
    models = importlib.import_module("llm_shared.models")
    executor = importlib.import_module("llm_shared.providers.ollama").OllamaRequestExecutor
    streaming = importlib.import_module("llm_shared.streaming").StreamingManager
    provider = executor(models.LLMSettings(), streaming())

    def sent(**metadata):
        request = models.LLMRequest(messages=[{"role": "user", "content": "hi"}], model_name=CHAT, metadata=metadata)
        return provider.build_request_data(request, CHAT, False)["options"]["num_ctx"]

    assert sent() == models.LLMSettings().num_ctx  # no override by model name
    assert sent(**chat_context_options(CHAT)) == ModelConfig.CHAT_NUM_CTX
    assert sent(num_ctx=0) == 0  # an explicit value is kept, falsy or not


def test_a_user_selected_chat_model_is_recognised_after_a_turn_ran_with_it():
    selected = "user-picked:14b"
    assert num_ctx_for_model(selected, 1234) == 1234
    note_chat_turn_model(selected)
    assert num_ctx_for_model(selected, 1234) == ModelConfig.CHAT_NUM_CTX
    assert num_ctx_for_model(OTHER, 1234) == 1234


def test_the_verifier_uses_the_same_rule():
    assert chat_context_options(OTHER, reuses_chat=True) == {"num_ctx": ModelConfig.CHAT_NUM_CTX}
    assert chat_context_options(OTHER) == {}


# --- num_gpu (#22257): the same options builder gives every chat-model caller the same GPU layer count ---


@pytest.fixture
def gpu_host(monkeypatch):
    monkeypatch.setattr(chat_model_context, "_host_has_nvidia_gpu", lambda: True)


def test_num_gpu_is_all_layers_on_a_gpu_host_and_left_out_without_one(monkeypatch, gpu_host):
    all_layers = ModelConfig.CHAT_NUM_GPU_ALL_LAYERS
    assert chat_context_options(CHAT) == {"num_ctx": ModelConfig.CHAT_NUM_CTX, "num_gpu": all_layers}
    monkeypatch.setattr(chat_model_context, "_host_has_nvidia_gpu", lambda: False)
    assert chat_context_options(CHAT) == {"num_ctx": ModelConfig.CHAT_NUM_CTX}


@pytest.mark.parametrize("raw, expected", [("20", 20), ("0", 0), ("off", None), ("-1", None), ("many", None)])
def test_the_env_value_decides_num_gpu(monkeypatch, gpu_host, raw, expected):
    monkeypatch.setenv(chat_model_context.CHAT_NUM_GPU_ENV, raw)
    assert chat_model_context.chat_num_gpu() == expected


def test_another_model_gets_no_gpu_option(gpu_host):
    assert chat_context_options(OTHER) == {}


@pytest.mark.asyncio
async def test_every_caller_path_sends_the_same_chat_options(monkeypatch, llm_shared_real, gpu_host):
    expected = chat_context_options(CHAT)
    ollama_helpers = importlib.import_module("llm_shared.ollama_helpers")
    sent = {}

    class _Client:
        def __init__(self, *a, **k): ...

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a): ...

        async def post(self, url, json):
            sent.update(json)
            return httpx.Response(200, json={"response": "ok"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(ollama_helpers.httpx, "AsyncClient", _Client)
    await ollama_helpers.call_ollama_generate("p", CHAT, "http://ollama.invalid")

    interpretation = LLMHandlerMixin.__new__(LLMHandlerMixin)._get_interpretation_llm_options(CHAT)
    models = importlib.import_module("llm_shared.models")
    executor = importlib.import_module("llm_shared.providers.ollama").OllamaRequestExecutor
    streaming = importlib.import_module("llm_shared.streaming").StreamingManager
    request = models.LLMRequest(messages=[{"role": "user", "content": "hi"}], model_name=CHAT, metadata=expected)
    provider = executor(models.LLMSettings(), streaming()).build_request_data(request, CHAT, False)["options"]

    for options in (sent["options"], interpretation, provider):
        assert {k: options[k] for k in expected} == expected


# --- think (#22258): Ollama's top-level thinking switch, decided in one place from the toggle + capability ---


@pytest.mark.parametrize(
    "toggle, supported, expected", [(False, True, {"think": False}), (True, True, {"think": True}), (True, False, {})]
)
def test_think_is_a_top_level_field_only_for_a_thinking_model(toggle, supported, expected):
    assert chat_model_context.chat_think_field(toggle, supported) == expected
    assert "think" not in chat_context_options(CHAT, reuses_chat=True)  # never an option


def test_an_unset_toggle_is_off_in_the_request_exactly_as_the_gui_shows_it():
    from api.chat_sessions_thinking import stored_thinking_preferences

    assert stored_thinking_preferences(None)["enabled"] is False  # what the GET endpoint returns for no preference
    assert stored_thinking_preferences({"thinking_preferences": {"enabled": True}})["enabled"] is True
    assert chat_model_context.session_thinking("never-noted") is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capabilities, toggle, expected",
    [(["thinking"], False, {"think": False}), (["completion"], False, {}), (None, False, {})],
)
async def test_the_capability_comes_from_the_runtime_not_the_model_name(monkeypatch, capabilities, toggle, expected):
    from chat_workflow import reasoning_kwargs, vision_capability

    async def _caps(model, endpoint):
        return None if capabilities is None else frozenset(capabilities)

    monkeypatch.setattr(vision_capability, "resolve_model_capabilities", _caps)
    assert await reasoning_kwargs.ollama_think_kwargs("qwen3.5:9b", "http://o", toggle) == expected


@pytest.mark.asyncio
async def test_the_continuation_payload_interpretation_and_provider_agree_on_think(monkeypatch, llm_shared_real):
    from chat_workflow import reasoning_kwargs, vision_capability

    async def _caps(model, endpoint):
        return frozenset({"thinking"})

    monkeypatch.setattr(vision_capability, "resolve_model_capabilities", _caps)
    kwargs = await reasoning_kwargs.build_reasoning_api_kwargs({"thinking_mode_enabled": False}, CHAT, "http://o", "s1")
    handler = LLMHandlerMixin.__new__(LLMHandlerMixin)
    interpretation = await handler._interpretation_think(CHAT, "http://o", "s1")
    models = importlib.import_module("llm_shared.models")
    executor = importlib.import_module("llm_shared.providers.ollama").OllamaRequestExecutor
    streaming = importlib.import_module("llm_shared.streaming").StreamingManager
    request = models.LLMRequest(messages=[{"role": "user", "content": "hi"}], model_name=CHAT, metadata=kwargs)
    provider = executor(models.LLMSettings(), streaming()).build_request_data(request, CHAT, False)
    assert kwargs == interpretation == {"think": False} and provider["think"] is False
    assert "think" not in provider["options"]


@pytest.mark.asyncio
async def test_a_context_without_the_toggle_sends_think_false_and_an_explicit_on_sends_true(monkeypatch):
    from chat_workflow import reasoning_kwargs, vision_capability

    async def _caps(model, endpoint):
        return frozenset({"thinking"})

    monkeypatch.setattr(vision_capability, "resolve_model_capabilities", _caps)
    assert await reasoning_kwargs.build_reasoning_api_kwargs({}, CHAT, "http://o", "s2") == {"think": False}
    assert await reasoning_kwargs.build_reasoning_api_kwargs(
        {"thinking_mode_enabled": True}, CHAT, "http://o", "s2"
    ) == {"think": True}
