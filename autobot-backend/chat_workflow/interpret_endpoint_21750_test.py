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
