# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Resuming an attachment turn needs the STRICT verdict; an ordinary turn keeps today's posture (#20195)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from autobot_shared.ai_lines import ATTACHMENT_CHAT_KEY, ATTACHMENT_TURN_KEY


def _graph(context=None, broken=False):
    graph = MagicMock()
    if broken:
        graph.aget_state = AsyncMock(side_effect=ConnectionError("down"))
    else:
        graph.aget_state = AsyncMock(return_value=SimpleNamespace(values={"context": context or {}}))
    return graph


async def _resume(strict: bool, graph):
    from api.chat import resume_chat_graph

    streamed = MagicMock(return_value=iter(()))
    with (
        patch("api.chat.get_chat_workflow_manager", AsyncMock(return_value=MagicMock())),
        patch("api.chat_streaming.attachments_allowed", AsyncMock(return_value=strict)),
        patch("chat_workflow.graph.get_compiled_graph", AsyncMock(return_value=graph)),
        patch("api.chat._stream_graph_resume", streamed),
    ):
        try:
            response = await resume_chat_graph(
                chat_id="chat-1",
                current_user={"user_id": "u1"},
                request_data={"approved": True},
                request=MagicMock(),
                ownership={},
            )
        except HTTPException as exc:
            return exc.status_code, streamed
    return response.status_code, streamed


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [ATTACHMENT_TURN_KEY, ATTACHMENT_CHAT_KEY])
async def test_a_shared_user_cannot_approve_an_attachment_turn_or_chat(key):
    status, streamed = await _resume(False, _graph({key: True}))
    assert status == 404 and not streamed.called  # same answer as a foreign conversation; nothing resumed


@pytest.mark.asyncio
async def test_the_owner_can_approve_an_attachment_turn():
    status, streamed = await _resume(True, _graph({ATTACHMENT_TURN_KEY: True}))
    assert status == 200 and streamed.call_args.args[-1] is True


@pytest.mark.asyncio
async def test_an_ordinary_turn_is_unchanged_for_a_non_strict_caller():
    status, streamed = await _resume(False, _graph({"attachments": []}))
    assert status == 200 and streamed.call_args.args[-1] is False


@pytest.mark.asyncio
async def test_an_unreadable_checkpoint_refuses_a_non_strict_caller():
    status, streamed = await _resume(False, _graph(broken=True))
    assert status == 404 and not streamed.called
