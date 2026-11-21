# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat turn's own post-command interpretation timing out keeps the command's result (#21938).

Traced from the live log: ``Tool execute_command: SUCCESS``, then ``Calling LLM`` (the BEFORE_LLM_CALL hook of
``_interpret_non_streaming``), then ``Tool execute_command error: Timeout`` (the TOOL_ERROR hook). The interpretation
runs inside ``_handle_direct_execution``, inside the tool's try block, so its socket timeout surfaced as a tool failure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_workflow import llm_handler
from chat_workflow.llm_handler import LLMHandlerMixin
from chat_workflow.tool_handler import ToolHandlerMixin

pytestmark = pytest.mark.asyncio

RESULT = {"status": "success", "stdout": "6.1.0-generic\n", "stderr": "", "return_code": 0}


class _Handler(ToolHandlerMixin, LLMHandlerMixin):
    pass


async def _run(monkeypatch, failure: BaseException):
    http = MagicMock()
    http.post_json = AsyncMock(side_effect=failure)
    monkeypatch.setattr(llm_handler, "get_http_client", lambda: http)
    monkeypatch.setattr(llm_handler, "_emit_before_llm_call", AsyncMock(return_value=True))
    handler = _Handler()
    return [m async for m in handler._handle_direct_execution("uname -r", "main", RESULT, "http://llm", "m", "s1")]


async def test_a_timing_out_interpretation_still_yields_the_command_result(monkeypatch):
    items = await _run(monkeypatch, TimeoutError("Timeout on reading data from socket"))
    exec_result, _text = items[-1]
    assert "6.1.0-generic" in str(exec_result)  # the output reaches the next iteration


async def test_control_cancellation_still_propagates(monkeypatch):
    import asyncio

    with pytest.raises(asyncio.CancelledError):
        await _run(monkeypatch, asyncio.CancelledError())
