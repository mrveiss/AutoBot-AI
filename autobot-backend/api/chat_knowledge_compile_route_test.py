# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A refused transcript is the user's to fix: the compile route answers 422, not 500 (#15700).

The route's blanket ``except Exception`` turned every failure into "Internal
server error", so a transcript refused for carrying an instruction to the model
read as a backend fault to the caller and to monitoring alike.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import chat_knowledge
from api.chat_knowledge_prompt import TranscriptRefused

_REQUEST = SimpleNamespace(chat_id="chat-15700", title=None, include_system_messages=False)


def _manager_raising(monkeypatch, exc: Exception) -> None:
    class _Manager:
        async def compile_chat_to_knowledge(self, **_kwargs):
            raise exc

    async def _instance(_request):
        return _Manager()

    monkeypatch.setattr(chat_knowledge, "get_chat_knowledge_manager_instance", _instance)


async def test_a_refused_transcript_is_a_422_carrying_the_reason(monkeypatch) -> None:
    _manager_raising(monkeypatch, TranscriptRefused("remove that text and try again"))

    with pytest.raises(HTTPException) as raised:
        await chat_knowledge.compile_chat_to_knowledge(_REQUEST, SimpleNamespace())

    assert (raised.value.status_code, raised.value.detail) == (422, "remove that text and try again")


async def test_any_other_failure_is_still_a_500(monkeypatch) -> None:
    """Only the refusal is the user's to fix; a real fault keeps its status and its silence."""
    _manager_raising(monkeypatch, RuntimeError("redis went away"))

    with pytest.raises(HTTPException) as raised:
        await chat_knowledge.compile_chat_to_knowledge(_REQUEST, SimpleNamespace())

    assert (raised.value.status_code, raised.value.detail) == (500, "Internal server error")
