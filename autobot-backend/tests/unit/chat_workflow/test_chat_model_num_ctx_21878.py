# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every caller of the chat model sends the chat's ``num_ctx``, so Ollama never reloads it between calls (#21878)."""

from __future__ import annotations

import asyncio
import importlib
import sys
from contextvars import ContextVar
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

    monkeypatch.setattr(chat_model_context, "_last_turn_model", ContextVar("t", default=None))
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
    monkeypatch.setattr(chat_model_context, "_chat_endpoint_local", ContextVar("t", default=True))


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


def test_a_provider_path_call_to_the_chat_model_sends_the_turns_think_field():
    """#22258: the verifier and the planner ask the chat model with the toggle the turn resolved; others do not."""
    note_chat_turn_model(CHAT)
    chat_model_context.note_chat_turn_think({"think": False})
    try:
        assert chat_model_context.chat_think_options(CHAT) == {"think": False}
        assert chat_model_context.chat_think_options(OTHER) == {}  # a different model keeps its own default
        assert chat_model_context.chat_think_options(OTHER, reuses_chat=True) == {"think": False}  # the verifier
        chat_model_context.note_chat_turn_think({})  # a model with no thinking switch: no field
        assert chat_model_context.chat_think_options(CHAT) == {}
    finally:
        chat_model_context.note_chat_turn_think({})


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


@pytest.mark.asyncio
async def test_concurrent_sessions_never_see_each_others_turn_model_or_think():
    """#22258: the turn's model and think are per request; one session's turn never decides another's side calls."""
    seen: dict[str, tuple[bool, dict]] = {}

    async def _turn(name: str, model: str, think: dict) -> None:
        note_chat_turn_model(model)
        chat_model_context.note_chat_turn_think(think)
        await asyncio.sleep(0)  # the other turn runs and notes its own
        await asyncio.sleep(0)
        seen[name] = (chat_model_context.is_chat_model(model), chat_model_context.chat_think_options(model))

    await asyncio.gather(
        asyncio.create_task(_turn("a", "alpha-model:1b", {"think": True})),
        asyncio.create_task(_turn("b", "beta-model:2b", {})),
    )
    assert seen["a"] == (True, {"think": True})
    assert seen["b"] == (True, {})
    assert chat_model_context.is_chat_model("alpha-model:1b") is False  # nothing leaks into the parent context


@pytest.mark.asyncio
async def test_a_turn_with_no_endpoint_clears_the_previous_turns_think(monkeypatch):
    from chat_workflow import reasoning_kwargs

    note_chat_turn_model(CHAT)
    chat_model_context.note_chat_turn_think({"think": True})
    try:
        await reasoning_kwargs.build_reasoning_api_kwargs({}, CHAT, "", "s3")
        assert chat_model_context.chat_think_options(CHAT) == {}
    finally:
        chat_model_context.note_chat_turn_think({})


# --- #22257: the auto-detect applies to a local endpoint only, runs off the loop and never caches a failure ---


def test_a_remote_endpoint_gets_no_auto_num_gpu_even_on_a_gpu_host(monkeypatch, gpu_host):
    monkeypatch.setattr(chat_model_context, "_chat_endpoint_local", ContextVar("t", default=False))
    assert "num_gpu" not in chat_context_options(CHAT)
    monkeypatch.setenv(chat_model_context.CHAT_NUM_GPU_ENV, "33")
    assert chat_context_options(CHAT)["num_gpu"] == 33  # the explicit value still applies


@pytest.mark.asyncio
async def test_the_probe_runs_off_the_event_loop_and_only_for_a_local_endpoint(monkeypatch):
    import threading

    monkeypatch.setattr(chat_model_context, "_host_gpu_probe", None)
    monkeypatch.setattr(chat_model_context, "_chat_endpoint_local", ContextVar("t", default=None))
    seen = []

    def _smi(fields):
        seen.append(threading.current_thread() is threading.main_thread())
        return [{"name": "gpu"}]

    monkeypatch.setattr(chat_model_context, "query_nvidia_gpus", _smi)
    await chat_model_context.note_chat_turn_endpoint("http://203.0.113.9:11434/api/generate")  # remote
    assert seen == [] and chat_model_context._chat_endpoint_local.get() is False
    await chat_model_context.note_chat_turn_endpoint("http://127.0.0.1:11434/api/generate")
    assert seen == [False], "nvidia-smi ran in a worker thread, not on the loop"
    assert (
        chat_model_context._host_gpu_probe is True
    )  # the worker thread's answer is kept (the autouse fixture pins the verdict reader)


@pytest.mark.asyncio
async def test_a_failed_probe_is_asked_again_and_is_never_cached(monkeypatch):
    monkeypatch.setattr(chat_model_context, "_host_gpu_probe", None)
    answers = iter([None, []])  # nvidia-smi unavailable, then answering: no GPU
    monkeypatch.setattr(chat_model_context, "query_nvidia_gpus", lambda fields: next(answers))
    await chat_model_context.note_chat_turn_endpoint("http://127.0.0.1:11434")
    assert chat_model_context._host_gpu_probe is None
    await chat_model_context.note_chat_turn_endpoint("http://127.0.0.1:11434")
    assert chat_model_context._host_gpu_probe is False  # an answer, even "no GPU", is kept
