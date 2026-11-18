# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A successful browser screenshot reaches chat as an ImageCell payload and survives persistence (#13424)."""

from __future__ import annotations

from chat_history.messages import MessagesMixin
from chat_workflow import browser_tool_handler as handler
from chat_workflow.manager import ChatWorkflowManager

_PNG = "iVBORw0KGgoAAAANSUhEUg"
_SCREENSHOT = {"success": True, "action": "screenshot", "result": {"image": _PNG}}


def test_screenshot_message_carries_the_image_payload_imagecell_reads() -> None:
    msg = handler.record_browser_success("screenshot", {}, _SCREENSHOT, [])

    assert msg.metadata["display_type"] == "image"
    assert msg.metadata["image_payload"]["images"] == [{"url": f"data:image/png;base64,{_PNG}"}]


def test_the_raw_bytes_are_not_stored_a_second_time_in_the_result() -> None:
    msg = handler.record_browser_success("screenshot", {}, _SCREENSHOT, [])

    assert "image" not in msg.metadata["result"]["result"]
    assert _SCREENSHOT["result"]["image"] == _PNG  # the caller's dict is untouched


def test_the_vision_loop_still_gets_the_raw_image() -> None:
    results: list = []
    handler.record_browser_success("screenshot", {}, _SCREENSHOT, results)

    assert results[0]["base64_image"] == _PNG


def test_a_data_url_image_is_not_double_prefixed() -> None:
    url = f"data:image/jpeg;base64,{_PNG}"
    msg = handler.record_browser_success("screenshot", {}, {"result": {"image": url}}, [])

    assert msg.metadata["image_payload"]["images"][0]["url"] == url


def test_non_image_results_get_no_image_metadata() -> None:
    result = {"result": {"url": "https://x.test"}}
    msg = handler.record_browser_success("navigate", {"url": "https://x.test"}, result, [])

    assert "image_payload" not in msg.metadata
    assert "display_type" not in msg.metadata


def test_the_image_payload_survives_the_persisted_history_entry() -> None:
    msg = handler.record_browser_success("screenshot", {}, _SCREENSHOT, [])
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)

    batch = manager._build_workflow_message_batch(MessagesMixin(), [msg])

    assert batch[0]["metadata"]["image_payload"]["images"][0]["url"].endswith(_PNG)
    assert batch[0]["metadata"]["display_type"] == "image"


def test_the_persisted_execution_summary_drops_raw_screenshots_but_the_live_one_keeps_them() -> None:
    from async_chat_workflow import WorkflowMessage

    results = [{"tool": "screenshot", "status": "success", "base64_image": _PNG}, {"tool": "navigate"}]
    summary = WorkflowMessage(type="execution_summary", content="", metadata={"execution_results": results})
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)

    batch = manager._build_workflow_message_batch(MessagesMixin(), [summary])

    assert "base64_image" not in batch[0]["metadata"]["execution_results"][0]
    assert batch[0]["metadata"]["execution_results"][0]["tool"] == "screenshot"
    assert summary.metadata["execution_results"][0]["base64_image"] == _PNG  # the vision loop still reads it


def test_only_png_jpeg_webp_data_urls_become_an_image_payload() -> None:
    for kind in ("png", "jpeg", "webp"):
        msg = handler.record_browser_success(
            "screenshot", {}, {"result": {"image": f"data:image/{kind};base64,{_PNG}"}}, []
        )
        assert msg.metadata["display_type"] == "image"
    for url in (f"data:image/svg+xml;base64,{_PNG}", f"data:text/html;base64,{_PNG}", "data:image/png,raw"):
        msg = handler.record_browser_success("screenshot", {}, {"result": {"image": url}}, [])
        assert "image_payload" not in msg.metadata and "display_type" not in msg.metadata


def test_a_non_dict_inner_result_does_not_crash_the_image_metadata() -> None:
    assert handler.persisted_result({"result": "plain string"}, ("image",)) == {"result": "plain string"}


def test_an_image_over_the_persisted_cap_is_not_stored_on_the_message(monkeypatch) -> None:
    monkeypatch.setattr(handler, "BROWSER_IMAGE_PERSIST_MAX_CHARS", 10)  # #21847
    results: list = []
    msg = handler.record_browser_success("screenshot", {}, _SCREENSHOT, results)
    assert "image_payload" not in msg.metadata and results[0]["base64_image"] == _PNG
