# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19997: the tier column is dropped only by an approved proposal, with a durable record."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import approval_execution
from services import org_tier_column_action as action
from user_management.models.organization import Organization

_ADMIN, _OTHER = uuid.uuid4(), uuid.uuid4()


def _session(present: bool = True, admins: int = 2) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    session.statements = []

    async def _execute(statement):
        session.statements.append(str(statement))
        return MagicMock(first=lambda: (1,) if present else None, scalar_one=lambda: admins)

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
    assert [c.kwargs["result"] for c in audit.await_args_list] == ["started", "success"]
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
    assert [c.kwargs["result"] for c in audit.await_args_list] == ["started"]


@pytest.mark.parametrize(
    ("decider", "requester", "admins"),
    [(_ADMIN, _ADMIN, 2), (None, _ADMIN, 1), (_OTHER, "someone", 2)],
    ids=["self-with-another-admin", "no-verified-decider", "unknown-requester"],
)
async def test_a_decider_who_may_not_decide_changes_nothing(decider, requester, admins: int) -> None:
    session = _session(admins=admins)
    with patch.object(action, "audit_log", AsyncMock()) as audit, pytest.raises(ValueError):
        await action.execute_tier_column_drop(_approval(decider, requester), session)
    assert not _dropped(session)
    audit.assert_not_awaited()


async def test_the_only_admin_may_self_approve_and_it_is_flagged() -> None:
    session = _session(admins=1)
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
