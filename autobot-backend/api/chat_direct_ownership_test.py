# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`/chat/direct` must refuse a chat the caller does not own (#13982).

The endpoint took `chat_id` from the request body and validated nothing, while
its sibling `/chats/{chat_id}/message` declared `Depends(validate_chat_ownership)`.
Authentication was required, so this was never anonymous — the missing boundary
was between authenticated users.

It matters more than message injection because this endpoint carries approval and
denial decisions: resolving another user's pending command approval, and with
`remember_choice` persisting that decision for their future turns.

These tests assert **behaviour**, not that a string appears in the source. A
source-inspection test passes on a check that is present but never reached, which
is the failure mode worth guarding against here.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import chat as chat_api


def _forbidden(*_args, **_kwargs):
    raise HTTPException(status_code=403, detail="not your session")


class TestOwnershipIsEnforced:
    @pytest.mark.asyncio
    async def test_a_non_owner_is_refused(self):
        with patch.object(chat_api, "validate_chat_ownership", side_effect=_forbidden):
            with pytest.raises(HTTPException) as excinfo:
                await chat_api.send_direct_chat_response(
                    current_user={"username": "mallory", "role": "user"},
                    request=MagicMock(),
                    message="approve",
                    chat_id="someone-elses-chat",
                    remember_choice=False,
                )

        assert excinfo.value.status_code == 403

    @pytest.mark.asyncio
    async def test_the_refusal_happens_before_any_workflow_work(self):
        """A check that runs after the side effect is not a check.

        `remember_choice` persists a decision, so reaching the workflow at all
        before the boundary holds would already have done the damage.
        """
        manager = AsyncMock()
        with patch.object(chat_api, "validate_chat_ownership", side_effect=_forbidden):
            with patch.object(chat_api, "get_chat_workflow_manager", manager):
                with pytest.raises(HTTPException):
                    await chat_api.send_direct_chat_response(
                        current_user={"username": "mallory", "role": "user"},
                        request=MagicMock(),
                        message="approve",
                        chat_id="someone-elses-chat",
                        remember_choice=True,
                    )

        manager.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_validated_chat_id_is_the_one_actually_used(self):
        """The subtle failure: validating a different id than the request acts on.

        `Depends(validate_chat_ownership)` resolves `chat_id` as a path parameter,
        and this endpoint takes it from the body — so wiring it as a dependency
        would have checked one value and streamed into another. This pins that
        the body value is what gets validated.
        """
        seen = {}

        async def _record(chat_id, request):  # noqa: ARG001
            seen["chat_id"] = chat_id
            return {"authorized": True}

        with patch.object(chat_api, "validate_chat_ownership", _record):
            with patch.object(chat_api, "get_chat_workflow_manager", AsyncMock(return_value=MagicMock())):
                with patch.object(chat_api, "_validate_workflow_manager", MagicMock()):
                    with patch.object(chat_api, "_create_streaming_response", MagicMock(return_value="streamed")):
                        result = await chat_api.send_direct_chat_response(
                            current_user={"username": "alice", "role": "user"},
                            request=MagicMock(),
                            message="approve",
                            chat_id="alices-chat",
                            remember_choice=False,
                        )

        assert seen["chat_id"] == "alices-chat"
        assert result == "streamed", "the owner must still reach the stream — no regression"


class TestTheOwnerIsUnaffected:
    @pytest.mark.asyncio
    async def test_the_owner_still_reaches_the_workflow(self):
        manager = MagicMock()
        with patch.object(chat_api, "validate_chat_ownership", AsyncMock(return_value={"authorized": True})):
            with patch.object(chat_api, "get_chat_workflow_manager", AsyncMock(return_value=manager)) as getter:
                with patch.object(chat_api, "_validate_workflow_manager", MagicMock()):
                    with patch.object(chat_api, "_create_streaming_response", MagicMock(return_value="streamed")):
                        result = await chat_api.send_direct_chat_response(
                            current_user={"username": "alice", "role": "user"},
                            request=MagicMock(),
                            message="approve",
                            chat_id="alices-chat",
                            remember_choice=True,
                        )

        getter.assert_awaited_once()
        assert result == "streamed"
