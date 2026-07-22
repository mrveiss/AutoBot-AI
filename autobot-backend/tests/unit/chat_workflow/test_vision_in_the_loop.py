# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vision-in-the-loop: browser/VNC screenshots threaded into LLM chat context (#11538).

OpenManus injects the current screenshot into the model's context on every
step while the browser is active, so the model *sees* the effect of its last
action instead of driving blind. These tests prove:

  (c) a browser screenshot tool result produces an image attachment in the
      SHAPE the target endpoint actually consumes — Ollama's /api/generate
      (the endpoint this continuation loop always POSTs to; see
      manager.py::_resolve_vision_payload_shape) reads a top-level raw-base64
      "images" list and ignores "messages" entirely — and stays text-only for
      a non-vision provider. A dedicated HTTP-capture test proves the image
      reaches the field the endpoint actually reads, not just that some dict
      shape was built (the "green test on wrong shape" trap from review).
  (d) only the single most recent screenshot is carried across the lookback
      window — older ones are dropped, never accumulated, and pruned from
      execution_history once they age out.
"""

from __future__ import annotations

import pytest

from chat_workflow.manager import (
    VISION_IMAGE_TOKEN_ESTIMATE,
    VISION_TOOL_LOOKBACK_MESSAGES,
    ChatWorkflowManager,
    _extract_latest_tool_screenshot,
    _model_supports_vision,
    _prune_stale_screenshots,
    _resolve_vision_payload_shape,
    _strip_data_url_prefix,
)
from chat_workflow.tool_handler import ToolHandlerMixin
from constants.api_constants import PATH_OLLAMA_GENERATE
from context_window_manager import ContextWindowManager

_FAKE_PNG_B64 = "aGVsbG8="  # "hello" — stand-in for real screenshot bytes
_OLLAMA_GENERATE_ENDPOINT = f"http://127.0.0.1:11434{PATH_OLLAMA_GENERATE}"


def _manager() -> ChatWorkflowManager:
    return ChatWorkflowManager.__new__(ChatWorkflowManager)  # no __init__ side effects needed


# ---------------------------------------------------------------------------
# _model_supports_vision
# ---------------------------------------------------------------------------


def test_known_vision_model_names_are_recognised() -> None:
    for name in ("llava:13b", "gpt-4o", "gpt-4-vision-preview", "claude-3-opus", "gemini-1.5-pro", "qwen2.5-vl:7b"):
        assert _model_supports_vision(name), name


def test_plain_text_model_names_are_not_vision_capable() -> None:
    for name in ("llama3.1:8b", "mistral", "deepseek-coder", "phi3"):
        assert not _model_supports_vision(name), name


def test_model_name_matching_is_case_insensitive() -> None:
    assert _model_supports_vision("LLaVA:13B")


def test_blank_model_name_is_not_vision_capable() -> None:
    assert not _model_supports_vision("")
    assert not _model_supports_vision(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _resolve_vision_payload_shape / _strip_data_url_prefix (MAJOR fix)
# ---------------------------------------------------------------------------


def test_ollama_generate_endpoint_resolves_to_ollama_shape() -> None:
    assert _resolve_vision_payload_shape(_OLLAMA_GENERATE_ENDPOINT) == "ollama_generate"
    assert _resolve_vision_payload_shape("http://gpu-node:11434/api/generate") == "ollama_generate"


def test_non_generate_endpoint_resolves_to_openai_chat_shape() -> None:
    """Defensive branch for a future OpenAI-compatible /chat/completions path —
    not wired into this loop today, but the router must not silently misroute
    it to the Ollama shape either."""
    assert _resolve_vision_payload_shape("https://api.example.com/v1/chat/completions") == "openai_chat"


def test_strip_data_url_prefix_removes_prefix() -> None:
    assert _strip_data_url_prefix(f"data:image/png;base64,{_FAKE_PNG_B64}") == _FAKE_PNG_B64


def test_strip_data_url_prefix_is_noop_on_raw_base64() -> None:
    """Screenshots already arrive raw from the browser worker — must pass through unchanged."""
    assert _strip_data_url_prefix(_FAKE_PNG_B64) == _FAKE_PNG_B64


# ---------------------------------------------------------------------------
# (c) _get_llm_request_payload — provider-aware image attachment
# ---------------------------------------------------------------------------


def test_ollama_generate_payload_carries_raw_base64_under_images() -> None:
    """The real, only endpoint shape this continuation loop targets today:
    Ollama's /api/generate. It must get the image under "images" as raw
    base64, and must NOT get a "messages" block (Ollama ignores it)."""
    mgr = _manager()
    payload = mgr._get_llm_request_payload(
        selected_model="gpt-4o",
        current_prompt="What is on the screen?",
        image_b64=_FAKE_PNG_B64,
        ollama_endpoint=_OLLAMA_GENERATE_ENDPOINT,
    )

    assert payload["images"] == [_FAKE_PNG_B64]
    assert "messages" not in payload
    # Text-only "prompt" field is preserved — this is what Ollama actually reads for text.
    assert payload["prompt"] == "What is on the screen?"


def test_ollama_generate_payload_strips_data_url_prefix() -> None:
    mgr = _manager()
    payload = mgr._get_llm_request_payload(
        selected_model="gpt-4o",
        current_prompt="hello",
        image_b64=f"data:image/png;base64,{_FAKE_PNG_B64}",
        ollama_endpoint=_OLLAMA_GENERATE_ENDPOINT,
    )

    assert payload["images"] == [_FAKE_PNG_B64]  # raw, no data: prefix


def test_openai_chat_shaped_endpoint_gets_messages_content_block() -> None:
    """Routing parity check: a non-Ollama-generate endpoint gets the OpenAI
    content-block shape instead — proves the branch, not just the default."""
    mgr = _manager()
    payload = mgr._get_llm_request_payload(
        selected_model="gpt-4o",
        current_prompt="What is on the screen?",
        image_b64=_FAKE_PNG_B64,
        ollama_endpoint="https://api.example.com/v1/chat/completions",
    )

    assert "images" not in payload
    content = payload["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "What is on the screen?"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == f"data:image/png;base64,{_FAKE_PNG_B64}"


def test_non_vision_model_stays_text_only() -> None:
    mgr = _manager()
    payload = mgr._get_llm_request_payload(
        selected_model="llama3.1:8b",
        current_prompt="What is on the screen?",
        image_b64=_FAKE_PNG_B64,
        ollama_endpoint=_OLLAMA_GENERATE_ENDPOINT,
    )

    assert "images" not in payload
    assert "messages" not in payload
    assert payload["prompt"] == "What is on the screen?"


def test_no_image_means_no_images_key_even_for_vision_model() -> None:
    mgr = _manager()
    payload = mgr._get_llm_request_payload(
        selected_model="gpt-4o", current_prompt="hello", image_b64=None, ollama_endpoint=_OLLAMA_GENERATE_ENDPOINT
    )

    assert "images" not in payload
    assert "messages" not in payload


def test_image_dropped_when_prompt_alone_already_exceeds_budget() -> None:
    """#11538: an oversized prompt must not silently grow further with an attached image."""
    mgr = _manager()
    huge_prompt = "x" * 500_000  # far beyond any configured history budget, alone
    payload = mgr._get_llm_request_payload(
        selected_model="gpt-4o",
        current_prompt=huge_prompt,
        image_b64=_FAKE_PNG_B64,
        ollama_endpoint=_OLLAMA_GENERATE_ENDPOINT,
    )

    assert "images" not in payload


