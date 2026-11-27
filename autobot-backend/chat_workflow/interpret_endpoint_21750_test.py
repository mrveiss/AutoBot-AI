# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21750: interpretation POSTs hit ``/api/generate`` once for either endpoint form."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_workflow.llm_handler import LLMHandlerMixin

_URL = "http://ollama.example:11434/api/generate"


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["http://ollama.example:11434", _URL])
async def test_interpret_non_streaming_posts_to_one_generate_path(endpoint):
    client = MagicMock()
    client.post_json = AsyncMock(return_value={"response": "ok"})
    with (
        patch("chat_workflow.llm_handler.get_http_client", return_value=client),
        patch("chat_workflow.llm_handler._emit_before_llm_call", AsyncMock(return_value=True)),
        patch("chat_workflow.llm_handler._emit_after_llm_response", AsyncMock(side_effect=lambda t, *a: t)),
    ):
        handler = LLMHandlerMixin.__new__(LLMHandlerMixin)
        msgs = [m async for m in handler._interpret_non_streaming(endpoint, "m", "p", {}, "s")]
    assert client.post_json.await_args.args[0] == _URL
    assert msgs[0].content == "ok"


@pytest.mark.asyncio
async def test_interpretation_is_not_bound_by_the_ten_second_session_read_timeout():
    """A model answers in minutes: the POST carries the interpretation deadline, not the session's 10 s sock_read."""
    from chat_workflow.interpretation_guard import INTERPRETATION_TIMEOUT_SECONDS

    client = MagicMock()
    client.post_json = AsyncMock(return_value={"response": "ok"})
    with (
        patch("chat_workflow.llm_handler.get_http_client", return_value=client),
        patch("chat_workflow.llm_handler._emit_before_llm_call", AsyncMock(return_value=True)),
        patch("chat_workflow.llm_handler._emit_after_llm_response", AsyncMock(side_effect=lambda t, *a: t)),
    ):
        handler = LLMHandlerMixin.__new__(LLMHandlerMixin)
        [m async for m in handler._interpret_non_streaming(_URL, "m", "p", {}, "s")]
    timeout = client.post_json.await_args.kwargs["timeout"]
    assert timeout.total == INTERPRETATION_TIMEOUT_SECONDS and timeout.sock_read is None
