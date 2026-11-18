# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed browser tool call reports its class and selector, never internals (#21769)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow import browser_tool_handler as handler

_PLANTED = (
    "page.textContent: Timeout 30000ms exceeded waiting for locator('#missing')\n"
    'Traceback (most recent call last):\n  File "/opt/internal/app/browser.py", line 9, in run\n'
    "connect ECONNREFUSED 10.1.2.3:9222 api_key=sk-secret-value-1234567890"
)


async def _run(tool: str, params: dict, exc: Exception):
    results: list = []
    with (
        patch.object(handler, "validate_browser_params", AsyncMock(return_value=None)),
        patch.object(handler, "_emit_before_tool_execute", AsyncMock(return_value=True)),
        patch.object(handler, "_emit_tool_error", AsyncMock()) as emit_error,
        patch("api.browser_mcp.send_to_browser_vm", AsyncMock(side_effect=exc)),
    ):
        messages = [m async for m in handler.handle_browser_tool({"name": tool, "params": params}, results)]
    return messages, results, emit_error


async def test_selector_timeout_reaches_model_and_chat_with_class_and_selector() -> None:
    messages, results, emit_error = await _run("get_text", {"selector": "#missing"}, TimeoutError(_PLANTED))
    err = [m for m in messages if m.type == "error"][0]
    for text in (results[0]["error"], err.content):
        assert "selector_not_found" in text
        assert "#missing" in text
        assert "30000ms" in text
    assert "could not find the requested element" in err.content
    emit_error.assert_awaited_once()  # TOOL_ERROR hook emission unchanged


async def test_no_internals_in_model_result_or_chat_message() -> None:
    messages, results, _ = await _run("get_text", {"selector": "#missing"}, RuntimeError(_PLANTED))
    err = [m for m in messages if m.type == "error"][0]
    blob = f"{results[0]} {err.content} {err.metadata}"
    for leaked in (
        "Traceback",
        "/opt/internal",
        "10.1.2.3",
        "ECONNREFUSED",
        "sk-secret",
    ):
        assert leaked not in blob


async def test_navigation_failure_names_class_and_redacted_url() -> None:
    url = "https://user:hunter2@example.com/page"  # pragma: allowlist secret
    _, results, _ = await _run("navigate", {"url": url}, RuntimeError("net::ERR_NAME_NOT_RESOLVED"))
    assert "navigation_failed" in results[0]["error"]
    assert "hunter2" not in results[0]["error"]


@pytest.mark.parametrize("params", [{}, {"selector": 5}])
async def test_unclassifiable_error_without_context_is_other(params: dict) -> None:
    _, results, _ = await _run("get_text", params, RuntimeError("boom"))
    assert results[0]["error_detail"]["error_class"] == "other"