def test_image_dropped_when_prompt_alone_fits_but_prompt_plus_image_does_not() -> None:
    """MINOR fix: isolate the +VISION_IMAGE_TOKEN_ESTIMATE term. A prompt that
    fits the budget on its own must still drop the image once the fixed
    per-image token cost would tip the total over — proving the image cost
    (not just prompt size) is what's being gated, per the review's flagged gap.

    Sized dynamically off the real ContextWindowManager budget (rather than a
    hardcoded char count) so the test stays correct if config/context_windows.yaml
    is retuned.
    """
    mgr = _manager()
    model = "gpt-4o"
    cwm = ContextWindowManager()
    max_tokens = cwm.get_max_history_tokens(model)
    chars_per_token = cwm.config["token_estimation"]["chars_per_token"]

    # Land just under the budget alone; +VISION_IMAGE_TOKEN_ESTIMATE must tip it over.
    borderline_tokens = max_tokens - (VISION_IMAGE_TOKEN_ESTIMATE // 2)
    borderline_prompt = "x" * (borderline_tokens * chars_per_token)

    payload_alone = mgr._get_llm_request_payload(
        selected_model=model,
        current_prompt=borderline_prompt,
        image_b64=None,
        ollama_endpoint=_OLLAMA_GENERATE_ENDPOINT,
    )
    assert "images" not in payload_alone  # no image requested — just sanity on the prompt itself
    assert cwm.estimate_tokens(borderline_prompt) < max_tokens  # prompt alone genuinely fits

    payload_with_image = mgr._get_llm_request_payload(
        selected_model=model,
        current_prompt=borderline_prompt,
        image_b64=_FAKE_PNG_B64,
        ollama_endpoint=_OLLAMA_GENERATE_ENDPOINT,
    )
    assert "images" not in payload_with_image  # image cost alone tips the budget — dropped


def test_image_attached_when_prompt_plus_image_both_fit() -> None:
    """Sanity counterpart: a genuinely small prompt keeps the image."""
    mgr = _manager()
    payload = mgr._get_llm_request_payload(
        selected_model="gpt-4o",
        current_prompt="short prompt",
        image_b64=_FAKE_PNG_B64,
        ollama_endpoint=_OLLAMA_GENERATE_ENDPOINT,
    )
    assert payload["images"] == [_FAKE_PNG_B64]


# ---------------------------------------------------------------------------
# (c) HTTP-capture: the image reaches the field the real endpoint reads
# ---------------------------------------------------------------------------


class _EmptyAsyncIterator:
    """Stand-in for an aiohttp streaming body that ends immediately (no chunks)."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _FakeStreamResponse:
    def __init__(self) -> None:
        self.status = 200
        self.content = _EmptyAsyncIterator()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeHttpClient:
    """Captures the outgoing POST payload without a real Ollama server."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def post(self, url, json=None, **kwargs):  # noqa: A002 - match aiohttp call signature
        self.calls.append({"url": url, "json": json})
        return _FakeStreamResponse()

    async def decrement_active(self) -> None:
        pass


@pytest.mark.asyncio
async def test_process_single_llm_iteration_posts_raw_base64_images_to_ollama_generate() -> None:
    """Capture the live outgoing request (mirrors #11539's session-id capture
    pattern): drive _process_single_llm_iteration end to end against a fake
    http_client and assert the POSTed JSON body — for the real endpoint this
    loop targets — carries the image in the field Ollama's /api/generate
    actually reads, not merely that some payload dict shape was constructed.
    """
    mgr = _manager()
    http_client = _FakeHttpClient()

    async for _item in mgr._process_single_llm_iteration(
        http_client,
        _OLLAMA_GENERATE_ENDPOINT,
        "gpt-4o",
        "What is on the screen?",
        "term-1",
        False,
        [],
        1,
        image_b64=_FAKE_PNG_B64,
    ):
        pass

    assert len(http_client.calls) == 1
    assert http_client.calls[0]["url"] == _OLLAMA_GENERATE_ENDPOINT
    posted_payload = http_client.calls[0]["json"]
    assert posted_payload["images"] == [_FAKE_PNG_B64]
    assert "messages" not in posted_payload


# ---------------------------------------------------------------------------
# (d) _extract_latest_tool_screenshot — only the latest screenshot, dropped after N
# ---------------------------------------------------------------------------


def test_extracts_the_only_screenshot_present() -> None:
    history = [
        {"tool": "click", "status": "success", "output": "Clicked"},
        {"tool": "screenshot", "status": "success", "output": "Screenshot captured.", "base64_image": "img-1"},
    ]
    assert _extract_latest_tool_screenshot(history) == "img-1"


def test_only_the_most_recent_screenshot_is_returned() -> None:
    """Multiple screenshots within the lookback window — only the latest wins."""
    history = [
        {"tool": "screenshot", "status": "success", "output": "s1", "base64_image": "img-old"},
        {"tool": "navigate", "status": "success", "output": "nav"},
        {"tool": "screenshot", "status": "success", "output": "s2", "base64_image": "img-latest"},
    ]
    assert _extract_latest_tool_screenshot(history) == "img-latest"


def test_screenshot_outside_the_lookback_window_is_dropped() -> None:
    """A screenshot older than VISION_TOOL_LOOKBACK_MESSAGES steps back must
    not resurface — context never accumulates stale screenshots."""
    history = [{"tool": "screenshot", "status": "success", "output": "old", "base64_image": "img-stale"}]
    # Pad with enough non-image entries to push the screenshot out of the window.
    padding_count = VISION_TOOL_LOOKBACK_MESSAGES
    padding = [{"tool": "click", "status": "success", "output": f"click-{i}"} for i in range(padding_count)]
    history += padding

    assert _extract_latest_tool_screenshot(history) is None


def test_no_screenshot_in_history_returns_none() -> None:
    history = [
        {"tool": "navigate", "status": "success", "output": "nav"},
        {"tool": "click", "status": "success", "output": "click"},
    ]
    assert _extract_latest_tool_screenshot(history) is None


def test_empty_history_returns_none() -> None:
    assert _extract_latest_tool_screenshot([]) is None


# ---------------------------------------------------------------------------
# MINOR fix: _prune_stale_screenshots — bounded base64 retention
# ---------------------------------------------------------------------------


def test_prune_removes_base64_image_outside_the_lookback_window() -> None:
    history = [{"tool": "screenshot", "status": "success", "output": "old", "base64_image": "img-stale"}]
    padding = [{"tool": "click", "status": "success", "output": f"c{i}"} for i in range(VISION_TOOL_LOOKBACK_MESSAGES)]
    history += padding

    _prune_stale_screenshots(history)

    assert "base64_image" not in history[0]
    # Non-image fields on the pruned entry are untouched.
    assert history[0]["output"] == "old"


def test_prune_keeps_base64_image_inside_the_lookback_window() -> None:
    history = [{"tool": "screenshot", "status": "success", "output": "recent", "base64_image": "img-recent"}]

    _prune_stale_screenshots(history)

    assert history[0]["base64_image"] == "img-recent"


def test_prune_is_a_noop_when_no_entry_has_an_image() -> None:
    history = [{"tool": "click", "status": "success", "output": "c"} for _ in range(5)]
    _prune_stale_screenshots(history)  # must not raise
    assert all("base64_image" not in entry for entry in history)


def test_prune_handles_empty_history() -> None:
    history: list = []
    _prune_stale_screenshots(history)  # must not raise
    assert history == []


# ---------------------------------------------------------------------------
# Source of the image: _record_browser_success threads base64_image through
# ---------------------------------------------------------------------------


def test_record_browser_success_captures_screenshot_image_for_vision_loop() -> None:
    handler = ToolHandlerMixin.__new__(ToolHandlerMixin)
    execution_results: list = []
    result = {"success": True, "action": "screenshot", "result": {"image": _FAKE_PNG_B64}}

    handler._record_browser_success("screenshot", {}, result, execution_results)

    assert execution_results[0]["base64_image"] == _FAKE_PNG_B64


def test_record_browser_success_omits_base64_image_key_when_absent() -> None:
    """A tool with no image data (e.g. navigate) must not grow execution_results
    with a stray None-valued key that would need special-casing downstream."""
    handler = ToolHandlerMixin.__new__(ToolHandlerMixin)
    execution_results: list = []
    result = {"success": True, "action": "navigate", "result": {"url": "https://example.com", "title": "Example"}}

    handler._record_browser_success("navigate", {"url": "https://example.com"}, result, execution_results)

    assert "base64_image" not in execution_results[0]
