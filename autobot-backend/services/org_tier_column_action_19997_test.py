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


def _session(present: bool = True) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()

    async def _execute(statement):
        session.statements.append(str(statement))
        return MagicMock(first=lambda: (1,) if present else None)

    session.statements = []
    session.execute = _execute
    return session


def _approval() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), decided_by_user="owner", context={"action": action.ACTION})


@pytest.mark.parametrize(("present", "said"), [(True, "Dropped"), (False, "was gone")])
async def test_approval_drops_it_and_leaves_a_record(present: bool, said: str) -> None:
    session = _session(present)
    with patch.object(action, "audit_log", AsyncMock()) as audit:
        await action.execute_tier_column_drop(_approval(), session)
    assert any("DROP COLUMN IF EXISTS subscription_tier" in s for s in session.statements)
    assert said in session.add.call_args.args[0].body
    session.commit.assert_awaited_once()
    assert audit.await_args.kwargs["details"]["was_present"] is present


async def test_a_failed_drop_records_no_success() -> None:
    session = _session()

    async def _fail(_statement):
        raise RuntimeError("locked")

    session.execute = _fail
    with patch.object(action, "audit_log", AsyncMock()) as audit, pytest.raises(RuntimeError):
        await action.execute_tier_column_drop(_approval(), session)
    audit.assert_not_awaited()


def test_the_action_is_registered_with_its_proposer() -> None:
    action.register_tier_column_action()
    assert approval_execution.is_registered_action(action.ACTION)
    assert approval_execution.registered_action_proposers()[action.ACTION] == action.PROPOSED_BY


def test_no_migration_drops_it_on_an_update() -> None:
    root = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    assert not [p.name for p in root.glob("*.py") if "subscription_tier" in p.read_text(encoding="utf-8")]


def test_the_application_does_not_map_the_column() -> None:
    assert "subscription_tier" not in Organization.__table__.columns
