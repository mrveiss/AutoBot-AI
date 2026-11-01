# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20030: an ownerless session gets an owner only through an approved proposal, with a record."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import approval_execution
from services import chat_session_owner_action as action

_ADMIN, _OTHER = uuid.uuid4(), uuid.uuid4()


class _Manager:
    def __init__(self, owners: dict, fail: bool = False) -> None:
        self.owners, self.fail, self.written = owners, fail, []

    async def list_sessions(self):
        return [{"chatId": session_id} for session_id in self.owners]

    async def get_session_owner(self, session_id):
        if self.owners[session_id] == "UNREADABLE":
            raise action.SessionOwnerUnreadable(session_id)
        return self.owners[session_id]

    async def update_session_metadata(self, session_id, metadata):
        self.written.append((session_id, metadata))
        return not self.fail


def _session(user_exists: bool = True, admins: int = 2) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    found = MagicMock()
    found.scalars.return_value.first.return_value = uuid.uuid4() if user_exists else None
    found.scalar_one.return_value = admins
    session.execute = AsyncMock(return_value=found)
    return session


def _approval(decider=_OTHER, requested_by=_ADMIN, session_id="s1", owner="alice") -> SimpleNamespace:
    approval = SimpleNamespace(
        id=uuid.uuid4(),
        decided_by_user="owner",
        requested_by_agent=f"chat-session-owner:{requested_by}",
        context={"action": action.ACTION, "session_id": session_id, "owner": owner},
    )
    approval_execution.set_verified_decider(approval, decider)
    return approval


async def _run(manager: _Manager, approval, session):
    redis_set = AsyncMock(return_value=True)
    with (
        patch.object(action, "ChatHistoryManager", return_value=manager),
        patch.object(action, "get_redis_client", AsyncMock()),
        patch.object(action, "SessionOwnershipValidator", return_value=SimpleNamespace(set_session_owner=redis_set)),
        patch.object(action, "audit_log", AsyncMock()) as audit,
    ):
        await action.execute_owner_assign(approval, session)
    return redis_set, audit


async def test_the_report_lists_ownerless_apart_from_unreadable() -> None:
    manager = _Manager({"a": "bob", "b": None, "c": "UNREADABLE"})
    assert await action.ownerless_report(manager) == (["b"], ["c"])


async def test_approval_writes_the_owner_to_file_and_redis_with_a_record() -> None:
    manager, session = _Manager({"s1": None}), _session()
    redis_set, audit = await _run(manager, _approval(), session)
    assert manager.written[0][1]["owner"] == "alice" and manager.written[0][1]["username"] == "alice"
    redis_set.assert_awaited_once_with("s1", "alice", force=True)
    assert "now belongs to alice" in session.add.call_args.args[0].body
    assert [c.kwargs["result"] for c in audit.await_args_list] == ["started", "success"]


async def test_a_session_that_gained_an_owner_is_left_alone() -> None:
    manager, session = _Manager({"s1": "bob"}), _session()
    _, audit = await _run(manager, _approval(), session)
    assert manager.written == [] and "already belongs to bob" in session.add.call_args.args[0].body
    assert audit.await_args.args[1:] == () and audit.await_args.kwargs["result"] == "skipped"


async def test_the_only_admin_may_self_approve_and_it_is_flagged() -> None:
    session = _session(admins=1)
    _, audit = await _run(_Manager({"s1": None}), _approval(decider=_ADMIN), session)
    assert "(self-approved)" in session.add.call_args.args[0].body
    assert audit.await_args.kwargs["details"]["self_approval"] is True


async def test_a_self_approval_with_another_admin_writes_nothing() -> None:
    manager = _Manager({"s1": None})
    with pytest.raises(ValueError):
        await _run(manager, _approval(decider=_ADMIN), _session(admins=2))
    assert manager.written == []


@pytest.mark.parametrize(
    "approval, user_exists",
    [
        (_approval(decider=None), True),
        (_approval(requested_by="someone"), True),
        (_approval(owner=""), True),
        (_approval(session_id=""), True),
        (_approval(), False),
    ],
    ids=["no-verified-decider", "unknown-requester", "no-owner", "no-session", "owner-not-a-user"],
)
async def test_a_bad_approval_writes_nothing(approval, user_exists: bool) -> None:
    manager = _Manager({"s1": None})
    with pytest.raises(ValueError):
        await _run(manager, approval, _session(user_exists))
    assert manager.written == []


async def test_a_failed_file_write_records_no_success() -> None:
    manager, session = _Manager({"s1": None}, fail=True), _session()
    audit = AsyncMock()
    with (
        patch.object(action, "ChatHistoryManager", return_value=manager),
        patch.object(action, "audit_log", audit),
        pytest.raises(ValueError),
    ):
        await action.execute_owner_assign(_approval(), session)
    assert [c.kwargs["result"] for c in audit.await_args_list] == ["started"]


def test_the_action_is_server_only_with_its_proposer() -> None:
    action.register_owner_assign_action()
    assert approval_execution.is_server_only_action(action.ACTION)
    assert approval_execution.registered_action_proposers()[action.ACTION] == action.PROPOSED_BY
