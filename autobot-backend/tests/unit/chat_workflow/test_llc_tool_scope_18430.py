# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An LLC work-object tool is scoped by the VERIFIED company, never by the request's own claim (#18430).

``_handle_llc_tool`` used to read ``ctx.context["company_id"]``, which is copied from the client's request: a
caller naming another company's id mutated that company's work objects. It reads ``verified_company_id`` now,
and a session with none (or a malformed one) is refused rather than sent to ``dispatch_llc_tool`` unscoped.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow.tool_handler import ToolHandlerMixin

VERIFIED = "00000000-0000-0000-0000-0000000000c1"
CLAIMED = "00000000-0000-0000-0000-0000000000c2"


async def _run(context):
    handler = ToolHandlerMixin.__new__(ToolHandlerMixin)
    results: list = []
    call = {"name": "create_task", "params": {"title": "x"}, "description": ""}
    dispatch = AsyncMock(return_value={"status": "success"})
    with patch("chat_workflow.tool_handler.dispatch_llc_tool", dispatch):
        messages = [
            m
            async for m in handler._handle_llc_tool(
                "create_task", call, results, SimpleNamespace(context=context), "s", "operator"
            )
        ]
    return dispatch, messages, results


@pytest.mark.asyncio
async def test_the_verified_company_scopes_the_tool_and_the_requests_claim_is_ignored():
    dispatch, _, _ = await _run({"company_id": CLAIMED, "verified_company_id": VERIFIED, "user_id": "claimed-user"})
    dispatch.assert_awaited_once()
    assert dispatch.await_args.args[2] == VERIFIED  # not the claimed company
    assert dispatch.await_args.args[3] != "claimed-user"  # the actor is not the claimed user either


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context",
    [
        {"company_id": CLAIMED},  # only the client's claim
        {"company_id": CLAIMED, "verified_user_id": "00000000-0000-0000-0000-000000000042"},  # a user, no company
        {"verified_company_id": "not-a-uuid"},
        {"verified_company_id": ""},
        {},
    ],
)
async def test_a_session_with_no_verified_company_is_refused_and_nothing_is_dispatched(context):
    dispatch, messages, results = await _run(context)
    dispatch.assert_not_awaited()
    assert messages[-1].type == "error" and "verified company" in messages[-1].content
    assert results[-1]["status"] == "error"
