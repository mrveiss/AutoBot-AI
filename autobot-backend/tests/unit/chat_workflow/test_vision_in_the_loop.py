# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vision-in-the-loop: browser/VNC screenshots threaded into LLM chat context (#11538).

OpenManus injects the current screenshot into the model's context on every
step while the browser is active, so the model *sees* the effect of its last
action instead of driving blind. These tests prove:

  (c) a browser screenshot tool result produces an image content block for a
      vision-capable provider, and stays text-only for a non-vision provider.
  (d) only the single most recent screenshot is carried across the lookback
      window — older ones are dropped, never accumulated.
"""

from __future__ import annotations

from chat_workflow.manager import (
    VISION_TOOL_LOOKBACK_MESSAGES,
    ChatWorkflowManager,
    _extract_latest_tool_screenshot,
    _model_supports_vision,
)
from chat_workflow.tool_handler import ToolHandlerMixin

_FAKE_PNG_B64 = "aGVsbG8="  # "hello" — stand-in for real screenshot bytes


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
# (c) _get_llm_request_payload — image content block gating
# ---------------------------------------------------------------------------


def test_vision_capable_model_gets_image_content_block() -> None:
    mgr = _manager()
    payload = mgr._get_llm_request_payload(
        selected_model="gpt-4o",
        current_prompt="What is on the screen?",
        image_b64=_FAKE_PNG_B64,
    )

    assert "messages" in payload
    content = payload["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "What is on the screen?"}
    image_block = content[1]
    assert image_block["type"] == "image_url"
    assert image_block["image_url"]["url"] == f"data:image/png;base64,{_FAKE_PNG_B64}"
    # Text-only "prompt" field is preserved for providers that don't read "messages".
    assert payload["prompt"] == "What is on the screen?"


def test_non_vision_model_stays_text_only() -> None:
    mgr = _manager()
    payload = mgr._get_llm_request_payload(
        selected_model="llama3.1:8b",
        current_prompt="What is on the screen?",
        image_b64=_FAKE_PNG_B64,
    )

    assert "messages" not in payload
    assert payload["prompt"] == "What is on the screen?"


def test_no_image_means_no_messages_key_even_for_vision_model() -> None:
    mgr = _manager()
    payload = mgr._get_llm_request_payload(selected_model="gpt-4o", current_prompt="hello", image_b64=None)

    assert "messages" not in payload


def test_image_dropped_when_it_would_blow_the_context_budget() -> None:
    """#11538: image token cost counts toward the context budget — an
    oversized prompt must not silently grow further with an attached image."""
    mgr = _manager()
    huge_prompt = "x" * 50_000  # far beyond the default ~3000-token history budget
    payload = mgr._get_llm_request_payload(
        selected_model="gpt-4o",
        current_prompt=huge_prompt,
        image_b64=_FAKE_PNG_B64,
    )

    assert "messages" not in payload


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
