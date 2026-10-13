# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat tool seam resolves each tool ACTION's AI line (#18430).

Same call, different line, different outcome: line 1 passes through, line 2 is held with a pending
approval, line 3 is refused. The contrasts are in the same test so a seam that ignored the line would
fail on one side of each.
"""

from types import SimpleNamespace

import pytest

from autobot_shared.ai_lines import AiLine
from tests.unit.chat_workflow.test_ai_line_support import VERIFIED_COMPANY, arun_guard

L1, L2, L3 = AiLine.AUTONOMOUS, AiLine.DRAFT_THEN_SEND, AiLine.NEVER
RELAXED = ["pushing commits", "sending externally"]


def _ctx(**kw) -> SimpleNamespace:
    base = {
        "requires_approval_before": [],
        "work_item_id": None,
        "context": {"verified_company_id": VERIFIED_COMPANY},
        "session_id": "s",
    }
    return SimpleNamespace(**{**base, **kw})


@pytest.mark.asyncio
async def test_each_action_of_one_tool_gets_its_own_line():
    lines = {"crm:read": L1, "crm:send": L2, "crm:delete": L3}
    outcomes = {}
    for action in ("read", "send", "delete"):
        results: list = []
        message, filed = await arun_guard({"name": "crm", "params": {"action": action}}, _ctx(), results, stored=lines)
        outcomes[action] = (message and message.type, filed, results and results[0]["status"])
    assert outcomes == {
        "read": (None, 0, []),
        "send": ("approval_required", 1, "pending_approval"),
        "delete": ("error", 0, "error"),
    }


@pytest.mark.asyncio
async def test_a_refusal_carries_the_line_and_is_not_an_approval_request():
    results: list = []
    message, filed = await arun_guard(
        {"name": "crm", "params": {"action": "delete"}}, _ctx(), results, stored={"crm:delete": L3}
    )
    assert message.metadata["error"] is True and message.metadata["approval_required"] is False
    assert message.metadata["line"] == "never" and filed == 0 and "never touches" in message.content


@pytest.mark.asyncio
async def test_a_held_call_reports_its_approval_so_the_person_can_find_it():
    message, _ = await arun_guard({"name": "crm", "params": {"action": "send"}}, _ctx(), [], stored={"crm:send": L2})
    assert message.metadata["approval_id"] and message.metadata["line"] == "draft_then_send"


@pytest.mark.asyncio
async def test_a_persons_yes_covers_only_the_calls_they_were_shown_and_never_line_three():
    from services.ai_line_enforcement import shown_call_fingerprint

    lines = {"crm:send": L2, "crm:delete": L3}
    send = {"name": "crm", "params": {"action": "send", "to": "a"}}
    other = {"name": "crm", "params": {"action": "send", "to": "b"}}
    delete = {"name": "crm", "params": {"action": "delete"}}
    shown = frozenset({shown_call_fingerprint("crm", send["params"]), shown_call_fingerprint("crm", delete["params"])})
    held, _ = await arun_guard(send, _ctx(), [], stored=lines)
    passed, _ = await arun_guard(send, _ctx(approved_fingerprints=shown), [], stored=lines)
    not_shown, _ = await arun_guard(other, _ctx(approved_fingerprints=shown), [], stored=lines)
    refused, _ = await arun_guard(delete, _ctx(approved_fingerprints=shown), [], stored=lines)
    assert (held.type, passed, not_shown.type, refused.type) == (
        "approval_required",
        None,
        "approval_required",
        "error",
    )


@pytest.mark.asyncio
async def test_a_request_cannot_satisfy_line_two_through_its_own_context():
    ctx = _ctx(
        context={"verified_company_id": VERIFIED_COMPANY, "approved_fingerprints": ["x"], "person_approved": True}
    )
    message, _ = await arun_guard({"name": "crm", "params": {"action": "send"}}, ctx, [], stored={"crm:send": L2})
    assert message is not None and message.type == "approval_required"


@pytest.mark.asyncio
async def test_the_requests_own_company_claim_never_scopes_a_decision():
    """A caller naming another company (or none) must not skip the stored `never` of the authenticated one."""
    ctx = _ctx(context={"company_id": "00000000-0000-0000-0000-000000000099"})
    message, _ = await arun_guard(
        {"name": "crm", "params": {"action": "delete"}}, ctx, [], verified_company=False, stored={"crm:delete": L3}
    )
    assert message.type == "error" and message.metadata["line"] == "never"  # no verified company: refused outright


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [None, "", "not-a-uuid", "12345"])
async def test_a_missing_or_malformed_verified_company_refuses_a_mutating_action(bad):
    ctx = _ctx(context={"verified_company_id": bad})
    message, filed = await arun_guard({"name": "write_file", "params": {}}, ctx, [], verified_company=False, stored=L1)
    assert message.type == "error" and filed == 0
    # Contrast: a tool the catalogue knows is a read still runs without a company.
    read, _ = await arun_guard({"name": "read_file", "params": {}}, ctx, [], verified_company=False)
    assert read is None


@pytest.mark.asyncio
async def test_an_unknown_tool_is_held_when_unset_and_a_known_read_runs():
    held, filed = await arun_guard({"name": "some_mcp_tool", "params": {}}, _ctx(), [])
    free, _ = await arun_guard({"name": "get_text", "params": {}}, _ctx(), [])
    reply, _ = await arun_guard({"name": "respond", "params": {}}, _ctx(), [])
    assert held.type == "approval_required" and filed == 1
    assert free is None and reply is None


@pytest.mark.asyncio
async def test_a_work_item_category_still_holds_a_tool_the_company_set_to_line_one():
    ctx = _ctx(requires_approval_before=["pushing commits"], work_item_id="wi-1")
    held, _ = await arun_guard({"name": "git_push"}, ctx, [], stored=L1, slm_relaxed=RELAXED)
    free, _ = await arun_guard({"name": "git_push"}, _ctx(), [], stored=L1, slm_relaxed=RELAXED)
    assert held is not None and held.metadata["category"] == "pushing commits"
    assert free is None  # contrast: no declaration, category relaxed, line 1 set -> it runs


@pytest.mark.asyncio
async def test_an_unreadable_store_refuses_rather_than_runs():
    message, filed = await arun_guard({"name": "crm", "params": {"action": "read"}}, _ctx(), [], store_unavailable=True)
    assert message.type == "error" and filed == 0


USER = "00000000-0000-0000-0000-000000000042"


def _me(**kw) -> SimpleNamespace:
    """A signed-in user with NO company: only the verified user id."""
    return _ctx(context={"verified_user_id": USER}, **kw)


@pytest.mark.asyncio
async def test_a_user_with_no_company_gets_line_two_and_can_approve_their_own_shown_call():
    from services.ai_line_enforcement import shown_call_fingerprint

    call = {"name": "write_file", "params": {"path": "a.md"}}
    held, filed = await arun_guard(call, _me(), [], verified_company=False, slm_relaxed=["writing files"])
    shown = frozenset({shown_call_fingerprint("write_file", call["params"])})
    passed, _ = await arun_guard(
        call, _me(approved_fingerprints=shown), [], verified_company=False, slm_relaxed=["writing files"]
    )
    assert held.type == "approval_required" and filed == 1 and passed is None


@pytest.mark.asyncio
async def test_a_user_with_no_company_runs_a_read_and_a_forged_company_is_still_refused():
    read, _ = await arun_guard({"name": "read_file", "params": {}}, _me(), [], verified_company=False)
    assert read is None
    forged = _ctx(context={"verified_company_id": "not-a-uuid", "verified_user_id": USER})
    refused, filed = await arun_guard(
        {"name": "write_file", "params": {}}, forged, [], verified_company=False, stored=L1
    )
    assert refused.type == "error" and filed == 0
