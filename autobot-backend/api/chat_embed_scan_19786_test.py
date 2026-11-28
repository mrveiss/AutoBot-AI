# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The embed widget's messages pass the chat safety scan before any model call (#19786)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import chat_embed

_EMAIL = "visitor@example.com"
_MESSAGE = f"please write to {_EMAIL} about this"
_BLOCKED = "my ssn is 123-45-6789"  # pragma: allowlist secret


def _client(llm) -> TestClient:
    app = FastAPI()
    app.include_router(chat_embed.router)
    app.state.chat_llm_service = llm
    return TestClient(app)


@pytest.fixture
def allowed():
    with (
        patch.object(chat_embed, "_check_embed_origin", return_value="https://site.example"),
        patch.object(chat_embed._embed_rate_limiter, "acquire", AsyncMock(return_value=True)),
    ):
        yield


def _llm(stream: bool):
    llm = SimpleNamespace(chat=AsyncMock(return_value=SimpleNamespace(content="ok", error=None)))
    if stream:
        seen: list[str] = []

        async def stream_response(message, session_id=None):
            seen.append(message)
            yield {"content": "ok"}

        llm.stream_response = stream_response
        llm.seen = seen
    return llm


def _post(llm, message: str, sse: bool = False):
    headers = {"accept": "text/event-stream"} if sse else {}
    with patch.object(chat_embed, "_get_llm_service", AsyncMock(return_value=llm)):
        return _client(llm).post("/chats/embed/message", json={"message": message}, headers=headers)


def _sent(llm) -> str:
    return llm.chat.await_args.kwargs["messages"][0]["content"]


def test_the_json_path_sends_the_redacted_message(allowed) -> None:
    llm = _llm(stream=False)
    assert _post(llm, _MESSAGE).status_code == 200
    assert _EMAIL not in _sent(llm) and "please write to" in _sent(llm)


def test_the_stream_path_sends_the_redacted_message(allowed) -> None:
    llm = _llm(stream=True)
    assert _post(llm, _MESSAGE, sse=True).status_code == 200
    assert len(llm.seen) == 1 and _EMAIL not in llm.seen[0]


def test_the_stream_fallback_sends_the_redacted_message(allowed) -> None:
    llm = _llm(stream=False)
    assert _post(llm, _MESSAGE, sse=True).status_code == 200
    assert _EMAIL not in _sent(llm)


@pytest.mark.parametrize("sse", [False, True], ids=["json", "stream"])
def test_a_blocked_message_makes_no_model_call_and_the_browser_can_read_why(allowed, sse: bool) -> None:
    llm = _llm(stream=sse)
    response = _post(llm, _BLOCKED, sse=sse)
    assert response.status_code == 400
    assert response.headers["access-control-allow-origin"] == "https://site.example"
    assert "123-45-6789" not in response.text
    llm.chat.assert_not_awaited()
    assert not getattr(llm, "seen", [])
