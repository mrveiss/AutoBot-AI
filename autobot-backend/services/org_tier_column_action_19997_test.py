# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19997: the tier column is dropped only by an approved proposal, with a durable record."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from llc.tests.test_ai_lines_api_18430 import factory  # noqa: F401 -- fixture
from llc.tests.test_ai_lines_api_18430 import _gates_client, _rows
from models.approval import Approval, ApprovalComment
from services import approval_execution
from services import org_tier_column_action as action
from user_management.models.organization import Organization
from user_management.models.user import User

_ADMIN, _OTHER = uuid.uuid4(), uuid.uuid4()


def _session(present: bool = True, admins: tuple = (_ADMIN, _OTHER)) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    session.statements = []

    async def _execute(statement):
        session.statements.append(str(statement))
        rows = MagicMock(all=lambda: list(admins))
        return MagicMock(first=lambda: (1,) if present else None, scalars=lambda: rows)

    session.execute = _execute
    return session


def _approval(decider: uuid.UUID | None = _OTHER, requester: object = _ADMIN) -> SimpleNamespace:
    approval = SimpleNamespace(
        id=uuid.uuid4(),
        decided_by_user="owner",
        context={"action": action.ACTION},
        requested_by_agent=f"org-tier-column:{requester}",
    )
    approval_execution.set_verified_decider(approval, decider)
    return approval


def _dropped(session: MagicMock) -> bool:
    return any("DROP COLUMN IF EXISTS subscription_tier" in s for s in session.statements)


@pytest.mark.parametrize(("present", "said"), [(True, "Dropped"), (False, "was gone")])
async def test_approval_drops_it_and_leaves_a_record(present: bool, said: str) -> None:
    session = _session(present)
    with patch.object(action, "audit_log", AsyncMock()) as audit:
        await action.execute_tier_column_drop(_approval(), session)
    assert _dropped(session) and said in session.add.call_args.args[0].body
    session.commit.assert_awaited_once()
    assert [c.kwargs["details"]["stage"] for c in audit.await_args_list] == ["started", "done"]
    assert [c.kwargs["result"] for c in audit.await_args_list] == ["attempted", "success"]
    assert audit.await_args.kwargs["details"]["was_present"] is present


async def test_no_audit_entry_means_no_drop() -> None:
    session = _session()
    with patch.object(action, "audit_log", AsyncMock(side_effect=OSError("no log"))), pytest.raises(OSError):
        await action.execute_tier_column_drop(_approval(), session)
    assert not _dropped(session)


async def test_a_failed_drop_records_no_success() -> None:
    session = _session()
    real = session.execute

    async def _fail(statement):
        if "DROP" in str(statement):
            raise RuntimeError("locked")
        return await real(statement)

    session.execute = _fail
    with patch.object(action, "audit_log", AsyncMock()) as audit, pytest.raises(RuntimeError):
        await action.execute_tier_column_drop(_approval(), session)
    assert [c.kwargs["details"]["stage"] for c in audit.await_args_list] == ["started"]


@pytest.mark.parametrize(
    ("decider", "requester", "admins"),
    [
        (_ADMIN, _ADMIN, (_ADMIN, _OTHER)),
        (None, _ADMIN, (_ADMIN,)),
        (_OTHER, "someone", (_ADMIN, _OTHER)),
        (_ADMIN, _ADMIN, (_OTHER,)),
    ],
    ids=["self-with-another-admin", "no-verified-decider", "unknown-requester", "self-not-the-sole-admin"],
)
async def test_a_decider_who_may_not_decide_changes_nothing(decider, requester, admins: tuple) -> None:
    session = _session(admins=admins)
    with patch.object(action, "audit_log", AsyncMock()) as audit, pytest.raises(ValueError):
        await action.execute_tier_column_drop(_approval(decider, requester), session)
    assert not _dropped(session)
    audit.assert_not_awaited()


async def test_the_only_admin_may_self_approve_and_it_is_flagged() -> None:
    session = _session(admins=(_ADMIN,))
    with patch.object(action, "audit_log", AsyncMock()) as audit:
        await action.execute_tier_column_drop(_approval(_ADMIN, _ADMIN), session)
    assert _dropped(session) and "self-approved" in session.add.call_args.args[0].body
    assert audit.await_args.kwargs["details"]["self_approval"] is True


def test_the_action_is_server_only_with_its_proposer() -> None:
    action.register_tier_column_action()
    assert approval_execution.is_server_only_action(action.ACTION)
    assert approval_execution.registered_action_proposers()[action.ACTION] == action.PROPOSED_BY


def test_no_migration_drops_it_on_an_update() -> None:
    root = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    assert not [p.name for p in root.glob("*.py") if "subscription_tier" in p.read_text(encoding="utf-8")]


def test_the_application_does_not_map_the_column() -> None:
    assert "subscription_tier" not in Organization.__table__.columns


@pytest.mark.asyncio
async def test_the_decider_check_runs_before_the_decision_commits() -> None:
    """Registered as the action's review, so a refused decider leaves the proposal pending rather than approved."""
    action.register_tier_column_action()
    approval = _approval(_ADMIN, _ADMIN)
    approval.context = {"action": action.ACTION}
    with pytest.raises(ValueError):
        await approval_execution.review_decision(approval, _session(admins=(_ADMIN, _OTHER)), _ADMIN)


async def _proposal_by_one_of_two_admins(factory) -> str:  # noqa: F811
    async with factory() as session:
        for user in (_ADMIN, _OTHER):
            session.add(
                User(id=user, email=f"{user}@e.test", username=str(user), is_active=True, is_platform_admin=True)
            )
        row = Approval(
            title="drop", approval_type="workflow_gate", status="pending",
            requested_by_agent=f"org-tier-column:{_ADMIN}", context={"action": action.ACTION},
        )  # fmt: skip
        session.add(row)
        await session.commit()
        return str(row.id)


async def test_the_requester_gets_400_and_the_other_admin_then_succeeds(factory) -> None:  # noqa: F811
    """The real route, service and review over a real store; only the Postgres-only SQL and the audit file stand in."""
    action.register_tier_column_action()
    approval_id = await _proposal_by_one_of_two_admins(factory)
    url = f"/api/approval-gates/{approval_id}/approve"
    with (
        patch.object(action, "_COLUMN_PRESENT", text("SELECT 1")),
        patch.object(action, "_DROP", text("SELECT 1")),
        patch.object(action, "audit_log", AsyncMock()) as audit,
        patch("events.bus.publish_event", AsyncMock()),
    ):
        assert _gates_client(factory, _ADMIN).post(url, json={}).status_code == 400
        [row] = await _rows(factory, Approval)
        assert (row.status, row.decided_by_user) == ("pending", None)
        assert await _rows(factory, ApprovalComment) == []
        audit.assert_not_awaited()
        assert _gates_client(factory, _OTHER).post(url, json={}).status_code == 200
    [row] = await _rows(factory, Approval)
    assert row.status == "approved"
    assert [c.body for c in await _rows(factory, ApprovalComment)] == ["Dropped organizations.subscription_tier."]
    assert [c.kwargs["result"] for c in audit.await_args_list] == ["attempted", "success"]  # #20445 vocabulary
