# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""On a turn that carries attached files, EVERY tool call asks, pre-approved or not (#20195).

Attached text is untrusted data in the prompt. The maintainer ruling: no pre-approval applies on such a turn, so
the contrasts below put the SAME call on a normal turn (runs without asking) and on an attachment turn (held).
The gate is the existing AI-line floor (``role_requires_approval`` of ``resolve_line``); nothing new decides.
"""

import asyncio

import pytest

from autobot_shared.ai_lines import ATTACHMENT_TURN_KEY, VERIFIED_COMPANY_KEY, VERIFIED_USER_KEY, AiLine
from chat_workflow.attachment_context import apply_attachments
from chat_workflow.models import LLMIterationContext
from chat_workflow.run_authority import Inheritance
from services.ai_line_enforcement import call_needs_approval, shown_call_fingerprint
from tests.unit.chat_workflow.test_ai_line_support import VERIFIED_COMPANY, arun_guard

L1, L3 = AiLine.AUTONOMOUS, AiLine.NEVER
_READ = {"name": "crm", "params": {"action": "read"}}  # pre-approved: the user stored line 1 ("always allow")


def _ctx(attachment_turn: bool, **kw) -> LLMIterationContext:
    context = {VERIFIED_COMPANY_KEY: VERIFIED_COMPANY, **({ATTACHMENT_TURN_KEY: True} if attachment_turn else {})}
    return LLMIterationContext(
        ollama_endpoint="e",
        selected_model="m",
        session_id="s",
        terminal_session_id="t",
        used_knowledge=False,
        rag_citations=[],
        workflow_messages=[],
        context=context,
        **kw,
    )


async def _run(call, attachment_turn, **world):
    results: list = []
    message, filed = await arun_guard(call, _ctx(attachment_turn), results, **world)
    return (message and message.type), filed


@pytest.mark.asyncio
async def test_a_pre_approved_tool_runs_on_a_normal_turn_and_asks_on_an_attachment_turn():
    stored = {"crm:read": L1}
    assert await _run(_READ, False, stored=stored) == (None, 0)
    assert await _run(_READ, True, stored=stored) == ("approval_required", 1)


@pytest.mark.asyncio
async def test_a_category_the_admin_relaxed_still_asks_on_an_attachment_turn():
    world = {"stored": {"crm:read": L1}, "slm_relaxed": ["sending externally", "pushing commits"]}
    assert await _run(_READ, False, **world) == (None, 0)
    assert await _run(_READ, True, **world) == ("approval_required", 1)


@pytest.mark.asyncio
async def test_a_tool_no_line_manages_asks_on_an_attachment_turn_only():
    unmanaged = {"name": "file_search", "params": {"query": "x"}}  # read-only: free on a normal turn
    assert await _run(unmanaged, False) == (None, 0)
    assert await _run(unmanaged, True) == ("approval_required", 1)


@pytest.mark.asyncio
async def test_the_two_conversation_tools_stay_free_or_the_turn_could_not_answer():
    for name in ("respond", "request_approval"):
        assert await _run({"name": name, "params": {}}, True) == (None, 0), name


@pytest.mark.asyncio
async def test_a_line_three_action_is_still_refused_not_merely_held():
    assert await _run(_READ, True, stored={"crm:read": L3}) == ("error", 0)


@pytest.mark.asyncio
async def test_a_persons_yes_to_the_shown_call_lets_exactly_that_call_run_on_an_attachment_turn():
    stored = {"crm:read": L1}
    shown = frozenset({shown_call_fingerprint("crm", _READ["params"])})
    ctx = _ctx(True, approved_fingerprints=shown)
    assert await arun_guard(_READ, ctx, [], stored=stored) == (None, 0)
    other = {"name": "crm", "params": {"action": "read", "id": "2"}}
    message, filed = await arun_guard(other, ctx, [], stored={"crm:read": L1})
    assert (message.type, filed) == ("approval_required", 1)


@pytest.mark.asyncio
async def test_the_plan_time_interrupt_agrees_with_the_dispatch_seam():
    from tests.unit.chat_workflow.test_ai_line_support import ai_line_world

    with ai_line_world(stored={"crm:read": L1}):
        assert await call_needs_approval(_READ, _ctx(False)) is False
        assert await call_needs_approval(_READ, _ctx(True)) is True


def test_a_delegated_subagent_inherits_the_gate_and_the_out_of_process_engine_refuses_to_run():
    assert Inheritance.of(_ctx(True)).approve_every_call is True
    assert Inheritance.of(_ctx(False)).approve_every_call is False
    from chat_workflow.delegation import _run_claude_code_subagent

    with pytest.raises(ValueError, match="cannot ask per call"):
        asyncio.run(_run_claude_code_subagent("t", "research_agent", 0, "user", Inheritance.of(_ctx(True))))


class _Session:
    session_id = "s"
    metadata: dict = {}


@pytest.mark.asyncio
async def test_the_turn_is_stamped_only_when_attachments_are_named_and_a_forged_stamp_is_cleared(monkeypatch):
    async def _no_files():
        return None

    async def _mark(_session_id):
        return None

    monkeypatch.setattr("chat_workflow.attachment_context._file_manager", _no_files)
    monkeypatch.setattr("chat_workflow.attachment_floor.mark_chat", _mark)  # the Redis record has its own tests
    params = {"prompt": "p", "model": "m"}
    forged = {ATTACHMENT_TURN_KEY: True, VERIFIED_USER_KEY: "u"}
    await apply_attachments(_Session(), forged, dict(params))
    assert ATTACHMENT_TURN_KEY not in forged  # a normal turn behaves as before
    named = {"attachments": ["id-1"], VERIFIED_USER_KEY: "u"}
    await apply_attachments(_Session(), named, dict(params))
    assert named[ATTACHMENT_TURN_KEY] is True  # even when nothing could be read: the ids were named
