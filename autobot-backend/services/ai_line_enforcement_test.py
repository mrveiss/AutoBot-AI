# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The three AI lines at the single enforcement point, against a real store and real approvals (#18430).

Each line is tested per tool ACTION, and each with its contrast: the same call under the line next to it
must come out the other way. The store, the approvals and the line-change path are real (in-memory
database); only the SLM setting (the approval baseline) and the audit sink are stubbed.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.ai_lines import SCOPE_COMPANY, SCOPE_USER, AiLine, LineScope
from autobot_shared.tool_catalogue import valid_approval_categories
from chat_workflow import approval_baseline as baseline
from llc.models.ai_line import LLCAiLine
from llc.services.ai_lines import record_approved_line, stored_line
from llc.tests import _e2e_harness as harness
from models.approval import Approval, ApprovalComment, ApprovalStatus, TaskApprovalLink
from services import ai_line_enforcement as enforcement
from services.ai_line_enforcement import Outcome, enforce_line, shown_call_fingerprint
from user_management.models.base import Base

COMPANY, OTHER_COMPANY = uuid.uuid4(), uuid.uuid4()
ALL_RELAXED = sorted(valid_approval_categories())
L1, L2, L3 = AiLine.AUTONOMOUS, AiLine.DRAFT_THEN_SEND, AiLine.NEVER


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    tables = [
        Approval.__table__,
        ApprovalComment.__table__,
        TaskApprovalLink.__table__,
        LLCAiLine.__table__,
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest.fixture
def world(factory):
    """Real store and approvals; the SLM relaxation is per-test via ``relaxed``."""
    state = {"relaxed": None}

    @contextmanager
    def _patched():
        with (
            patch.object(baseline, "fetch_slm_policy_json", AsyncMock(side_effect=lambda _k: state["relaxed"])),
            patch.object(enforcement, "get_async_session_factory", lambda: factory),
            patch.object(enforcement, "audit_log", AsyncMock(return_value=True)) as audit,
            patch("events.bus.publish_event", AsyncMock()),
        ):
            yield audit

    with _patched() as audit:
        state["audit"] = audit
        yield state


async def _set(factory, key, line, company=COMPANY):
    async with factory() as session:
        await record_approved_line(
            session, company_id=company, key=key, line=line, approval_id=uuid.uuid4(), decided_by="owner"
        )
        await session.commit()


async def _approvals(factory) -> list[Approval]:
    async with factory() as session:
        return list((await session.execute(sa.select(Approval))).scalars().all())


def _shown(tool, params):
    return frozenset({shown_call_fingerprint(tool, params)})


async def _act(tool, params=None, company=COMPANY, **kw):
    return await enforce_line(
        tool_name=tool, params=params or {}, company_id=str(company), requested_by="agent-1", surface="test", **kw
    )


# -- the three lines, per action of one tool (the owner's CRM example) -------------------------------------


async def test_one_tool_three_actions_three_lines(factory, world):
    await _set(factory, "crm:read", L1)
    await _set(factory, "crm:send", L2)
    await _set(factory, "crm:delete", L3)

    read = await _act("crm", {"action": "read"})
    send = await _act("crm", {"action": "send", "to": "lead@example.test"})
    delete = await _act("crm", {"action": "delete"})

    assert (read.outcome, send.outcome, delete.outcome) == (Outcome.RUN, Outcome.HOLD, Outcome.REFUSE)
    assert read.approval_id is None and delete.approval_id is None  # only line 2 files an approval
    assert send.approval_recorded and send.approval_id


async def test_line_one_runs_and_reports(factory, world):
    await _set(factory, "write_file", L1)
    verdict = await _act("write_file", {"path": "a.md"})
    # The category baseline is on (nothing relaxed), so line 1 is lifted to 2 ...
    assert verdict.outcome is Outcome.HOLD and verdict.resolution.source == "baseline_floor"
    world["relaxed"] = ["writing files"]
    # ... and only when an administrator relaxes the category does line 1 hold.
    verdict = await _act("write_file", {"path": "a.md"})
    assert verdict.outcome is Outcome.RUN
    assert world["audit"].await_args.args[0] == "ai_line.run"  # "then reports"
    assert len(await _approvals(factory)) == 1  # the earlier hold only; the run filed nothing


async def test_line_two_creates_a_pending_approval_and_does_not_run(factory, world):
    await _set(factory, "crm:send", L2)
    verdict = await _act("crm", {"action": "send", "body": "hello"})
    [approval] = await _approvals(factory)
    assert verdict.outcome is Outcome.HOLD and str(approval.id) == verdict.approval_id
    assert approval.status == ApprovalStatus.PENDING.value and approval.company_id == COMPANY
    assert approval.context["action_key"] == "crm:send" and approval.context["params"]["body"] == "hello"
    assert "action" not in approval.context  # nothing is dispatched on approval: a person sends it


async def test_line_three_refuses_even_when_a_person_approved_in_the_interrupt(factory, world):
    await _set(factory, "crm:delete", L3)
    plain = await _act("crm", {"action": "delete"})
    approved = await _act("crm", {"action": "delete"}, approved_fingerprints=_shown("crm", {"action": "delete"}))
    assert plain.outcome is approved.outcome is Outcome.REFUSE
    assert await _approvals(factory) == []


async def test_a_person_approved_batch_satisfies_line_two_only(factory, world):
    await _set(factory, "crm:send", L2)
    assert (await _act("crm", {"action": "send"})).outcome is Outcome.HOLD
    assert (
        await _act("crm", {"action": "send"}, approved_fingerprints=_shown("crm", {"action": "send"}))
    ).outcome is Outcome.RUN
    # A yes bound to a DIFFERENT call (other params) does not carry over.
    elsewhere = _shown("crm", {"action": "send", "to": "someone-else"})
    assert (await _act("crm", {"action": "send"}, approved_fingerprints=elsewhere)).outcome is Outcome.HOLD


async def test_the_tool_level_line_is_the_fallback_for_an_action_with_no_line_of_its_own(factory, world):
    await _set(factory, "crm", L3)
    await _set(factory, "crm:read", L1)
    assert (await _act("crm", {"action": "read"})).outcome is Outcome.RUN
    assert (await _act("crm", {"action": "anything-else"})).outcome is Outcome.REFUSE


# -- unset behaves as line two -------------------------------------------------------------------------


async def test_an_unset_mutating_action_behaves_as_line_two_and_files_an_approval(factory, world):
    world["relaxed"] = ALL_RELAXED  # no baseline in the way: the default alone decides
    unset = await _act("write_file", {"path": "a.md"})
    await _set(factory, "create_file", L1)
    set_line_one = await _act("create_file", {"path": "b.md"})
    assert unset.outcome is Outcome.HOLD and unset.resolution.source == "default"
    assert set_line_one.outcome is Outcome.RUN  # contrast: the same shape of call once line 1 is set
    assert len(await _approvals(factory)) == 1


async def test_a_read_that_changes_nothing_is_not_managed(factory, world):
    verdict = await _act("read_file", {"path": "a.md"})
    assert verdict.outcome is Outcome.RUN and verdict.resolution.source == "unmanaged"


# -- baseline-sensitive categories can never be line one ---------------------------------------------


@pytest.mark.parametrize(
    ("tool", "category"),
    [("run_shell", "executing code"), ("create_file", "writing files"), ("set_redis_value", "writing data")],
)
async def test_a_baseline_category_is_never_line_one(factory, world, tool, category):
    await _set(factory, tool, L1)
    held = await _act(tool)
    world["relaxed"] = [category]
    lifted = await _act(tool)
    assert held.outcome is Outcome.HOLD and held.resolution.floor_category == category
    assert lifted.outcome is Outcome.RUN  # contrast: relaxed by the administrator, then line 1 holds


async def test_an_unreachable_slm_fails_closed(factory, world):
    await _set(factory, "create_file", L1)
    world["relaxed"] = None  # the SLM returned nothing
    assert (await _act("create_file")).outcome is Outcome.HOLD


async def test_an_unreadable_baseline_gates_every_category(factory, world):
    await _set(factory, "create_file", L1)
    with patch.object(baseline, "baseline_approval_categories", AsyncMock(side_effect=RuntimeError("slm down"))):
        assert (await _act("create_file")).outcome is Outcome.HOLD


async def test_a_declared_category_extends_the_baseline_and_never_shrinks_it(factory, world):
    world["relaxed"] = ["publishing"]
    await _set(factory, "publish", L1)
    assert (await _act("publish")).outcome is Outcome.RUN
    assert (await _act("publish", declared_categories=["publishing"])).outcome is Outcome.HOLD


# -- fail closed, scope, duplicates, redaction ------------------------------------------------------------


async def test_an_unreadable_line_store_refuses(factory, world):
    with patch.object(enforcement, "stored_line", AsyncMock(side_effect=RuntimeError("db down"))):
        verdict = await _act("crm", {"action": "read"})
    assert verdict.outcome is Outcome.REFUSE and verdict.resolution.source == "store_unavailable"


async def test_an_approval_that_cannot_be_recorded_still_does_not_run(factory, world):
    await _set(factory, "crm:send", L2)
    with patch.object(enforcement, "_file_hold", AsyncMock(side_effect=RuntimeError("db down"))):
        verdict = await _act("crm", {"action": "send"})
    assert verdict.outcome is Outcome.HOLD and not verdict.approval_recorded and verdict.approval_id is None


async def test_a_line_is_per_company(factory, world):
    await _set(factory, "crm:read", L1)
    await _set(factory, "crm:send", L3, company=OTHER_COMPANY)
    assert (await _act("crm", {"action": "read"})).outcome is Outcome.RUN
    assert (await _act("crm", {"action": "read"}, company=OTHER_COMPANY)).resolution.source == "default"
    assert (await _act("crm", {"action": "send"}, company=OTHER_COMPANY)).outcome is Outcome.REFUSE
    assert (await _act("crm", {"action": "send"})).resolution.source == "default"  # company A never set it


async def test_the_same_held_call_files_one_approval(factory, world):
    await _set(factory, "crm:send", L2)
    first = await _act("crm", {"action": "send", "to": "a"})
    again = await _act("crm", {"action": "send", "to": "a"})
    other = await _act("crm", {"action": "send", "to": "b"})
    assert first.approval_id == again.approval_id != other.approval_id
    assert len(await _approvals(factory)) == 2


async def test_a_credential_in_the_params_is_not_stored_in_the_approval(factory, world):
    await _set(factory, "crm:send", L2)
    secret = "sk-live-abcdef1234567890"  # pragma: allowlist secret
    await _act("crm", {"action": "send", "api_key": secret, "to": "a"})
    [approval] = await _approvals(factory)
    assert secret not in str(approval.context)
    assert approval.context["params"]["to"] == "a"


async def test_a_stored_value_that_is_not_a_line_is_read_as_never(factory, world):
    async with factory() as session:
        session.add(LLCAiLine(id=uuid.uuid4(), company_id=COMPANY, action_key="crm", line="allow-everything"))
        await session.commit()
        assert await stored_line(session, COMPANY, "crm") is L3


# -- agents never change a line --------------------------------------------------------------------------


async def test_the_line_store_has_no_write_path_an_agent_reaches(factory, world):
    """A held tool call and a propose-request both leave the store untouched; only an approval moves it."""
    await _set(factory, "crm:send", L2)
    await _act("crm", {"action": "send"})
    async with factory() as session:
        assert await stored_line(session, COMPANY, "crm:send") is L2
        rows = (await session.execute(sa.select(LLCAiLine))).scalars().all()
        assert [(r.action_key, r.line) for r in rows] == [("crm:send", "draft_then_send")]


async def test_proposing_a_change_changes_nothing_until_a_person_approves(factory, world):
    from services.ai_line_change_proposal import propose_line_change

    with patch("services.ai_line_change_proposal.get_async_session_factory", lambda: factory):
        scope = LineScope(SCOPE_COMPANY, COMPANY)
        proposed = await propose_line_change(scope=scope, key="crm:send", line=L1, requested_by="u")
        again = await propose_line_change(scope=scope, key="CRM:send", line=L1, requested_by="u")
    assert proposed.status == "pending" and again.id == proposed.id  # reused, not duplicated
    async with factory() as session:
        assert await stored_line(session, COMPANY, "crm:send") is None


async def test_the_handler_refuses_an_approval_that_is_not_approved_or_has_no_company(factory, world):
    from services.ai_line_change_action import ACTION, execute_line_change

    async with factory() as session:
        pending = Approval(
            title="t", approval_type="workflow_gate", status="pending", company_id=COMPANY,
            context={"action": ACTION, "action_key": "crm", "line": "autonomous"},
        )  # fmt: skip
        no_company = Approval(
            title="t", approval_type="workflow_gate", status="approved", company_id=None,
            context={"action": ACTION, "action_key": "crm", "line": "autonomous"},
        )  # fmt: skip
        bad_line = Approval(
            title="t", approval_type="workflow_gate", status="approved", company_id=COMPANY,
            context={"action": ACTION, "action_key": "crm", "line": "anything"},
        )  # fmt: skip
        for approval in (pending, no_company, bad_line):
            with pytest.raises(ValueError):
                await execute_line_change(approval, session)
        assert await stored_line(session, COMPANY, "crm") is None


# -- company scope, unknown tools, the HMAC fingerprint ---------------------------------------------------


@pytest.mark.parametrize("bad", [None, "", "not-a-uuid"])
async def test_a_missing_or_malformed_company_refuses_a_mutating_action(factory, world, bad):
    world["relaxed"] = ALL_RELAXED
    refused = await enforce_line(tool_name="write_file", params={}, company_id=bad, requested_by="a", surface="t")
    read = await enforce_line(tool_name="read_file", params={}, company_id=bad, requested_by="a", surface="t")
    assert refused.outcome is Outcome.REFUSE and refused.resolution.source == "no_verified_company"
    assert read.outcome is Outcome.RUN  # contrast: a tool the catalogue knows is a read


async def test_an_unknown_tool_is_held_when_unset_and_runs_once_a_line_one_is_set(factory, world):
    held = await _act("some_mcp_tool", {"x": 1})
    await _set(factory, "some_mcp_tool", L1)
    world["relaxed"] = ALL_RELAXED
    freed = await _act("some_mcp_tool", {"x": 1})
    assert held.outcome is Outcome.HOLD and held.resolution.source == "default"
    assert freed.outcome is Outcome.RUN


def test_the_fingerprint_is_an_hmac_of_the_raw_call_and_is_not_the_plain_hash():
    import hashlib
    import json

    params = {"action": "send", "api_key": "k1"}  # pragma: allowlist secret
    fp = shown_call_fingerprint("crm", params)
    plain = hashlib.sha256(json.dumps({"k": "crm:send", "p": params}, sort_keys=True).encode()).hexdigest()
    assert fp != plain and len(fp) == 64
    assert fp == shown_call_fingerprint("crm", dict(params))
    assert fp != shown_call_fingerprint("crm", {**params, "api_key": "k2"})  # pragma: allowlist secret
    with patch.object(enforcement, "_fingerprint_key", lambda: b"another-key-" * 3):
        assert shown_call_fingerprint("crm", params) != fp  # keyed: the digest cannot be recomputed without the secret


# -- personal scope: a user with no company (owner decision, #18430) -----------------------------------------

USER = uuid.UUID(int=18432)
OTHER_USER = uuid.UUID(int=18433)


async def _me(tool, params=None, user=USER, company=None, **kw):
    return await enforce_line(
        tool_name=tool, params=params or {}, company_id=company, user_id=str(user), requested_by="s", surface="t", **kw
    )


async def test_a_user_with_no_company_gets_line_two_for_an_unset_mutating_action_and_can_approve_it(factory, world):
    world["relaxed"] = ALL_RELAXED
    verdict = await _me("write_file", {"path": "a.md"})
    [approval] = await _approvals(factory)
    assert verdict.outcome is Outcome.HOLD and verdict.resolution.source == "default"
    assert approval.company_id is None and approval.context["scope_kind"] == "user"
    assert approval.context["scope_id"] == str(USER)
    # Self-approval: a yes bound to exactly this call carries it.
    shown = _shown("write_file", {"path": "a.md"})
    assert (await _me("write_file", {"path": "a.md"}, approved_fingerprints=shown)).outcome is Outcome.RUN
    assert (await _me("write_file", {"path": "b.md"}, approved_fingerprints=shown)).outcome is Outcome.HOLD


async def test_a_user_with_no_company_runs_a_known_read(factory, world):
    assert (await _me("read_file", {"path": "a.md"})).outcome is Outcome.RUN


async def test_a_forged_company_is_still_refused_even_for_a_signed_in_user(factory, world):
    world["relaxed"] = ALL_RELAXED
    for forged in ("not-a-uuid", "12345"):
        verdict = await _me("write_file", company=forged)
        assert verdict.outcome is Outcome.REFUSE and verdict.resolution.source == "no_verified_company"
    assert await _approvals(factory) == []


async def test_personal_lines_apply_to_the_user_and_to_nobody_else(factory, world):
    world["relaxed"] = ALL_RELAXED
    async with factory() as session:
        await record_approved_line(
            session,
            company_id=USER,
            kind=SCOPE_USER,
            key="write_file",
            line=L1,
            approval_id=uuid.uuid4(),
            decided_by="me",
        )
        await record_approved_line(
            session,
            company_id=USER,
            kind=SCOPE_USER,
            key="crm:delete",
            line=L3,
            approval_id=uuid.uuid4(),
            decided_by="me",
        )
        await session.commit()
    assert (await _me("write_file")).outcome is Outcome.RUN
    assert (await _me("crm", {"action": "delete"})).outcome is Outcome.REFUSE
    assert (await _me("write_file", user=OTHER_USER)).outcome is Outcome.HOLD  # someone else's scope: unset
    # The same id as a COMPANY is a different scope: a personal line never leaks into a company, or back.
    assert (await _act("write_file", company=USER)).outcome is Outcome.HOLD


async def test_with_a_company_the_company_scope_applies_not_the_personal_one(factory, world):
    world["relaxed"] = ALL_RELAXED
    async with factory() as session:
        await record_approved_line(
            session,
            company_id=USER,
            kind=SCOPE_USER,
            key="write_file",
            line=L1,
            approval_id=uuid.uuid4(),
            decided_by="me",
        )
        await session.commit()
    assert (await _me("write_file", company=COMPANY)).outcome is Outcome.HOLD  # in a company, its lines decide


async def test_the_baseline_floor_applies_to_a_personal_line_too(factory, world):
    async with factory() as session:
        await record_approved_line(
            session,
            company_id=USER,
            kind=SCOPE_USER,
            key="write_file",
            line=L1,
            approval_id=uuid.uuid4(),
            decided_by="me",
        )
        await session.commit()
    held = await _me("write_file")  # baseline not relaxed
    assert held.outcome is Outcome.HOLD and held.resolution.source == "baseline_floor"
